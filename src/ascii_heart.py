"""
ASCII Heart Animation — Beats in sync with VirtualCreature physiology.

Drives animation from simulation parameters:
  - HR → beat frequency
  - SV → size swing amplitude
  - contractility → color intensity
  - MAP → border style (dashed when hypotensive)

Usage:
    uv run python src/ascii_heart.py --once
    uv run python src/ascii_heart.py --disease dka --steps 3000
"""

from __future__ import annotations

import os
import sys
import time
from typing import Any

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

try:
    import curses
    HAS_CURSES = True
except ImportError:
    HAS_CURSES = False

# ── ANSI helpers ──────────────────────────────────────────────

def _truecolor() -> bool:
    ct = os.environ.get("COLORTERM", "")
    wt = os.environ.get("WT_SESSION", "")
    return ct in ("truecolor", "24bit") or bool(wt)

TC = _truecolor()

def _fg(r: int, g: int, b: int) -> str:
    return f"\033[38;2;{r};{g};{b}m" if TC else ""

RESET = "\033[0m" if TC else ""
BOLD = "\033[1m" if TC else ""
DIM = "\033[2m" if TC else ""


# ── Heart frames (ASCII art) ─────────────────────────────────
# 4 frames: systole (contracted) → diastole (full)
# Each frame is a list of strings, same width for smooth animation

HEART_FRAMES = [
    # Frame 0: end-systole (most contracted)
    [
        "      ╱╲      ",
        "    ╱    ╲    ",
        "  ╱   ♥♥   ╲  ",
        " │    ♥♥    │ ",
        "  ╲        ╱  ",
        "    ╲    ╱    ",
        "      ╲╱      ",
    ],
    # Frame 1: early filling
    [
        "     ╱──╲     ",
        "   ╱      ╲   ",
        " ╱   ♥♥♥♥   ╲ ",
        "│    ♥♥♥♥    │",
        " ╲          ╱ ",
        "   ╲      ╱   ",
        "     ╲──╱     ",
    ],
    # Frame 2: mid filling
    [
        "    ╱────╲    ",
        "  ╱        ╲  ",
        "╱   ♥♥♥♥♥♥   ╲",
        "│   ♥♥♥♥♥♥   │",
        "╲            ╱",
        "  ╲        ╱  ",
        "    ╲────╱    ",
    ],
    # Frame 3: end-diastole (most expanded)
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

# Frame indices for animation cycle: 0→1→2→3→2→1→0 (systole→diastole→systole)
CYCLE = [0, 1, 2, 3, 3, 2, 1, 0]


# ── Heart rate → color (red intensity) ───────────────────────

def _heart_color(hr: float, contractility: float) -> tuple[int, int, int]:
    """Map HR + contractility to RGB color."""
    # Base: red. Tachycardia → brighter. Bradycardia → dimmer.
    base_r = int(180 + min(75, hr / 2))
    base_g = int(40 + contractility * 30)
    base_b = int(40 + contractility * 20)
    return (min(255, base_r), min(255, base_g), min(255, base_b))


def _border_char(map_val: float) -> str:
    """MAP < 60 → dashed border (hypotension indicator)."""
    if map_val < 50:
        return "·"
    elif map_val < 65:
        return "~"
    return "─"


# ── Render single frame ──────────────────────────────────────

def render_heart_frame(creature: Any, frame_idx: int, width: int = 20) -> list[str]:
    """Render one heart animation frame with vital signs."""
    hr = getattr(creature.heart, "heart_rate", 80)
    sv = getattr(creature.heart, "stroke_volume", 20)
    map_val = getattr(creature.heart, "mean_arterial_pressure", 100)
    contractility = getattr(creature.heart, "contractility_factor", 1.0)

    frame = HEART_FRAMES[frame_idx]
    r, g, b = _heart_color(hr, contractility)

    lines = []
    for row in frame:
        if TC:
            colored = f"{_fg(r, g, b)}{row}{RESET}"
        else:
            colored = row
        lines.append(colored)

    return lines


# ── Dashboard layout (heart + vitals side-by-side) ───────────

def build_heart_dashboard(creature: Any, frame_idx: int, width: int = 78) -> list[str]:
    """Build heart animation + vital signs dashboard."""
    hr = getattr(creature.heart, "heart_rate", 80)
    sv = getattr(creature.heart, "stroke_volume", 20)
    map_val = getattr(creature.heart, "mean_arterial_pressure", 100)
    co = hr * sv / 1000  # L/min

    heart_lines = render_heart_frame(creature, frame_idx)

    # Vital signs (right side)
    vitals = [
        f" HR  {hr:6.1f} bpm",
        f" MAP {map_val:6.1f} mmHg",
        f" SV  {sv:6.1f} mL",
        f" CO  {co:6.2f} L/min",
    ]

    # Disease
    disease = getattr(creature, "disease", None)
    if disease:
        name = getattr(disease, "name", type(disease).__name__)
        vitals.append(f" {name}")

    # Time
    t = getattr(creature, "current_time_s", 0)
    vitals.append(f" {t/60:.0f}m {t%60:.0f}s")

    # Combine: heart (left) + vitals (right)
    lines = []
    heart_w = max(len(h) for h in heart_lines) + 2
    for i in range(max(len(heart_lines), len(vitals))):
        left = heart_lines[i] if i < len(heart_lines) else " " * heart_w
        right = vitals[i] if i < len(vitals) else ""
        # Pad left to fixed width
        left_padded = left.ljust(heart_w)
        lines.append(f"  {left_padded}  {right}")

    return lines


# ── Interactive mode ──────────────────────────────────────────

def _curses_main(stdscr: Any, creature_fn: Any) -> None:
    curses.curs_set(0)
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_RED, -1)
    curses.init_pair(2, curses.COLOR_YELLOW, -1)

    creature = creature_fn()
    cycle_idx = 0
    paused = False

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
        elif key == ord("r") or key == ord("R"):
            creature = creature_fn()

        if not paused:
            creature.step()

        # Calculate beat timing
        hr = getattr(creature.heart, "heart_rate", 80)
        beat_period = 60.0 / max(hr, 1)  # seconds per beat
        frames_per_beat = len(CYCLE)
        frame_duration = beat_period / frames_per_beat

        # Get current frame
        frame_idx = CYCLE[cycle_idx % len(CYCLE)]
        cycle_idx += 1

        # Render
        h, w = stdscr.getmaxyx()
        lines = build_heart_dashboard(creature, frame_idx, w - 2)

        stdscr.erase()
        for i, line in enumerate(lines):
            if i >= h - 1:
                break
            try:
                stdscr.addstr(i, 0, line[:w-1])
            except curses.error:
                pass

        status = f" HR={hr:.0f} | {'PAUSED' if paused else 'BEATING'} | Q=quit Space=pause R=reset"
        try:
            stdscr.addstr(h-1, 0, status[:w-1], curses.color_pair(1) | curses.A_REVERSE)
        except curses.error:
            pass

        stdscr.refresh()
        time.sleep(frame_duration)


def run_interactive(disease_name: str = "pneumonia", severity: str = "moderate") -> None:
    if not HAS_CURSES:
        print("curses not available. Use --once for snapshot.", file=sys.stderr)
        sys.exit(1)

    from src.simulation import VirtualCreature
    from src.diseases import create_disease

    def make():
        c = VirtualCreature(body_weight_kg=20.0, record_history=True)
        d = create_disease(disease_name, severity=severity)
        c.attach_disease(d)
        return c

    curses.wrapper(lambda s: _curses_main(s, make))


# ── Snapshot ──────────────────────────────────────────────────

def snapshot(disease_name: str = "pneumonia", severity: str = "moderate",
             steps: int = 600, beats: int = 3) -> str:
    """Run simulation and render N heartbeats as ASCII animation frames."""
    from src.simulation import VirtualCreature
    from src.diseases import create_disease

    c = VirtualCreature(body_weight_kg=20.0, record_history=True)
    d = create_disease(disease_name, severity=severity)
    c.attach_disease(d)

    for _ in range(steps):
        c.step()

    # Render multiple frames of one heartbeat cycle
    output_lines = []
    hr = getattr(c.heart, "heart_rate", 80)
    output_lines.append(f"  Heartbeat @ HR={hr:.0f} bpm ({disease_name})")
    output_lines.append("")

    for beat in range(beats):
        for ci in CYCLE:
            frame_lines = build_heart_dashboard(c, ci)
            output_lines.extend(frame_lines)
            output_lines.append("")  # spacer between frames

    return "\n".join(output_lines)


# ── Disease aliases ────────────────────────────────────────────

_DISEASE_ALIASES = {
    "dka": "diabetic_ketoacidosis",
    "arf": "acute_renal_failure",
    "dcm": "dilated_cardiomyopathy",
    "gdv": "gastric_dilatation_volvulus",
    "imha": "immune_mediated_hemolytic_anemia",
    "dic": "disseminated_intravascular_coagulation",
    "ckd": "ckd_anemia",
    "ivdd": "ivdd",
    "bloat": "gastric_dilatation_volvulus",
}


def _resolve_disease(name: str) -> str:
    return _DISEASE_ALIASES.get(name.lower(), name)


# ── CLI ───────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(prog="ascii-heart", description="ASCII heart animation")
    parser.add_argument("--once", action="store_true", help="Print snapshot frames")
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI colors")
    parser.add_argument("--disease", default="pneumonia")
    parser.add_argument("--severity", default="moderate")
    parser.add_argument("--steps", type=int, default=600)
    parser.add_argument("--beats", type=int, default=3, help="Number of heartbeat cycles to show")
    args = parser.parse_args()

    disease = _resolve_disease(args.disease)

    if args.once:
        print(snapshot(disease, args.severity, args.steps, args.beats))
    else:
        run_interactive(disease, args.severity)


if __name__ == "__main__":
    main()
