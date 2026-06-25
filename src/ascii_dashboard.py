"""
ASCII Dashboard — Real-time terminal visualization of VirtualCreature state.

Inspired by likwid's curses-based rendering. Shows:
  - Vital signs as bar gauges (HR, MAP, SpO2, Temp, RR)
  - Organ status indicators (heart, lung, kidney, brain)
  - Disease progression sparklines
  - Active clinical signs

Usage:
    uv run python src/ascii_dashboard.py             # Interactive curses mode
    uv run python src/ascii_dashboard.py --once      # Single snapshot (pipe-friendly)
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from typing import Any

# Ensure project root is on sys.path for imports
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

try:
    import curses
    HAS_CURSES = True
except ImportError:
    HAS_CURSES = False

# ── Gauge config ──────────────────────────────────────────────

@dataclass(frozen=True)
class GaugeSpec:
    label: str
    unit: str
    lo: float       # gauge min
    hi: float       # gauge max
    warn_lo: float  # yellow below
    warn_hi: float  # yellow above
    crit_lo: float  # red below
    crit_hi: float  # red above


VITAL_GAUGES = {
    "HR":   GaugeSpec("HR",   "bpm",  0, 300, 60, 140, 40, 180),
    "MAP":  GaugeSpec("MAP",  "mmHg", 0, 200, 70, 120, 50, 160),
    "SpO2": GaugeSpec("SpO2", "%",    0, 100, 90, 100, 80, 100),
    "Temp": GaugeSpec("Temp", "°C",  30,  43, 37.5, 39.5, 36.0, 40.5),
    "RR":   GaugeSpec("RR",   "br/m", 0,  80, 10,  30,  5,  50),
    "Glu":  GaugeSpec("Glu",  "mg/dL",0, 600, 65, 150, 40, 300),
}

# ASCII bar characters (likwid-style density ramp)
BAR_EMPTY = "░"
BAR_FILL  = "█"
BAR_WARN  = "▓"
BAR_CRIT  = "▒"

# Sparkline characters for time-series
SPARK_CHARS = "▁▂▃▄▅▆▇█"

# Organ status icons
ORGAN_OK    = "●"
ORGAN_WARN  = "◐"
ORGAN_CRIT  = "○"
ORGAN_DEAD  = "✗"


# ── Gauge rendering ──────────────────────────────────────────

def render_gauge(spec: GaugeSpec, value: float | None, width: int = 30) -> str:
    """Render a single vital sign as an ASCII bar gauge."""
    if value is None:
        bar = "─" * width
        return f"{spec.label:>5} [{bar}] ── {spec.unit}"

    # Normalize to 0..1
    clamped = max(spec.lo, min(spec.hi, value))
    frac = (clamped - spec.lo) / (spec.hi - spec.lo) if spec.hi > spec.lo else 0
    fill_n = int(frac * width)

    # Pick color class
    if value < spec.crit_lo or value > spec.crit_hi:
        ch = BAR_CRIT
        tag = " !!!"
    elif value < spec.warn_lo or value > spec.warn_hi:
        ch = BAR_WARN
        tag = " !"
    else:
        ch = BAR_FILL
        tag = ""

    bar = ch * fill_n + BAR_EMPTY * (width - fill_n)
    return f"{spec.label:>5} [{bar}] {value:6.1f} {spec.unit}{tag}"


def render_sparkline(values: list[float], width: int = 20) -> str:
    """Render a list of values as a sparkline string."""
    if not values:
        return "─" * width
    recent = values[-width:]
    lo = min(recent)
    hi = max(recent)
    rng = hi - lo if hi > lo else 1
    chars = []
    for v in recent:
        idx = int((v - lo) / rng * (len(SPARK_CHARS) - 1))
        chars.append(SPARK_CHARS[idx])
    return "".join(chars)


# ── Organ status ─────────────────────────────────────────────

def organ_icon(health: float) -> str:
    """Map organ health (0..1) to status icon."""
    if health >= 0.8:
        return ORGAN_OK
    elif health >= 0.4:
        return ORGAN_WARN
    elif health > 0:
        return ORGAN_CRIT
    return ORGAN_DEAD


def render_organ_panel(creature: Any) -> list[str]:
    """Render organ status as a compact grid."""
    organs = {}
    for name in ("heart", "lung", "kidney", "brain", "liver"):
        mod = getattr(creature, name, None)
        if mod is None:
            continue
        health = getattr(mod, "health", None)
        if health is None:
            health = getattr(mod, "organ_health", 1.0)
        organs[name] = organ_icon(float(health) if health else 1.0)

    # 2-column layout
    lines = []
    items = list(organs.items())
    for i in range(0, len(items), 2):
        left = f" {items[i][1]} {items[i][0]:>8}"
        right = ""
        if i + 1 < len(items):
            right = f"   {items[i+1][1]} {items[i+1][0]:>8}"
        lines.append(left + right)
    return lines


# ── Clinical signs ────────────────────────────────────────────

def render_signs(creature: Any, max_lines: int = 6) -> list[str]:
    """Render active clinical signs as a compact list."""
    signs_engine = getattr(creature, "clinical_signs_engine", None)
    if signs_engine is None:
        signs_engine = getattr(creature, "_clinical_signs", None)
    if signs_engine is None:
        return [" (no signs engine)"]

    active = signs_engine.get_active_signs()
    if not active:
        return [" (none)"]

    lines = []
    for s in active[:max_lines]:
        sev = s.severity[0].upper() if s.severity else "?"
        lines.append(f" [{sev}] {s.display_name}")
    if len(active) > max_lines:
        lines.append(f" ... +{len(active) - max_lines} more")
    return lines


# ── Full dashboard ────────────────────────────────────────────

def build_dashboard(creature: Any, width: int = 78) -> list[str]:
    """Build complete dashboard lines for a VirtualCreature."""
    lines = []
    sep = "─" * width

    # Header
    lines.append(sep)
    lines.append("  VIRTUAL VET  ─  Patient Monitor")
    lines.append(sep)

    # Vital signs gauges
    state = {}
    try:
        state["HR"] = creature.heart.heart_rate
        state["MAP"] = creature.heart.mean_arterial_pressure

        # Respiratory rate from lung
        lung = getattr(creature, "lung", None)
        if lung:
            state["RR"] = getattr(lung, "respiratory_rate", None)
            # SpO2 estimate from arterial PO2 (simplified dissociation curve)
            po2 = getattr(creature.blood, "arterial_PO2_mmHg", None)
            if po2 is not None:
                state["SpO2"] = max(0, min(100, (po2 - 40) / 20 * 50 + 50)) if po2 > 40 else po2

        # Core temperature from blood
        blood = getattr(creature, "blood", None)
        if blood:
            state["Temp"] = getattr(blood, "core_temperature_C", None)
            glu = getattr(blood, "glucose_mmol_L", None)
            if glu is not None:
                state["Glu"] = glu * 18.018  # mmol/L → mg/dL
    except Exception:
        pass

    gauge_width = max(20, width - 28)
    for key, spec in VITAL_GAUGES.items():
        lines.append(render_gauge(spec, state.get(key), gauge_width))

    lines.append(sep)

    # Sparklines (if history available)
    history = getattr(creature, "history", None)
    if history:
        spark_w = min(30, width - 20)
        for key, hist_key in [("HR", "HR_bpm"), ("MAP", "MAP_mmHg")]:
            vals = history.get(hist_key, [])
            if vals:
                spark = render_sparkline(list(vals), spark_w)
                lines.append(f"  {key:>5} trend [{spark}]")

        lines.append(sep)

    # Organ status
    lines.append("  ORGANS")
    lines.extend(render_organ_panel(creature))
    lines.append(sep)

    # Clinical signs
    lines.append("  ACTIVE SIGNS")
    lines.extend(render_signs(creature, max_lines=6))
    lines.append(sep)

    # Disease
    disease = getattr(creature, "disease", None)
    if disease:
        name = getattr(disease, "name", type(disease).__name__)
        lines.append(f"  DISEASE: {name}")
    else:
        lines.append("  DISEASE: (none)")

    # Simulation time
    t = getattr(creature, "current_time_s", 0)
    lines.append(f"  TIME: {t/60:.0f}h {(t%3600)/60:.0f}m {t%60:.0f}s")
    lines.append(sep)

    return lines


# ── Curses interactive mode ───────────────────────────────────

def _curses_main(stdscr: Any, creature_fn: Any, fps: float = 4) -> None:
    """Main curses loop. creature_fn() returns a fresh VirtualCreature."""
    curses.curs_set(0)
    curses.start_color()
    curses.use_default_colors()

    # Simple color pairs: 1=normal, 2=warn(yellow), 3=crit(red), 4=ok(green)
    curses.init_pair(1, curses.COLOR_WHITE, -1)
    curses.init_pair(2, curses.COLOR_YELLOW, -1)
    curses.init_pair(3, curses.COLOR_RED, -1)
    curses.init_pair(4, curses.COLOR_GREEN, -1)

    creature = creature_fn()
    paused = False
    speed = 1  # steps per frame

    while True:
        # Handle input
        stdscr.nodelay(True)
        try:
            key = stdscr.getch()
        except curses.error:
            key = -1

        if key == ord("q") or key == ord("Q"):
            break
        elif key == ord(" "):
            paused = not paused
        elif key == ord("+") or key == ord("="):
            speed = min(64, speed * 2)
        elif key == ord("-"):
            speed = max(1, speed // 2)
        elif key == ord("r") or key == ord("R"):
            creature = creature_fn()

        # Step simulation
        if not paused:
            for _ in range(speed):
                creature.step()

        # Render
        h, w = stdscr.getmaxyx()
        lines = build_dashboard(creature, width=w - 2)

        stdscr.erase()
        for i, line in enumerate(lines):
            if i >= h - 1:
                break
            # Color based on content
            color = 1
            if "!!!" in line:
                color = 3
            elif "!" in line:
                color = 2
            elif ORGAN_OK in line:
                color = 4

            try:
                stdscr.addstr(i, 0, line[:w-1], curses.color_pair(color))
            except curses.error:
                pass

        # Status bar
        status = f" {'PAUSED' if paused else 'RUNNING'} | speed={speed}x | Q=quit Space=pause +/-=speed R=reset"
        try:
            stdscr.addstr(h-1, 0, status[:w-1], curses.color_pair(2) | curses.A_REVERSE)
        except curses.error:
            pass

        stdscr.refresh()
        time.sleep(1.0 / fps)


def run_interactive(disease_name: str = "pneumonia", severity: str = "moderate") -> None:
    """Launch interactive curses dashboard."""
    if not HAS_CURSES:
        print("curses not available on this platform. Use --once for snapshot mode.", file=sys.stderr)
        sys.exit(1)

    from src.simulation import VirtualCreature
    from src.diseases import create_disease

    def make_creature():
        c = VirtualCreature(body_weight_kg=20.0, record_history=True)
        d = create_disease(disease_name, severity=severity)
        c.attach_disease(d)
        return c

    curses.wrapper(lambda stdscr: _curses_main(stdscr, make_creature))


# ── One-shot snapshot ─────────────────────────────────────────

def snapshot(disease_name: str = "pneumonia", severity: str = "moderate",
             steps: int = 600) -> str:
    """Run N steps and return dashboard as a string."""
    from src.simulation import VirtualCreature
    from src.diseases import create_disease

    c = VirtualCreature(body_weight_kg=20.0, record_history=True)
    d = create_disease(disease_name, severity=severity)
    c.attach_disease(d)

    for _ in range(steps):
        c.step()

    lines = build_dashboard(c)
    return "\n".join(lines)


# ── CLI entry point ───────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Virtual Vet ASCII Dashboard")
    parser.add_argument("--once", action="store_true", help="Single snapshot mode")
    parser.add_argument("--disease", default="pneumonia", help="Disease name")
    parser.add_argument("--severity", default="moderate", help="Severity: mild/moderate/severe")
    parser.add_argument("--steps", type=int, default=600, help="Simulation steps before snapshot")
    args = parser.parse_args()

    if args.once:
        print(snapshot(args.disease, args.severity, args.steps))
    else:
        run_interactive(args.disease, args.severity)
