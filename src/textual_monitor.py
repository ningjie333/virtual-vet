"""
Textual Patient Monitor — Real-time interactive terminal UI.

Combines:
  - ASCII heart animation (parameter-driven beating)
  - Sparkline vital sign trends (Textual built-in)
  - Truecolor medical colormaps (from life-simulator)
  - Organ status grid + clinical signs

Usage:
    uv run python src/textual_monitor.py
    uv run python src/textual_monitor.py --disease dka --severity severe
"""

from __future__ import annotations

import os
import sys
from typing import Any

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from textual.app import App, ComposeResult
from textual.color import Color
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Digits, Label, ProgressBar, Sparkline, Static

# ── Disease aliases ────────────────────────────────────────────

_DISEASE_ALIASES = {
    "dka": "diabetic_ketoacidosis",
    "arf": "acute_renal_failure",
    "dcm": "dilated_cardiomyopathy",
    "gdv": "gastric_dilatation_volvulus",
    "imha": "immune_mediated_hemolytic_anemia",
    "dic": "disseminated_intravascular_coagulation",
    "ckd": "ckd_anemia",
    "bloat": "gastric_dilatation_volvulus",
}

def _resolve_disease(name: str) -> str:
    return _DISEASE_ALIASES.get(name.lower(), name)


# ── Heart frames ──────────────────────────────────────────────

HEART_FRAMES = [
    # 0: end-systole
    [
        "      ╱╲      ",
        "    ╱    ╲    ",
        "  ╱   ♥♥   ╲  ",
        " │    ♥♥    │ ",
        "  ╲        ╱  ",
        "    ╲    ╱    ",
        "      ╲╱      ",
    ],
    # 1: early filling
    [
        "     ╱──╲     ",
        "   ╱      ╲   ",
        " ╱   ♥♥♥♥   ╲ ",
        "│    ♥♥♥♥    │",
        " ╲          ╱ ",
        "   ╲      ╱   ",
        "     ╲──╱     ",
    ],
    # 2: mid filling
    [
        "    ╱────╲    ",
        "  ╱        ╲  ",
        "╱   ♥♥♥♥♥♥   ╲",
        "│   ♥♥♥♥♥♥   │",
        "╲            ╱",
        "  ╲        ╱  ",
        "    ╲────╱    ",
    ],
    # 3: end-diastole
    [
        "   ╱──────╲   ",
        " ╱          ╲ ",
        "╱  ♥♥♥♥♥♥♥♥  ╲",
        "│  ♥♥♥♥♥♥♥♥  │",
        "╲            ╱",
        " ╲          ╱ ",
        "   ╲──────╱   ",
    ],
]

CYCLE = [0, 1, 2, 3, 3, 2, 1, 0]


# ── Colormap (thermal style) ─────────────────────────────────

def _thermal_color(frac: float) -> str:
    """Map 0..1 to a thermal colormap hex color."""
    # blue → cyan → green → yellow → red
    if frac < 0.25:
        r, g, b = 30, 30, int(100 + 155 * frac * 4)
    elif frac < 0.5:
        t = (frac - 0.25) * 4
        r, g, b = 30, int(30 + 170 * t), int(255 - 55 * t)
    elif frac < 0.75:
        t = (frac - 0.5) * 4
        r, g, b = int(30 + 225 * t), int(200 + 55 * t), int(200 - 160 * t)
    else:
        t = (frac - 0.75) * 4
        r, g, b = 255, int(255 - 155 * t), int(40 - 20 * t)
    return f"#{r:02x}{g:02x}{b:02x}"


def _vital_color(value: float, lo: float, hi: float, crit_lo: float, crit_hi: float) -> str:
    """Map a vital sign value to a color."""
    if value < crit_lo or value > crit_hi:
        return "#ff3030"  # red
    elif value < lo or value > hi:
        return "#ffb020"  # amber
    else:
        return "#40c060"  # green


# ── Widgets ───────────────────────────────────────────────────

class HeartWidget(Static):
    """Animated heart driven by simulation parameters."""

    frame_idx = reactive(0)

    def __init__(self, creature: Any, **kwargs):
        super().__init__(**kwargs)
        self._creature = creature
        self._cycle_pos = 0

    def on_mount(self) -> None:
        hr = getattr(self._creature.heart, "heart_rate", 80)
        beat_interval = 60.0 / max(hr, 1) / len(CYCLE)
        self.set_interval(beat_interval, self._advance)

    def _advance(self) -> None:
        self._cycle_pos = (self._cycle_pos + 1) % len(CYCLE)
        self.frame_idx = CYCLE[self._cycle_pos]

    def render(self) -> str:
        frame = HEART_FRAMES[self.frame_idx]
        hr = getattr(self._creature.heart, "heart_rate", 80)
        contractility = getattr(self._creature.heart, "contractility_factor", 1.0)

        # Color intensity based on contractility
        intensity = min(1.0, contractility)
        color = _thermal_color(intensity)

        lines = []
        for row in frame:
            lines.append(f"[{color}]{row}[/]")
        return "\n".join(lines)


class VitalWidget(Static):
    """Single vital sign with color-coded value."""

    def __init__(self, label: str, unit: str, creature: Any,
                 getter: str, lo: float, hi: float, crit_lo: float, crit_hi: float,
                 multiplier: float = 1.0, **kwargs):
        super().__init__(**kwargs)
        self._label = label
        self._unit = unit
        self._creature = creature
        self._getter = getter
        self._lo = lo
        self._hi = hi
        self._crit_lo = crit_lo
        self._crit_hi = crit_hi
        self._multiplier = multiplier

    def on_mount(self) -> None:
        self.set_interval(0.25, self.refresh)

    def render(self) -> str:
        try:
            parts = self._getter.split(".")
            obj = self._creature
            for p in parts:
                obj = getattr(obj, p)
            value = float(obj) * self._multiplier
        except (AttributeError, TypeError):
            value = 0.0

        color = _vital_color(value, self._lo, self._hi, self._crit_lo, self._crit_hi)
        return f"[bold]{self._label:>5}[/] [{color}]{value:6.1f}[/] {self._unit}"


class OrgansWidget(Static):
    """Organ status grid."""

    def __init__(self, creature: Any, **kwargs):
        super().__init__(**kwargs)
        self._creature = creature

    def on_mount(self) -> None:
        self.set_interval(0.5, self.refresh)

    def render(self) -> str:
        organs = []
        for name in ("heart", "lung", "kidney", "brain", "liver"):
            mod = getattr(self._creature, name, None)
            if mod is None:
                continue
            health = getattr(mod, "health", None) or getattr(mod, "organ_health", 1.0)
            health = float(health) if health else 1.0

            if health >= 0.8:
                icon, color = "●", "#40c060"
            elif health >= 0.4:
                icon, color = "◐", "#ffb020"
            elif health > 0:
                icon, color = "○", "#ff8030"
            else:
                icon, color = "✗", "#ff3030"

            organs.append(f"[{color}]{icon}[/] {name:>8}")

        # 2-column layout
        lines = []
        for i in range(0, len(organs), 2):
            left = organs[i]
            right = organs[i + 1] if i + 1 < len(organs) else ""
            lines.append(f"  {left}   {right}")
        return "\n".join(lines)


class SignsWidget(Static):
    """Active clinical signs list."""

    def __init__(self, creature: Any, **kwargs):
        super().__init__(**kwargs)
        self._creature = creature

    def on_mount(self) -> None:
        self.set_interval(0.5, self.refresh)

    def render(self) -> str:
        engine = getattr(self._creature, "clinical_signs_engine", None)
        if engine is None:
            return "  [dim](no signs engine)[/]"

        active = engine.get_active_signs()
        if not active:
            return "  [dim](none)[/]"

        sev_colors = {"mild": "#40c060", "moderate": "#ffb020", "severe": "#ff3030"}
        lines = []
        for s in active[:6]:
            sev = s.severity[0].upper() if s.severity else "?"
            color = sev_colors.get(s.severity, "#ffffff")
            lines.append(f"  [{color}][{sev}][/] {s.display_name}")
        if len(active) > 6:
            lines.append(f"  [dim]... +{len(active) - 6} more[/]")
        return "\n".join(lines)


class TrendWidget(Static):
    """Sparkline trend for a vital sign history."""

    def __init__(self, creature: Any, history_key: str, label: str, **kwargs):
        super().__init__(**kwargs)
        self._creature = creature
        self._key = history_key
        self._label = label

    def on_mount(self) -> None:
        self.set_interval(0.5, self.refresh)

    def render(self) -> str:
        hist = getattr(self._creature, "history", None)
        if hist is None:
            return f"  {self._label}: [dim]--[/]"

        vals = hist.get(self._key, [])
        if not vals or len(vals) < 2:
            return f"  {self._label}: [dim]--[/]"

        recent = list(vals)[-40:]
        lo, hi = min(recent), max(recent)
        rng = hi - lo if hi > lo else 1

        spark_chars = "▁▂▃▄▅▆▇█"
        chars = []
        for v in recent:
            idx = int((v - lo) / rng * (len(spark_chars) - 1))
            frac = (v - lo) / rng
            color = _thermal_color(frac)
            chars.append(f"[{color}]{spark_chars[idx]}[/]")

        return f"  {self._label}: {''.join(chars)}"


# ── Main App ──────────────────────────────────────────────────

class PatientMonitor(App):
    """Real-time patient monitor with animated heart and vital signs."""

    CSS = """
    Screen {
        background: #0a0e14;
    }

    #header {
        height: 1;
        background: #1a2030;
        color: #6090c0;
        content-align: center middle;
    }

    #main {
        height: 1fr;
    }

    #heart-panel {
        width: 20;
        height: 1fr;
        border: solid #304060;
        content-align: center middle;
    }

    #vitals-panel {
        width: 1fr;
        height: 1fr;
        border: solid #304060;
    }

    #trends-panel {
        height: 8;
        border: solid #304060;
    }

    #organs-panel {
        width: 25;
        height: 1fr;
        border: solid #304060;
    }

    #signs-panel {
        width: 1fr;
        height: 1fr;
        border: solid #304060;
    }

    .vital-row {
        height: 1;
    }

    #footer-bar {
        height: 1;
        background: #1a2030;
        color: #6090c0;
        content-align: center middle;
    }
    """

    def __init__(self, creature: Any, disease_name: str, **kwargs):
        super().__init__(**kwargs)
        self._creature = creature
        self._disease = disease_name

    def compose(self) -> ComposeResult:
        c = self._creature

        yield Label("VIRTUAL VET ─ Patient Monitor", id="header")

        with Horizontal(id="main"):
            # Left: Heart animation
            yield HeartWidget(c, id="heart-panel")

            with Vertical():
                # Vital signs
                with Vertical(id="vitals-panel"):
                    yield VitalWidget("  HR", "bpm", c, "heart.heart_rate", 60, 140, 40, 180, classes="vital-row")
                    yield VitalWidget(" MAP", "mmHg", c, "heart.mean_arterial_pressure", 70, 120, 50, 160, classes="vital-row")
                    yield VitalWidget("SpO2", "%", c, "blood.arterial_saturation", 95, 100, 80, 100, multiplier=100, classes="vital-row")
                    yield VitalWidget("Temp", "°C", c, "blood.core_temperature_C", 37.5, 39.5, 36, 40.5, classes="vital-row")
                    yield VitalWidget("  RR", "br/m", c, "lung.respiratory_rate", 10, 30, 5, 50, classes="vital-row")

                # Trends
                with Vertical(id="trends-panel"):
                    yield TrendWidget(c, "HR_bpm", "HR trend")
                    yield TrendWidget(c, "MAP_mmHg", "MAP trend")

            # Right: Organs + Signs
            with Vertical():
                yield Label("[bold]ORGANS[/]", id="organs-title")
                yield OrgansWidget(c, id="organs-panel")

                yield Label("[bold]ACTIVE SIGNS[/]", id="signs-title")
                yield SignsWidget(c, id="signs-panel")

        yield Label(f"  Disease: [yellow]{self._disease}[/]  |  Q=quit  Space=pause  R=reset", id="footer-bar")

    def on_ready(self) -> None:
        self.set_interval(1.0, self._update_time)

    def _update_time(self) -> None:
        t = self._creature.current_time_s
        footer = self.query_one("#footer-bar")
        footer.update(f"  Disease: [yellow]{self._disease}[/]  |  Time: {t/60:.0f}h {(t%3600)/60:.0f}m  |  Q=quit  Space=pause")


# ── CLI ───────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(prog="textual-monitor", description="Interactive patient monitor")
    parser.add_argument("--disease", default="pneumonia")
    parser.add_argument("--severity", default="moderate")
    parser.add_argument("--steps", type=int, default=0, help="Pre-simulate N steps before launching")
    args = parser.parse_args()

    from src.simulation import VirtualCreature
    from src.diseases import create_disease

    disease = _resolve_disease(args.disease)
    c = VirtualCreature(body_weight_kg=20.0, record_history=True)
    d = create_disease(disease, severity=args.severity)
    c.attach_disease(d)

    # Pre-simulate if requested
    if args.steps > 0:
        for _ in range(args.steps):
            c.step()

    app = PatientMonitor(c, disease)
    app.run()


if __name__ == "__main__":
    main()
