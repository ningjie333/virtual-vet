#!/usr/bin/env python3
"""
Literature-validated baseline check for VirtualVet engine.

Runs predefined scenarios and compares outputs against published canine
reference ranges from PMID-cited literature. Outputs a pass/warn/fail table.

Usage:
    python tools/dev/validate_baseline.py
    python tools/dev/validate_baseline.py --output validation_report.md
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import logging
logging.disable(logging.WARNING)

from simulation import VirtualCreature
from src.diseases import create_disease

# ── Literature reference ranges ────────────────────────────────────────────
# Each entry: (scenario, variable, engine_attr, ref_low, ref_high, source)

LITERATURE_RANGES = [
    # ── Healthy Baseline ──
    ("healthy", "HR (bpm)",             "heart.heart_rate",               60,   140,  "Nelson & Couto 5e Ch22"),
    ("healthy", "MAP (mmHg)",           "heart.mean_arterial_pressure",    80,   120,  "Nelson & Couto 5e Ch22"),
    ("healthy", "CO (mL/min)",          "heart.cardiac_output",         1400,  2000,  "Guyton 14e Ch20 (20kg dog)"),
    ("healthy", "GFR (mL/min)",         "kidney.GFR",                     50,    80,  "Nelson & Couto 5e Ch53"),
    ("healthy", "SVR",                  "heart.SVR",                     1.0,   1.8,  "Guyton 14e Ch26"),
    ("healthy", "pH",                   "blood.arterial_pH",            7.35,  7.45,  "Nelson & Couto 5e Ch6"),
    ("healthy", "BUN (mg/dL)",          "blood.bun_mg_dL",                10,    28,  "Cornell Vet Lab"),
    ("healthy", "Creatinine (mg/dL)",   "blood.creatinine_mg_dL",       0.5,   1.6,  "Cornell Vet Lab"),
    ("healthy", "Na (mEq/L)",           "blood.sodium_mEq_L",             141,   151,  "Iowa State Vet Path"),
    ("healthy", "K (mEq/L)",            "blood.potassium_mEq_L",        3.9,   5.3,  "Iowa State Vet Path"),
    ("healthy", "Lactate (mmol/L)",     "blood.lactate_mmol_L",         0.5,   2.5,  "IDEXX Catalyst"),
    ("healthy", "ALT (U/L)",            "blood.ALT_U_L",                  17,    95,  "Cornell Vet Lab"),
    ("healthy", "Albumin (g/dL)",       "blood.albumin_g_dL",           3.2,   4.1,  "Cornell Vet Lab"),
    ("healthy", "PaO2 (mmHg)",          "blood.arterial_PO2_mmHg",        85,    95,  "Iowa State Vet Path"),
    ("healthy", "PaCO2 (mmHg)",         "blood.arterial_PCO2_mmHg",       29,    42,  "Iowa State Vet Path"),
    ("healthy", "RR (/min)",            "lung.respiratory_rate",           10,    30,  "Nelson & Couto 5e Ch6"),

    # ── ARF Moderate ──
    ("arf",     "GFR decline (%)",      "kidney.GFR",                     30,    60,  "Nelson & Couto 5e Ch53 (moderate ARF: GFR 30-60% of normal)"),
    ("arf",     "BUN elevation (mg/dL)","blood.bun_mg_dL",                25,    60,  "Nelson & Couto 5e Ch53"),
    ("arf",     "Cr elevation (mg/dL)", "blood.creatinine_mg_dL",        1.5,   4.0,  "Nelson & Couto 5e Ch53"),
    ("arf",     "K+ elevation (mEq/L)", "blood.potassium_mEq_L",        4.5,   6.0,  "Nelson & Couto 5e Ch53 (hyperkalemia in ARF)"),

    # ── Hemorrhage 400mL ──
    ("hemorrhage", "HR compensation",   "heart.heart_rate",              120,   180,  "Guyton 14e Ch26 (Class II-III hemorrhage)"),
    ("hemorrhage", "MAP drop (mmHg)",   "heart.mean_arterial_pressure",   70,   100,  "Guyton 14e Ch26 (400mL loss on 20kg dog)"),
    ("hemorrhage", "BV remaining (%)",  "heart.circulating_volume_ml",  1200,  1500,  "Guyton 14e Ch26 (20-25% loss)"),

    # ── Pneumonia Moderate ──
    ("pneumonia", "HR elevation",       "heart.heart_rate",              100,   160,  "Nelson & Couto 5e Ch11"),
    ("pneumonia", "PaO2 depression",    "blood.arterial_PO2_mmHg",        50,    80,  "Nelson & Couto 5e Ch11 (V/Q mismatch)"),
]


def get_nested_attr(obj, path: str):
    """Get attribute by dot-separated path like 'heart.heart_rate'."""
    parts = path.split(".")
    for part in parts:
        obj = getattr(obj, part)
    return obj


def run_scenario(name: str, setup_fn, steps: int) -> VirtualCreature:
    c = VirtualCreature(body_weight_kg=20.0)
    setup_fn(c)
    for _ in range(steps):
        c.step()
    return c


def main():
    # Define scenarios
    def healthy_setup(c): pass

    def arf_setup(c):
        d = create_disease("acute_renal_failure", severity="moderate")
        c.attach_disease(d)

    def hemorrhage_setup(c):
        c.schedule_event(2.0, "blood_loss", {"volume_ml": 400.0})

    def pneumonia_setup(c):
        d = create_disease("pneumonia", severity="moderate")
        c.attach_disease(d)

    scenarios = {
        "healthy":    (healthy_setup,    300),
        "arf":        (arf_setup,        600),
        "hemorrhage": (hemorrhage_setup, 300),
        "pneumonia":  (pneumonia_setup,  600),
    }

    results = {}
    for name, (setup_fn, steps) in scenarios.items():
        c = run_scenario(name, setup_fn, steps)
        results[name] = c

    # Compare against literature
    lines = [
        "# VirtualVet Validation Report — Literature Comparison",
        "",
        "| Scenario | Variable | Simulated | Literature Range | Status | Source |",
        "|---|---|---|---|---|---|",
    ]

    pass_count = 0
    warn_count = 0
    fail_count = 0

    for scenario, var_name, attr, ref_low, ref_high, source in LITERATURE_RANGES:
        if scenario not in results:
            continue
        c = results[scenario]
        try:
            val = get_nested_attr(c, attr)
        except AttributeError:
            lines.append(f"| {scenario} | {var_name} | N/A | {ref_low}-{ref_high} | SKIP | {source} |")
            continue

        # For percentage-type metrics, compute from baseline
        if "%" in var_name and scenario != "healthy":
            baseline_val = get_nested_attr(results["healthy"], attr)
            if baseline_val > 0:
                val_pct = val / baseline_val * 100
                val_display = f"{val_pct:.0f}%"
            else:
                val_display = f"{val:.1f}"
        else:
            val_display = f"{val:.1f}"

        if ref_low <= val <= ref_high:
            status = "PASS"
            pass_count += 1
        elif val < ref_low * 0.8 or val > ref_high * 1.2:
            status = "FAIL"
            fail_count += 1
        else:
            status = "WARN"
            warn_count += 1

        lines.append(
            f"| {scenario} | {var_name} | {val_display} | {ref_low}-{ref_high} | {status} | {source} |"
        )

    lines.append("")
    lines.append(f"**Summary**: {pass_count} PASS, {warn_count} WARN, {fail_count} FAIL")
    lines.append("")

    # Identify top issues
    if fail_count > 0 or warn_count > 0:
        lines.append("## Issues Requiring Calibration")
        lines.append("")
        for scenario, var_name, attr, ref_low, ref_high, source in LITERATURE_RANGES:
            if scenario not in results:
                continue
            c = results[scenario]
            try:
                val = get_nested_attr(c, attr)
            except AttributeError:
                continue
            if val < ref_low * 0.8 or val > ref_high * 1.2:
                lines.append(f"- **{scenario}/{var_name}**: simulated={val:.1f}, expected {ref_low}-{ref_high} ({source})")
        lines.append("")

    report = "\n".join(lines)

    # Write to file
    out_path = PROJECT_ROOT / "tools" / "dev" / "validation_report.md"
    out_path.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nReport saved to {out_path}")


if __name__ == "__main__":
    main()
