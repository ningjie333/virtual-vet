#!/usr/bin/env python
"""
Experiment 5: Chemoreceptor Parameter Sweep
============================================
Three sub-experiments investigating chemoreceptor gain and dynamics:

  1. Chemo multiplier sweep  — vary chemo_HR_add gain in [5, 10, 15, 20, 30, 50]
  2. Chemo time constant sweep — vary chemo low-pass tau in [5, 10, 30, 60, 120] s
  3. VdP oscillator PO2 analysis — characterize steady-state PO2 oscillation

Prediction (Exp 1): higher multiplier → larger FC amplitude → same chemo_drive
  threshold (0.1/multiplier) → earlier FC onset → same final MAP (saturation at 144.7)

Prediction (Exp 2): shorter tau → faster chemo integration → earlier FC onset
"""

import sys
import os
import types
import time as time_module
import numpy as np

_EXPERIMENTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_EXPERIMENTS_DIR)
_SRC_DIR = os.path.join(_PROJECT_ROOT, "src")
sys.path.insert(0, _SRC_DIR)


# ═══════════════════════════════════════════════════════════════════════════════
# Module loading (patched for standalone execution)
# ═══════════════════════════════════════════════════════════════════════════════

def _read_patched(path):
    """Remove 'from src.' prefix so modules find each other in sys.modules."""
    return open(path, encoding="utf-8").read().replace("from src.", "from ")


sys.modules["parameters"] = types.ModuleType("parameters")
exec(compile(_read_patched(os.path.join(_SRC_DIR, "parameters.py")),
             os.path.join(_SRC_DIR, "parameters.py"), "exec"),
     sys.modules["parameters"].__dict__)

for _name in ["blood", "fluid", "cardiac_electrophysiology", "noble_purkinje",
              "respiratory_rhythm", "heart", "lung", "kidney", "gut", "liver",
              "endocrine", "neuro", "immune", "coagulation", "lymphatic",
              "lifecycle", "toxicology", "organ_health", "pharmacology", "simulation"]:
    _path = os.path.join(_SRC_DIR, f"{_name}.py")
    _src = _read_patched(_path)
    _mod = types.ModuleType(_name)
    sys.modules[_name] = _mod
    exec(compile(_src, _path, "exec"), _mod.__dict__)

VirtualCreature = sys.modules["simulation"].VirtualCreature
NeuroModule = sys.modules["neuro"].NeuroModule
FactorCommand = sys.modules["simulation"].FactorCommand


# ═══════════════════════════════════════════════════════════════════════════════
# Monkey-patching helpers
# ═══════════════════════════════════════════════════════════════════════════════

_ORIG_COMPUTE = NeuroModule.compute


def _make_patched_mult(multiplier):
    """Replace chemo_HR_add in NeuroModule.compute with `chemo_drive * multiplier`.

    Strips all existing heart_rate factor commands (pain, seizure, CNS) and
    replaces them with a single chemo-derived add. For a healthy animal without
    pain/seizure/CNS involvement, this is equivalent to changing just the gain.
    """
    def patched_compute(self, dt, heart_state, lung_state):
        result = _ORIG_COMPUTE(self, dt, heart_state, lung_state)
        other_fcs = [fc for fc in result.get("factor_commands", [])
                     if fc.target != "heart.heart_rate"]
        new_net_HR_add = self.chemoreceptor_drive * multiplier
        if abs(new_net_HR_add) > 0.1:
            other_fcs.append(FactorCommand("heart.heart_rate", "add", new_net_HR_add))
        result["factor_commands"] = other_fcs
        result["net_HR_add"] = round(new_net_HR_add, 1)
        return result
    return patched_compute


def _make_patched_tau(tau):
    """Replace the chemo low-pass filter time constant in NeuroModule.compute.

    The default tau=30 s means alpha = dt/30.  This patch overrides it to
    alpha = dt/tau, giving faster (shorter tau) or slower (longer tau)
    integration of chemoreceptor drive.
    """
    def patched_compute(self, dt, heart_state, lung_state):
        # Save pre-update drive before ORIG_COMPUTE overwrites it with tau=30
        saved_drive = self.chemoreceptor_drive
        result = _ORIG_COMPUTE(self, dt, heart_state, lung_state)

        # Recalculate raw chemoreceptor signal from blood gases
        PO2 = self.blood.arterial_PO2_mmHg
        PCO2 = self.blood.arterial_PCO2_mmHg
        pH = self.blood.arterial_pH
        hypoxia_signal = max(0.0, (70.0 - PO2) / 70.0) if PO2 < 70 else 0.0
        hypercapnia_signal = max(0.0, (PCO2 - 50.0) / 50.0) if PCO2 > 50 else 0.0
        acidosis_signal = max(0.0, (7.35 - pH) / 0.35) if pH < 7.35 else 0.0
        chemoreceptor_raw = min(1.0, hypoxia_signal + hypercapnia_signal + acidosis_signal)

        # Reapply low-pass with requested tau
        new_drive = saved_drive + (dt / tau) * (chemoreceptor_raw - saved_drive)
        self.chemoreceptor_drive = max(0.0, min(1.0, new_drive))

        # Rebuild factor commands with corrected drive (default multiplier 15)
        net_HR_add = self.chemoreceptor_drive * 15.0
        new_fcs = [fc for fc in result.get("factor_commands", [])
                   if fc.target != "heart.heart_rate"]
        if abs(net_HR_add) > 0.1:
            new_fcs.append(FactorCommand("heart.heart_rate", "add", net_HR_add))
        result["factor_commands"] = new_fcs
        result["chemoreceptor_drive"] = round(self.chemoreceptor_drive, 3)
        result["net_HR_add"] = round(net_HR_add, 1)
        return result
    return patched_compute


# ═══════════════════════════════════════════════════════════════════════════════
# Simulation runner
# ═══════════════════════════════════════════════════════════════════════════════

def _run_and_track(dt, t_end, effective_multiplier):
    """Run simulation with *already-patched* NeuroModule and return traces.

    effective_multiplier: used to determine FC threshold for tracking.
      For mult sweep = the sweep value; for tau sweep = 15 (default).
    """
    n_steps = int(t_end / dt)
    vc = VirtualCreature(body_weight_kg=20.0)
    vc.dt = dt

    fc_count = 0
    first_fc_time = None

    traces = {
        "t": np.zeros(n_steps),
        "MAP": np.zeros(n_steps),
        "HR": np.zeros(n_steps),
        "chemo_drive": np.zeros(n_steps),
        "PO2": np.zeros(n_steps),
    }

    fc_threshold_hr = 0.1  # FactorCommand threshold for heart_rate add

    for i in range(n_steps):
        vc.step()
        t_s = vc.current_time_s

        traces["t"][i] = t_s
        traces["MAP"][i] = vc.heart.mean_arterial_pressure
        traces["HR"][i] = vc.heart.heart_rate
        traces["chemo_drive"][i] = vc.neuro.chemoreceptor_drive
        traces["PO2"][i] = vc.blood.arterial_PO2_mmHg

        # Track factor command: issued when chemo_drive * eff_mult > 0.1
        if vc.neuro.chemoreceptor_drive * effective_multiplier > fc_threshold_hr:
            fc_count += 1
            if first_fc_time is None:
                first_fc_time = t_s

    return traces, fc_count, first_fc_time


# ═══════════════════════════════════════════════════════════════════════════════
# Experiment 1: Multiplier sweep
# ═══════════════════════════════════════════════════════════════════════════════

def experiment_multiplier_sweep(dt=0.01, t_end=60.0):
    """Vary chemo --> HR gain multiplier: [5, 10, 15, 20, 30, 50]."""
    multipliers = [5, 10, 15, 20, 30, 50]
    print()
    print("=" * 88)
    print("  Experiment 1: Chemo Multiplier Sweep")
    print("=" * 88)
    print()
    print("  Prediction: higher multiplier -> larger FC amplitude ->")
    print("  same chemo_drive threshold (0.1/mult) -> earlier FC onset ->")
    print("  same final MAP (~144.7)")
    print()
    print(f"  dt={dt}s, t_end={t_end}s ({int(t_end/dt)} steps/run)")
    print()

    sep = "-" * 80
    hdr = (f"  {'mult':>6}  {'final_MAP':>10}  {'final_HR':>9}  "
           f"{'FC_count':>8}  {'chemo_drive':>9}  {'first_FC(s)':>10}  "
           f"{'FC_thr':>8}")
    print(hdr)
    print(f"  {sep}")

    row_fmt = "  {mult:>6d}  {map:>10.2f}  {hr:>9.1f}  {fc:>8d}  {cd:>9.5f}  {ff:>10}  {thr:>8.5f}"

    results = {}
    for mult in multipliers:
        t0_run = time_module.time()
        NeuroModule.compute = _make_patched_mult(mult)
        try:
            traces, fc_count, first_fc = _run_and_track(dt, t_end, mult)
        finally:
            NeuroModule.compute = _ORIG_COMPUTE
        elapsed = time_module.time() - t0_run

        fm = traces["MAP"][-1]
        fh = traces["HR"][-1]
        cd = traces["chemo_drive"][-1]
        thr = 0.1 / mult
        ff_str = f"{first_fc:.2f}" if first_fc is not None else "never"

        print(row_fmt.format(mult=mult, map=fm, hr=fh, fc=fc_count,
                             cd=cd, ff=ff_str, thr=thr))

        results[mult] = {
            "final_MAP": float(fm),
            "final_HR": float(fh),
            "FC_count": fc_count,
            "final_chemo_drive": float(cd),
            "first_FC_time": first_fc,
            "FC_threshold": thr,
            "elapsed_s": round(elapsed, 2),
        }

    print(f"  {sep}")
    print()
    return results, traces


# ═══════════════════════════════════════════════════════════════════════════════
# Experiment 2: Time constant sweep
# ═══════════════════════════════════════════════════════════════════════════════

def experiment_tau_sweep(dt=0.01, t_end=60.0):
    """Vary chemo low-pass filter tau: [5, 10, 30, 60, 120] seconds."""
    taus = [5, 10, 30, 60, 120]
    print()
    print("=" * 88)
    print("  Experiment 2: Chemo Time Constant (tau) Sweep")
    print("=" * 88)
    print()
    print("  Prediction: shorter tau -> faster chemo integration ->")
    print("  earlier FC onset")
    print()
    print(f"  dt={dt}s, t_end={t_end}s ({int(t_end/dt)} steps/run)")
    print()

    sep = "-" * 80
    hdr = (f"  {'tau(s)':>6}  {'final_MAP':>10}  {'final_HR':>9}  "
           f"{'FC_count':>8}  {'chemo_drive':>9}  {'first_FC(s)':>10}  "
           f"{'alpha':>8}")
    print(hdr)
    print(f"  {sep}")

    row_fmt = "  {tau:>6d}  {map:>10.2f}  {hr:>9.1f}  {fc:>8d}  {cd:>9.5f}  {ff:>10}  {alpha:>8.5f}"

    results = {}
    for tau in taus:
        t0_run = time_module.time()
        NeuroModule.compute = _make_patched_tau(tau)
        try:
            # effective_multiplier is 15 (default) since tau patch leaves gain alone
            traces, fc_count, first_fc = _run_and_track(dt, t_end, 15.0)
        finally:
            NeuroModule.compute = _ORIG_COMPUTE
        elapsed = time_module.time() - t0_run

        fm = traces["MAP"][-1]
        fh = traces["HR"][-1]
        cd = traces["chemo_drive"][-1]
        alpha = dt / tau
        ff_str = f"{first_fc:.2f}" if first_fc is not None else "never"

        print(row_fmt.format(tau=tau, map=fm, hr=fh, fc=fc_count,
                             cd=cd, ff=ff_str, alpha=alpha))

        results[tau] = {
            "final_MAP": float(fm),
            "final_HR": float(fh),
            "FC_count": fc_count,
            "final_chemo_drive": float(cd),
            "first_FC_time": first_fc,
            "alpha": alpha,
            "elapsed_s": round(elapsed, 2),
        }

    print(f"  {sep}")
    print()
    return results


# ═══════════════════════════════════════════════════════════════════════════════
# Experiment 3: VdP oscillator PO2 analysis
# ═══════════════════════════════════════════════════════════════════════════════

def experiment_vdp_analysis(dt=0.01, t_end=120.0):
    """Characterize steady-state PO2 oscillation from VdP respiratory rhythm.

    Runs 30s warmup to reach steady state, then records 60s of data.
    """
    print()
    print("=" * 88)
    print("  Experiment 3: VdP Oscillator -- PO2 Oscillation Analysis")
    print("=" * 88)
    print()
    print("  Runs 30s warmup, then records 60s steady-state PO2 trace")
    print("  to quantify hypoxic drive during normal respiratory cycling.")
    print()

    warmup_steps = int(30.0 / dt)
    record_steps = int(t_end / dt) - warmup_steps

    vc = VirtualCreature(body_weight_kg=20.0)
    vc.dt = dt

    for _ in range(warmup_steps):
        vc.step()

    po2_vals = np.zeros(record_steps)
    vdp_amp_vals = np.zeros(record_steps)

    for i in range(record_steps):
        vc.step()
        po2_vals[i] = vc.blood.arterial_PO2_mmHg
        vdp_amp_vals[i] = vc.lung._vdp.amplitude

    po2_min = po2_vals.min()
    po2_max = po2_vals.max()
    po2_mean = po2_vals.mean()
    po2_below_70_pct = 100.0 * np.mean(po2_vals < 70.0)

    hypoxic_drive_vals = np.maximum(0.0, (70.0 - po2_vals) / 70.0)
    mean_hypoxic_drive = hypoxic_drive_vals.mean()
    peak_hypoxic_drive = hypoxic_drive_vals.max()

    print(f"  PO2 range:            {po2_min:.1f} -- {po2_max:.1f} mmHg")
    print(f"  PO2 mean:             {po2_mean:.1f} mmHg")
    print(f"  Hypoxia threshold:    70 mmHg")
    print(f"  Time below 70 mmHg:   {po2_below_70_pct:.1f}% of cycle")
    print(f"  Hypoxic drive (mean): {mean_hypoxic_drive:.4f}")
    print(f"  Hypoxic drive (peak): {peak_hypoxic_drive:.4f}")
    print(f"  VdP amplitude range:  {vdp_amp_vals.min():.3f} -- {vdp_amp_vals.max():.3f}")
    print()

    # Consequence for chemoreceptor
    print("  ---")
    print(f"  At default multiplier=15 and tau=30 s:")
    print(f"    During hypoxic dip:  chemo_HR_add = 15 * {mean_hypoxic_drive:.4f} = {15*mean_hypoxic_drive:.1f} bpm (mean)")
    print(f"    At peak hypoxia:     chemo_HR_add = 15 * {peak_hypoxic_drive:.4f} = {15*peak_hypoxic_drive:.1f} bpm (peak)")
    print(f"    FC enabled when chemo_drive > {0.1/15:.4f} ({0.1/15:.1%} of max)")
    print()

    return {
        "PO2_min": float(po2_min),
        "PO2_max": float(po2_max),
        "PO2_mean": float(po2_mean),
        "pct_below_70": float(po2_below_70_pct),
        "mean_hypoxic_drive": float(mean_hypoxic_drive),
        "peak_hypoxic_drive": float(peak_hypoxic_drive),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    t_start = time_module.time()

    dt = 0.01
    t_end = 60.0

    # ── Exp 1: Multiplier sweep (maps / traces saved for last run) ──
    r1, last_traces = experiment_multiplier_sweep(dt, t_end)

    # ── Exp 2: Tau sweep ──
    r2 = experiment_tau_sweep(dt, t_end)

    # ── Exp 3: VdP analysis ──
    r3 = experiment_vdp_analysis(dt, t_end=120.0)

    elapsed = time_module.time() - t_start
    print(f"  Total experiment time: {elapsed:.1f}s")
    print()

    # ── Summary of predictions ──
    print("=" * 88)
    print("  Summary")
    print("=" * 88)
    print()
    print("  Exp 1 (multiplier sweep):")
    print(f"    MAP saturation: {r1[15]['final_MAP']:.1f} mmHg (default mult=15)")
    for m in [5, 10, 20, 30, 50]:
        delta = r1[m]["final_MAP"] - r1[15]["final_MAP"]
        fc_time_1 = r1[m]['first_FC_time']
        fc_str_1 = f"{fc_time_1:.2f}" if fc_time_1 is not None else "never"
        print(f"    mult={m:2d}: MAP={r1[m]['final_MAP']:.1f} (delta={delta:+.1f}), "
              f"first_FC={fc_str_1}s, "
              f"FC_count={r1[m]['FC_count']}")
    print()
    print("  Exp 2 (tau sweep):")
    for tau in [5, 10, 30, 60, 120]:
        fc_time_2 = r2[tau]['first_FC_time']
        fc_str_2 = f"{fc_time_2:.2f}" if fc_time_2 is not None else "never"
        print(f"    tau={tau:3d}s: MAP={r2[tau]['final_MAP']:.1f}, "
              f"first_FC={fc_str_2}s, "
              f"FC_count={r2[tau]['FC_count']}, "
              f"chemo_drive={r2[tau]['final_chemo_drive']:.4f}")
    print()


if __name__ == "__main__":
    main()
