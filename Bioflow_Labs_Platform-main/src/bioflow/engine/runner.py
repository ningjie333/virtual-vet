# src/bioflow/engine/runner.py
from __future__ import annotations

from dataclasses import replace
from typing import Dict, List, Tuple

import json
from pathlib import Path
from typing import Any

from bioflow.core.validate_template import validate_template
from bioflow.core.hashing import hash_json
from bioflow.core.version import ENGINE_VERSION
from bioflow.core.logging import event

from bioflow.db.conn import connect
from bioflow.db.schema import init_db
from bioflow.db.templates import fetch_template_by_id, fetch_template_by_hash, insert_template
from bioflow.db.runs import create_run, append_sample, append_event, finalize_run, commit_buffer

from bioflow.engine.state import GlobalState
from bioflow.engine.physiology.algebraic import (
    BedParameters,
    compute_bed_flows,
    total_flow_ml_per_s,
)

from bioflow.engine.physiology.compliance import (
    step_phase41_compliance,
    CompartmentParameters,
)


class RunnerError(RuntimeError):
    pass


def _load_template_from_path(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8"))


def _build_initial_state(template: dict[str, Any]) -> GlobalState:
    init = template.get("initial_state") or {}
    resolved = template["resolved_parameters"]

    total_ml = float(resolved["total_blood_volume_ml"])

    V_art = float(init.get("V_art_ml", 0.30 * total_ml))
    V_ven = float(init.get("V_ven_ml", total_ml - V_art))

    # pressures will be computed on first step; store something deterministic now
    P_art = float(init.get("P_art_mmHg", resolved.get(
        "baseline", {}).get("P_art_mmHg", 95.0)))
    P_ven = float(init.get("P_ven_mmHg", resolved.get(
        "baseline", {}).get("P_ven_mmHg", 5.0)))

    return GlobalState(
        t_s=0.0,
        V_art_ml=V_art,
        V_ven_ml=V_ven,
        P_art_mmHg=P_art,
        P_ven_mmHg=P_ven,
        bed_Q_ml_per_s={},
        bed_perfusion_index={},
    )


# src/bioflow/engine/runner.py


def _build_bed_parameters_from_template(template: dict) -> List[BedParameters]:
    """
    Extract bed list from resolved template fields.
    Adjust keys to match your actual template structure.
    """
    resolved = template["resolved_parameters"]
    beds_raw = resolved["beds"]

    beds: List[BedParameters] = []
    for bed in beds_raw:
        beds.append(
            BedParameters(
                bed_id=str(bed["bed_id"]),
                R_mmHg_s_per_ml=float(bed["R_mmHg_s_per_ml"]),
            )
        )
    return beds


def _compute_baseline_flows(template: dict, beds: List[BedParameters]) -> Dict[str, float]:
    """
    Baseline is computed ONCE from the template's baseline pressures.
    This avoids hidden state and keeps determinism tight.

    If you don't have baseline pressures, pick the template's initial_state pressures.
    """
    resolved = template["resolved_parameters"]

    # Prefer explicit baseline, fall back to initial_state
    baseline = resolved.get("baseline", {})  # optional
    P_art0 = float(baseline.get("P_art_mmHg", template.get(
        "initial_state", {}).get("P_art_mmHg", 95.0)))
    P_ven0 = float(baseline.get("P_ven_mmHg", template.get(
        "initial_state", {}).get("P_ven_mmHg", 5.0)))

    flows = compute_bed_flows(
        P_art_mmHg=P_art0,
        P_ven_mmHg=P_ven0,
        beds=beds,
        # temp seed, replaced below
        baseline_flows_ml_per_s={bed.bed_id: 1.0 for bed in beds},
    )

    # Use the computed baseline as baseline (so baseline index will be 100 later)
    return {f.bed_id: f.Q_ml_per_s for f in flows}


def _step_phase4_algebraic(
    *,
    prev_state: GlobalState,
    template: dict,
    dt_s: float,
    beds: List[BedParameters],
    baseline_flows_ml_per_s: Dict[str, float],
) -> Tuple[GlobalState, dict]:
    """
    Phase 4 step:
    - pressures stay constant (for now)
    - bed flows are computed algebraically
    - returns new state + a small 'summary delta' dict (optional)
    """
    # Time update is the only "evolution" in Phase 4
    t_next_s = prev_state.t_s + dt_s

    bed_flow_results = compute_bed_flows(
        P_art_mmHg=prev_state.P_art_mmHg,
        P_ven_mmHg=prev_state.P_ven_mmHg,
        beds=beds,
        baseline_flows_ml_per_s=baseline_flows_ml_per_s,
    )

    bed_Q = {r.bed_id: r.Q_ml_per_s for r in bed_flow_results}
    bed_perf = {r.bed_id: r.perfusion_index for r in bed_flow_results}

    total_Q = total_flow_ml_per_s(bed_flow_results)

    next_state = replace(
        prev_state,
        t_s=t_next_s,
        bed_Q_ml_per_s=bed_Q,
        bed_perfusion_index=bed_perf,
    )

    step_metrics = {
        "total_flow_ml_per_s": total_Q,
        "P_art_mmHg": prev_state.P_art_mmHg,
        "P_ven_mmHg": prev_state.P_ven_mmHg,
    }
    return next_state, step_metrics


def run_template(
    *,
    template: dict[str, Any],
    db_path: str | Path,
    dt: float,
    duration_s: float,
    sample_rate_hz: float,
    conn=None,
) -> dict[str, Any]:
    """
    Runs from a direct template object. Writes a run record + samples/events to DB.
    Returns a run artifact dict (includes run_id, hashes, summary).
    """
    validation = validate_template(template)
    if not validation["is_valid"]:
        raise RunnerError(f"Template not runnable: {validation['errors'][:3]}")

    conn = connect(db_path)

    try:
        init_db(conn)

        template_hash = validation["template_hash"]
        run_config = {
            "dt": float(dt),
            "duration_s": float(duration_s),
            "sample_rate_hz": float(sample_rate_hz),
        }

        existing = fetch_template_by_hash(conn, template_hash)
        if existing is None:
            insert_template(conn, name=None, template=template,
                            validation=validation)

        run_id = create_run(
            conn,
            template_hash=template_hash,
            template_snapshot=template,  # snapshot is what was run
            engine_version=ENGINE_VERSION,
            run_config=run_config,
        )

        event("run_start", run_id=run_id, template_hash=template_hash,
              engine_version=ENGINE_VERSION)

        # --- execution ---------------------------------------------------------
        state = _build_initial_state(template)

        # sample scheduling
        sample_every_s = 1.0 / float(sample_rate_hz)
        next_sample_t = 0.0

        steps = int(round(duration_s / dt))
        wrote_anything = False

        # Phase 4.x bed params + baseline (perfusion normalization)
        beds = _build_bed_parameters_from_template(template)
        baseline_flows = _compute_baseline_flows(template, beds)

        # Phase 4.1: pump + compliance compartments (required now)
        rp = template["resolved_parameters"]

        pump_Q_ml_per_s = float(rp["pump"]["Q_ml_per_s"])

        art_cfg = rp["compartments"]["arterial"]
        ven_cfg = rp["compartments"]["venous"]

        arterial = CompartmentParameters(
            C_ml_per_mmHg=float(art_cfg["C_ml_per_mmHg"]),
            V0_ml=float(art_cfg["V0_ml"]),
        )
        venous = CompartmentParameters(
            C_ml_per_mmHg=float(ven_cfg["C_ml_per_mmHg"]),
            V0_ml=float(ven_cfg["V0_ml"]),
        )

        try:
            for _ in range(steps + 1):
                t = state.t_s

                # write sample BEFORE stepping (t-aligned)
                if t + 1e-12 >= next_sample_t:
                    append_sample(
                        conn,
                        run_id=run_id,
                        t_ms=int(round(t * 1000.0)),
                        global_state=state.to_json(),
                    )
                    wrote_anything = True
                    next_sample_t += sample_every_s

                # Phase 4.1 step (volumes + compliance + algebraic beds)
                state, step_metrics = step_phase41_compliance(
                    prev_state=state,
                    dt_s=float(dt),
                    beds=beds,
                    baseline_flows_ml_per_s=baseline_flows,
                    pump_Q_ml_per_s=pump_Q_ml_per_s,
                    art=arterial,
                    ven=venous,
                )

            # commit buffered sample inserts once
            commit_buffer(conn)

            summary = {
                "final_t_s": state.t_s,

                "final_P_art_mmHg": state.P_art_mmHg,
                "final_P_ven_mmHg": state.P_ven_mmHg,

                "final_V_art_ml": state.V_art_ml,
                "final_V_ven_ml": state.V_ven_ml,
                "final_total_volume_ml": state.V_art_ml + state.V_ven_ml,

                "samples_written": wrote_anything,
            }

            # Deterministic summary hash: hash of {template_hash + run_config + summary}
            summary_hash = hash_json(
                {"template_hash": template_hash,
                    "run_config": run_config, "summary": summary}
            )
            summary["summary_hash"] = summary_hash

            finalize_run(conn, run_id=run_id, summary=summary)

            return {
                "run_id": run_id,
                "template_hash": template_hash,
                "engine_version": ENGINE_VERSION,
                "run_config": run_config,
                "summary": summary,
            }

        except Exception as e:
            # record event, but do NOT finalize summary (no partial run “success”)
            append_event(
                conn,
                run_id=run_id,
                t_ms=int(round(state.t_s * 1000.0)),
                level="ERROR",
                code="run_failed",
                message=str(e),
            )
            commit_buffer(conn)
            raise

    finally:
        conn.close()


def run_template_from_json_file(
    *,
    json_path: str | Path,
    db_path: str | Path,
    dt: float,
    duration_s: float,
    sample_rate_hz: float,
) -> dict[str, Any]:
    return run_template(
        template=_load_template_from_path(json_path),
        db_path=db_path,
        dt=dt,
        duration_s=duration_s,
        sample_rate_hz=sample_rate_hz,
    )


def run_template_by_db_id(
    *,
    template_id: int,
    db_path: str | Path,
    dt: float,
    duration_s: float,
    sample_rate_hz: float,
) -> dict[str, Any]:
    conn = connect(db_path)
    try:
        init_db(conn)

        row = fetch_template_by_id(conn, int(template_id))
        if row is None:
            raise RunnerError(f"No template with id={template_id}")

        template = json.loads(row["json"])

        return run_template(
            template=template,
            db_path=db_path,
            dt=dt,
            duration_s=duration_s,
            sample_rate_hz=sample_rate_hz,
            conn=conn,   # reuse same connection
        )
    finally:
        conn.close()
