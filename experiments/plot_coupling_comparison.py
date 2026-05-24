"""Figure 4: Coupling Strategy Comparison — MAP/HR/CO/BV Time Series"""

import json
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

_EXPERIMENTS_DIR = os.path.dirname(os.path.abspath(__file__))
_DATA_PATH = os.path.join(_EXPERIMENTS_DIR, "coupling_comparison_data.json")

with open(_DATA_PATH) as f:
    data = json.load(f)

seq = data["sequential"]["time_series"]
semi = data["semi_implicit"]["time_series"]

def extract(key, series):
    return [p[key] for p in series]

t_seq = extract("t", seq)
t_semi = extract("t", semi)

fig, axes = plt.subplots(2, 2, figsize=(12, 8))
fig.suptitle("Figure 4: Coupling Strategy Comparison — Hemorrhagic Shock (20 kg Dog)", fontsize=13, fontweight="bold")

varnames = [("MAP", "MAP (mmHg)", "tab:blue"), ("HR", "HR (bpm)", "tab:red"),
            ("CO", "CO (mL/min)", "tab:green"), ("blood_volume_mL", "Blood Volume (mL)", "tab:orange")]

for ax, (key, ylabel, color) in zip(axes.flat, varnames):
    seq_vals = extract(key, seq)
    semi_vals = extract(key, semi)

    ax.plot(t_seq, seq_vals, "o-", color=color, label="Sequential (Euler dt=0.05s)", linewidth=1.5, markersize=4)
    ax.plot(t_semi, semi_vals, "s--", color=color, alpha=0.6, label="Semi-implicit (Radau)", linewidth=1.5, markersize=4)
    ax.axvline(x=5.0, color="gray", linestyle=":", alpha=0.7)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel(ylabel)
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

fig.tight_layout(rect=[0, 0, 1, 0.96])

out_path = os.path.join(_EXPERIMENTS_DIR, "figure4_coupling_comparison.png")
fig.savefig(out_path, dpi=150, bbox_inches="tight")
print(f"Figure saved → {out_path}")