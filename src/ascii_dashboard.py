"""
ASCII Dashboard — Real-time terminal visualization of VirtualCreature state.

Techniques from life-simulator:
  - TrueColorBuffer for 24-bit ANSI rendering (no curses dependency)
  - Perceptually uniform colormaps (thermal, ocean, viridis)
  - Smooth gradient gauges with color interpolation
  - Heatmap sparklines for vital sign trends

Usage:
    uv run python src/ascii_dashboard.py             # Interactive mode
    uv run python src/ascii_dashboard.py --once      # Single snapshot (pipe-friendly)
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from typing import Any

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

try:
    import curses
    HAS_CURSES = True
except ImportError:
    HAS_CURSES = False


# ── TrueColor support (from life-simulator) ───────────────────

_TRUECOLOR = None

def truecolor_available() -> bool:
    global _TRUECOLOR
    if _TRUECOLOR is None:
        ct = os.environ.get("COLORTERM", "")
        wt = os.environ.get("WT_SESSION", "")      # Windows Terminal
        _TRUECOLOR = ct in ("truecolor", "24bit") or bool(wt)
    return _TRUECOLOR


def _lerp_color(c0: tuple[int, ...], c1: tuple[int, ...], t: float) -> tuple[int, int, int]:
    return (int(c0[0] + (c1[0] - c0[0]) * t),
            int(c0[1] + (c1[1] - c0[1]) * t),
            int(c0[2] + (c1[2] - c0[2]) * t))


def _build_colormap(pts: list[tuple[float, int, int, int]]) -> list[tuple[int, int, int]]:
    cmap = [(0, 0, 0)] * 256
    for i in range(256):
        t = i / 255.0
        lo, hi = pts[0], pts[-1]
        for j in range(len(pts) - 1):
            if pts[j][0] <= t <= pts[j + 1][0]:
                lo, hi = pts[j], pts[j + 1]
                break
        seg = hi[0] - lo[0]
        st = (t - lo[0]) / seg if seg > 0 else 0.0
        cmap[i] = _lerp_color(lo[1:], hi[1:], st)
    return cmap


# Medical colormaps
_THERMAL_PTS = [
    (0.00, 10, 10, 60), (0.14, 30, 20, 120), (0.28, 80, 15, 150),
    (0.42, 160, 30, 100), (0.57, 210, 50, 50), (0.71, 240, 120, 20),
    (0.85, 255, 200, 50), (1.00, 255, 255, 220),
]
_OCEAN_PTS = [
    (0.00, 3, 4, 30), (0.25, 15, 42, 110), (0.50, 30, 130, 170),
    (0.75, 80, 200, 200), (1.00, 200, 245, 240),
]
_VITAL_PTS = [
    (0.00, 200, 30, 30),   # red (danger low)
    (0.30, 255, 180, 30),  # amber (warning)
    (0.50, 40, 200, 80),   # green (normal)
    (0.70, 255, 180, 30),  # amber (warning)
    (1.00, 200, 30, 30),   # red (danger high)
]
_SEPSIS_PTS = [
    (0.00, 40, 200, 80),   # green (healthy)
    (0.30, 255, 220, 50),  # yellow
    (0.60, 255, 120, 30),  # orange
    (1.00, 200, 30, 30),   # red (critical)
]

COLORMAPS = {
    "thermal": _build_colormap(_THERMAL_PTS),
    "ocean":   _build_colormap(_OCEAN_PTS),
    "vital":   _build_colormap(_VITAL_PTS),
    "sepsis":  _build_colormap(_SEPSIS_PTS),
}


def colormap_rgb(name: str, frac: float) -> tuple[int, int, int]:
    cmap = COLORMAPS.get(name, COLORMAPS["vital"])
    idx = max(0, min(255, int(frac * 255)))
    return cmap[idx]


# ── ANSI helpers ──────────────────────────────────────────────

def _ansi_fg(r: int, g: int, b: int) -> str:
    return f"\033[38;2;{r};{g};{b}m"

def _ansi_bg(r: int, g: int, b: int) -> str:
    return f"\033[48;2;{r};{g};{b}m"

RESET = "\033[0m"
BOLD  = "\033[1m"
DIM   = "\033[2m"


# ── Gauge config ──────────────────────────────────────────────

@dataclass(frozen=True)
class GaugeSpec:
    label: str
    unit: str
    lo: float
    hi: float
    normal_lo: float
    normal_hi: float
    colormap: str = "vital"


VITAL_GAUGES = {
    "HR":   GaugeSpec("HR",   "bpm",    0, 300,  60, 140, "vital"),
    "MAP":  GaugeSpec("MAP",  "mmHg",   0, 200,  70, 120, "vital"),
    "SpO2": GaugeSpec("SpO2", "%",      0, 100,  95, 100, "ocean"),
    "Temp": GaugeSpec("Temp", "°C",    30,  43, 37.5, 39.5, "thermal"),
    "RR":   GaugeSpec("RR",   "br/m",   0,  80,  10,  30, "vital"),
    "Glu":  GaugeSpec("Glu",  "mg/dL",  0, 600,  65, 150, "vital"),
}

SPARK_CHARS = "▁▂▃▄▅▆▇█"

ORGAN_OK   = "●"
ORGAN_WARN = "◐"
ORGAN_CRIT = "○"
ORGAN_DEAD = "✗"


# ── Rendering ─────────────────────────────────────────────────

def _vital_fraction(spec: GaugeSpec, value: float) -> float:
    """Map value to 0..1 where 0.5 = center of normal range."""
    mid = (spec.normal_lo + spec.normal_hi) / 2
    if value < mid:
        return 0.5 * (value - spec.lo) / (mid - spec.lo) if mid > spec.lo else 0
    else:
        return 0.5 + 0.5 * (value - mid) / (spec.hi - mid) if spec.hi > mid else 1


def render_gauge(spec: GaugeSpec, value: float | None, width: int = 30,
                 use_color: bool = True) -> str:
    if value is None:
        bar = "─" * width
        return f"{spec.label:>5} [{bar}] ── {spec.unit}"

    frac = _vital_fraction(spec, value)
    frac = max(0.0, min(1.0, frac))
    fill_n = int(frac * width)

    # Gradient bar: each segment gets its own color from the colormap
    bar_chars = []
    if use_color and truecolor_available():
        for i in range(width):
            if i < fill_n:
                seg_frac = i / max(1, width - 1)
                r, g, b = colormap_rgb(spec.colormap, seg_frac)
                bar_chars.append(f"{_ansi_fg(r,g,b)}█{RESET}")
            else:
                bar_chars.append("░")
        bar = "".join(bar_chars)
    else:
        # Fallback: single character based on severity
        if value < spec.normal_lo * 0.8 or value > spec.normal_hi * 1.2:
            ch = "▒"
        elif value < spec.normal_lo or value > spec.normal_hi:
            ch = "▓"
        else:
            ch = "█"
        bar = ch * fill_n + "░" * (width - fill_n)

    # Warning tag
    if value < spec.normal_lo * 0.8 or value > spec.normal_hi * 1.2:
        tag = f"{_ansi_fg(200,30,30)} !!!{RESET}"
    elif value < spec.normal_lo or value > spec.normal_hi:
        tag = f"{_ansi_fg(255,180,30)} !{RESET}"
    else:
        tag = ""

    return f"{spec.label:>5} [{bar}] {value:6.1f} {spec.unit}{tag}"


def render_sparkline(values: list[float], width: int = 20,
                     colormap: str = "vital", use_color: bool = True) -> str:
    if not values:
        return "─" * width
    recent = list(values[-width:])
    lo, hi = min(recent), max(recent)
    rng = hi - lo if hi > lo else 1

    chars = []
    for v in recent:
        idx = int((v - lo) / rng * (len(SPARK_CHARS) - 1))
        ch = SPARK_CHARS[idx]
        if use_color and truecolor_available():
            frac = (v - lo) / rng
            r, g, b = colormap_rgb(colormap, frac)
            chars.append(f"{_ansi_fg(r,g,b)}{ch}{RESET}")
        else:
            chars.append(ch)
    return "".join(chars)


def render_heatmap_row(values: list[float], width: int = 40,
                       colormap: str = "sepsis") -> str:
    """Render values as a heatmap strip (one char per time slice)."""
    if not values:
        return "─" * width
    recent = list(values[-width:])
    lo, hi = min(recent), max(recent)
    rng = hi - lo if hi > lo else 1

    chars = []
    for v in recent:
        frac = (v - lo) / rng
        if truecolor_available():
            r, g, b = colormap_rgb(colormap, frac)
            chars.append(f"{_ansi_bg(r,g,b)} {RESET}")
        else:
            idx = int(frac * (len(SPARK_CHARS) - 1))
            chars.append(SPARK_CHARS[idx])
    return "".join(chars)


def organ_icon(health: float) -> str:
    if health >= 0.8:
        return ORGAN_OK
    elif health >= 0.4:
        return ORGAN_WARN
    elif health > 0:
        return ORGAN_CRIT
    return ORGAN_DEAD


def organ_color(health: float) -> tuple[int, int, int]:
    if health >= 0.8:
        return (40, 200, 80)
    elif health >= 0.4:
        return (255, 200, 40)
    elif health > 0:
        return (255, 100, 30)
    return (200, 30, 30)


def render_organ_panel(creature: Any, use_color: bool = True) -> list[str]:
    organs = {}
    for name in ("heart", "lung", "kidney", "brain", "liver"):
        mod = getattr(creature, name, None)
        if mod is None:
            continue
        health = getattr(mod, "health", None)
        if health is None:
            health = getattr(mod, "organ_health", 1.0)
        organs[name] = float(health) if health else 1.0

    lines = []
    items = list(organs.items())
    for i in range(0, len(items), 2):
        h1 = items[i][1]
        icon1 = organ_icon(h1)
        left = f" {icon1} {items[i][0]:>8}"
        if use_color and truecolor_available():
            r, g, b = organ_color(h1)
            left = f" {_ansi_fg(r,g,b)}{icon1}{RESET} {items[i][0]:>8}"

        right = ""
        if i + 1 < len(items):
            h2 = items[i + 1][1]
            icon2 = organ_icon(h2)
            if use_color and truecolor_available():
                r, g, b = organ_color(h2)
                right = f"   {_ansi_fg(r,g,b)}{icon2}{RESET} {items[i+1][0]:>8}"
            else:
                right = f"   {icon2} {items[i+1][0]:>8}"
        lines.append(left + right)
    return lines


def render_signs(creature: Any, max_lines: int = 6) -> list[str]:
    signs_engine = getattr(creature, "clinical_signs_engine", None)
    if signs_engine is None:
        signs_engine = getattr(creature, "_clinical_signs", None)
    if signs_engine is None:
        return [" (no signs engine)"]

    active = signs_engine.get_active_signs()
    if not active:
        return [" (none)"]

    sev_colors = {
        "mild":     (40, 200, 80),
        "moderate": (255, 200, 40),
        "severe":   (200, 30, 30),
    }

    lines = []
    for s in active[:max_lines]:
        sev = s.severity[0].upper() if s.severity else "?"
        if truecolor_available():
            r, g, b = sev_colors.get(s.severity, (200, 200, 200))
            lines.append(f" [{_ansi_fg(r,g,b)}{sev}{RESET}] {s.display_name}")
        else:
            lines.append(f" [{sev}] {s.display_name}")
    if len(active) > max_lines:
        lines.append(f" ... +{len(active) - max_lines} more")
    return lines


# ── Full dashboard ────────────────────────────────────────────

def build_dashboard(creature: Any, width: int = 78, use_color: bool = True) -> list[str]:
    lines = []
    tc = use_color and truecolor_available()
    sep = "─" * width

    # Header
    if tc:
        lines.append(f"{_ansi_fg(80,180,255)}{_ansi_bg(15,20,30)}{'VIRTUAL VET':^{width}}{RESET}")
    else:
        lines.append(sep)
        lines.append("  VIRTUAL VET  ─  Patient Monitor")
    lines.append(sep)

    # Vital signs
    state: dict[str, float | None] = {}
    try:
        state["HR"] = creature.heart.heart_rate
        state["MAP"] = creature.heart.mean_arterial_pressure
        lung = getattr(creature, "lung", None)
        if lung:
            state["RR"] = getattr(lung, "respiratory_rate", None)
            po2 = getattr(creature.blood, "arterial_PO2_mmHg", None)
            if po2 is not None:
                # Hill equation: SO2 = PO2^n / (P50^n + PO2^n), n=2.7, P50=26.6
                state["SpO2"] = 100 * po2**2.7 / (26.6**2.7 + po2**2.7) if po2 > 0 else 0
        blood = getattr(creature, "blood", None)
        if blood:
            state["Temp"] = getattr(blood, "core_temperature_C", None)
            glu = getattr(blood, "glucose_mmol_L", None)
            if glu is not None:
                state["Glu"] = glu * 18.018
    except Exception:
        pass

    gauge_w = max(20, width - 28)
    for key, spec in VITAL_GAUGES.items():
        lines.append(render_gauge(spec, state.get(key), gauge_w, tc))

    lines.append(sep)

    # Sparklines + heatmap
    history = getattr(creature, "history", None)
    if history:
        spark_w = min(30, width - 20)
        for key, hist_key, cmap in [("HR", "HR_bpm", "vital"), ("MAP", "MAP_mmHg", "thermal")]:
            vals = history.get(hist_key, [])
            if vals:
                spark = render_sparkline(list(vals), spark_w, cmap, tc)
                lines.append(f"  {key:>5} trend [{spark}]")

        # Heatmap row for HR history density
        hr_vals = history.get("HR_bpm", [])
        if hr_vals and len(hr_vals) > 10:
            heat = render_heatmap_row(list(hr_vals), min(40, width - 14), "sepsis")
            lines.append(f"  {'heat':>5} [{heat}]")

        lines.append(sep)

    # Organs
    lines.append("  ORGANS")
    lines.extend(render_organ_panel(creature, tc))
    lines.append(sep)

    # Signs
    lines.append("  ACTIVE SIGNS")
    lines.extend(render_signs(creature, max_lines=6))
    lines.append(sep)

    # Disease
    disease = getattr(creature, "disease", None)
    if disease:
        name = getattr(disease, "name", type(disease).__name__)
        if tc:
            lines.append(f"  DISEASE: {_ansi_fg(255,180,40)}{name}{RESET}")
        else:
            lines.append(f"  DISEASE: {name}")
    else:
        lines.append("  DISEASE: (none)")

    # Time
    t = getattr(creature, "current_time_s", 0)
    lines.append(f"  TIME: {t/3600:.0f}h {(t%3600)/60:.0f}m {t%60:.0f}s")
    lines.append(sep)

    return lines


# ── Interactive mode (curses) ─────────────────────────────────

def _curses_main(stdscr: Any, creature_fn: Any, fps: float = 4) -> None:
    curses.curs_set(0)
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_WHITE, -1)
    curses.init_pair(2, curses.COLOR_YELLOW, -1)
    curses.init_pair(3, curses.COLOR_RED, -1)
    curses.init_pair(4, curses.COLOR_GREEN, -1)

    creature = creature_fn()
    paused = False
    speed = 1

    while True:
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

        if not paused:
            for _ in range(speed):
                creature.step()

        h, w = stdscr.getmaxyx()
        # Use no-color for curses (it has its own color system)
        lines = build_dashboard(creature, width=w - 2, use_color=False)

        stdscr.erase()
        for i, line in enumerate(lines):
            if i >= h - 1:
                break
            color = 1
            if "!!!" in line:
                color = 3
            elif " !" in line:
                color = 2
            elif ORGAN_OK in line:
                color = 4
            try:
                stdscr.addstr(i, 0, line[:w-1], curses.color_pair(color))
            except curses.error:
                pass

        status = f" {'PAUSED' if paused else 'RUNNING'} | speed={speed}x | Q=quit Space=pause +/-=speed R=reset"
        try:
            stdscr.addstr(h-1, 0, status[:w-1], curses.color_pair(2) | curses.A_REVERSE)
        except curses.error:
            pass

        stdscr.refresh()
        time.sleep(1.0 / fps)


def run_interactive(disease_name: str = "pneumonia", severity: str = "moderate") -> None:
    if not HAS_CURSES:
        print("curses not available. Use --once for snapshot mode.", file=sys.stderr)
        sys.exit(1)

    from src.simulation import VirtualCreature
    from src.diseases import create_disease

    def make_creature():
        c = VirtualCreature(body_weight_kg=20.0, record_history=True)
        d = create_disease(disease_name, severity=severity)
        c.attach_disease(d)
        return c

    curses.wrapper(lambda stdscr: _curses_main(stdscr, make_creature))


# ── Snapshot ──────────────────────────────────────────────────

def snapshot(disease_name: str = "pneumonia", severity: str = "moderate",
             steps: int = 600, use_color: bool = True) -> str:
    from src.simulation import VirtualCreature
    from src.diseases import create_disease

    c = VirtualCreature(body_weight_kg=20.0, record_history=True)
    d = create_disease(disease_name, severity=severity)
    c.attach_disease(d)

    for _ in range(steps):
        c.step()

    lines = build_dashboard(c, use_color=use_color)
    return "\n".join(lines)


# ── CLI entry point ───────────────────────────────────────────

def main():
    # Ensure project root is on sys.path (needed when installed as console_scripts)
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _root not in sys.path:
        sys.path.insert(0, _root)

    import argparse
    parser = argparse.ArgumentParser(prog="vet-monitor", description="Virtual Vet ASCII patient monitor")
    parser.add_argument("--once", action="store_true", help="Single snapshot (pipe-friendly)")
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI colors")
    parser.add_argument("--disease", default="pneumonia", help="Disease name (pneumonia, dka, ckd, etc.)")
    parser.add_argument("--severity", default="moderate", help="mild/moderate/severe")
    parser.add_argument("--steps", type=int, default=600, help="Simulation steps before snapshot")
    args = parser.parse_args()

    if args.once:
        print(snapshot(args.disease, args.severity, args.steps, not args.no_color))
    else:
        run_interactive(args.disease, args.severity)


if __name__ == "__main__":
    main()
