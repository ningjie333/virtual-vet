"""
Realistic Cardiac Cycle Animation — Based on actual cardiac physiology.

Reference: Real echocardiogram 4-chamber view + cardiac cycle phases.

Key features:
  - Wall thickening during systole (myocardial contraction)
  - Valve leaflet motion (mitral/tricuspid open/close)
  - Blood flow particles (direction + velocity)
  - Volume visualization (chamber size changes)
  - Pressure waveform (integrated ECG + arterial pressure)
  - 6 phases with proper timing ratios

Phases (total ~0.8s at 75 bpm):
  1. Atrial systole      (10%) - atria contract, AV valves open
  2. Isovolumetric CT     (5%) - all valves closed, pressure builds
  3. Rapid ejection      (20%) - SL valves open, blood ejected
  4. Reduced ejection    (15%) - slower ejection
  5. Isovolumetric RT     (5%) - all valves closed, pressure drops
  6. Rapid filling       (30%) - AV valves open, passive fill
  7. Reduced filling     (15%) - slower fill (diastasis)
"""

from __future__ import annotations

import math
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
    try:
        import _curses
        import curses
        HAS_CURSES = True
    except ImportError:
        HAS_CURSES = False


# ── ANSI helpers ──────────────────────────────────────────────

def _tc() -> bool:
    ct = os.environ.get("COLORTERM", "")
    wt = os.environ.get("WT_SESSION", "")
    return ct in ("truecolor", "24bit") or bool(wt)

TC = _tc()

def _fg(r, g, b):
    return f"\033[38;2;{r};{g};{b}m" if TC else ""

def _bg(r, g, b):
    return f"\033[48;2;{r};{g};{b}m" if TC else ""

RESET = "\033[0m" if TC else ""


# ── Cardiac cycle timing ─────────────────────────────────────

# Phase fractions (must sum to 1.0)
PHASE_FRACTIONS = [0.10, 0.05, 0.20, 0.15, 0.05, 0.30, 0.15]
PHASE_NAMES = [
    "Atrial systole",
    "Isovolumetric contraction",
    "Rapid ejection",
    "Reduced ejection",
    "Isovolumetric relaxation",
    "Rapid filling",
    "Reduced filling",
]

def _phase_at(t: float) -> int:
    """Get phase index (0-6) at time t within one beat (0..1)."""
    cumulative = 0.0
    for i, frac in enumerate(PHASE_FRACTIONS):
        cumulative += frac
        if t < cumulative:
            return i
    return 6


def _phase_progress(t: float) -> float:
    """Get progress within current phase (0..1)."""
    cumulative = 0.0
    for i, frac in enumerate(PHASE_FRACTIONS):
        if t < cumulative + frac:
            return (t - cumulative) / frac
        cumulative += frac
    return 1.0


# ── Ventricular volume curve ──────────────────────────────────
# Normalized ventricular volume (0=empty, 1=full) through cardiac cycle

def _ventricular_volume(t: float) -> float:
    """
    Ventricular volume through one cardiac cycle.
    Based on real pressure-volume loop shape.
    """
    phase = _phase_at(t)
    prog = _phase_progress(t)

    if phase == 0:   # Atrial systole: slight filling
        return 0.85 + 0.15 * prog
    elif phase == 1: # Isovolumetric CT: constant volume
        return 1.0
    elif phase == 2: # Rapid ejection: fast emptying
        return 1.0 - 0.55 * prog
    elif phase == 3: # Reduced ejection: slower emptying
        return 0.45 - 0.10 * prog
    elif phase == 4: # Isovolumetric RT: constant volume
        return 0.35
    elif phase == 5: # Rapid filling: fast filling
        return 0.35 + 0.45 * prog
    else:            # Reduced filling: slow filling
        return 0.80 + 0.05 * prog


# ── Atrial volume curve ───────────────────────────────────────

def _atrial_volume(t: float) -> float:
    """Atrial volume (0=empty, 1=full)."""
    phase = _phase_at(t)
    prog = _phase_progress(t)

    if phase == 0:   # Atrial systole: contracting
        return 0.9 - 0.5 * prog
    elif phase <= 4: # Gradual filling
        return 0.4 + 0.1 * (phase - 1 + prog) / 4
    elif phase == 5: # Rapid filling from veins
        return 0.5 + 0.3 * prog
    else:
        return 0.8 + 0.1 * prog


# ── Valve states ──────────────────────────────────────────────

def _av_valve_open(t: float) -> bool:
    """AV valves (mitral/tricuspid) open during filling + atrial systole."""
    phase = _phase_at(t)
    return phase in (0, 5, 6)  # open during filling phases


def _sl_valve_open(t: float) -> bool:
    """Semilunar valves (aortic/pulmonary) open during ejection."""
    phase = _phase_at(t)
    return phase in (2, 3)  # open during ejection


# ── Blood flow direction ──────────────────────────────────────

def _flow_direction(t: float) -> str:
    """Current blood flow direction indicator."""
    phase = _phase_at(t)
    if phase == 0:
        return "A→V"  # atria to ventricles
    elif phase in (2, 3):
        return "V→A"  # ventricles to arteries
    elif phase in (5, 6):
        return "V←A"  # veins to atria (and atria to ventricles)
    else:
        return "───"  # no flow


# ── Generate heart frame ──────────────────────────────────────

def _render_heart(t: float, width: int = 24) -> list[str]:
    """
    Render one frame of the heart at time t (0..1 within beat).

    Uses box-drawing characters for anatomy:
      ╔╗╚╝═║  for walls
      ─│     for open valves
      ▪▫●    for blood particles
    """
    v_vol = _ventricular_volume(t)
    a_vol = _atrial_volume(t)
    av_open = _av_valve_open(t)
    sl_open = _sl_valve_open(t)

    # Wall thickness based on contraction (thicker = more contracted)
    v_wall = int(2 + (1 - v_vol) * 3)  # 2-5 chars
    a_wall = int(2 + (1 - a_vol) * 2)  # 2-4 chars

    # Chamber widths
    lv_w = max(4, int(v_vol * 10))
    rv_w = max(3, int(v_vol * 8))
    la_w = max(3, int(a_vol * 6))
    ra_w = max(3, int(a_vol * 6))

    # Blood density (more particles when full)
    blood_ch = "●" if v_vol > 0.5 else "○" if v_vol > 0.3 else "·"

    # Valve characters
    av_ch = "│" if av_open else "═"
    sl_ch = "│" if sl_open else "═"

    lines = []

    # Great vessels
    lines.append("    ╔════╗  ╔════╗    ")
    lines.append("    ║ Aorta║  ║ VCS ║    ")
    lines.append("    ╚═══╤╝  ╚╤═══╝    ")

    # Semilunar valves
    if sl_open:
        lines.append("        │    │        ")
    else:
        lines.append("        ══════        ")

    # Atria
    la_fill = "●" * la_w + " " * (6 - la_w)
    ra_fill = "●" * ra_w + " " * (6 - ra_w)
    lines.append(f"   ╔{'═' * a_wall}{la_fill:^{6}}{'═' * a_wall}╗╔{'═' * a_wall}{ra_fill:^{6}}{'═' * a_wall}╗   ")

    # AV valves
    if av_open:
        lines.append(f"   ║{' ' * (a_wall + 6 + a_wall)}║║{' ' * (a_wall + 6 + a_wall)}║   ")
    else:
        lines.append(f"   ║{'═' * (a_wall + 6 + a_wall)}║║{'═' * (a_wall + 6 + a_wall)}║   ")

    # Ventricles
    lv_fill = blood_ch * lv_w + " " * (10 - lv_w)
    rv_fill = blood_ch * rv_w + " " * (8 - rv_w)

    for row in range(3):
        if row == 0:
            lines.append(f"   ╔{'═' * v_wall}{lv_fill:^{10}}{'═' * v_wall}╗╔{'═' * v_wall}{rv_fill:^{8}}{'═' * v_wall}╗   ")
        elif row == 1:
            lines.append(f"   ║{'█' * v_wall}{lv_fill:^{10}}{'█' * v_wall}║║{'█' * v_wall}{rv_fill:^{8}}{'█' * v_wall}║   ")
        else:
            lines.append(f"   ╚{'═' * v_wall}{lv_fill:^{10}}{'═' * v_wall}╝╚{'═' * v_wall}{rv_fill:^{8}}{'═' * v_wall}╝   ")

    # Apex
    apex_w = lv_w + rv_w + v_wall * 4 + 3
    apex_fill = blood_ch * (apex_w - 4)
    lines.append(f"      ╲{apex_fill:^{apex_w - 4}}╱      ")
    lines.append(f"       ╲{'█' * (apex_w - 8):^{apex_w - 8}}╱       ")

    return lines


# ── Pressure waveform ─────────────────────────────────────────

def _pressure_line(t: float, width: int = 50) -> str:
    """Generate arterial pressure waveform."""
    # Simplified Windkessel model shape
    phase = _phase_at(t)
    prog = _phase_progress(t)

    if phase == 0:   # Atrial systole: slight bump
        p = 0.6 + 0.05 * math.sin(prog * math.pi)
    elif phase == 1: # Isovolumetric CT: rising
        p = 0.65 + 0.35 * prog
    elif phase == 2: # Rapid ejection: peak
        p = 1.0 - 0.15 * prog
    elif phase == 3: # Reduced ejection: falling
        p = 0.85 - 0.25 * prog
    elif phase == 4: # Isovolumetric RT: falling
        p = 0.6 - 0.15 * prog
    elif phase == 5: # Rapid filling: dicrotic notch then rise
        p = 0.45 + 0.1 * math.sin(prog * math.pi * 2)
    else:            # Reduced filling: baseline
        p = 0.55 + 0.05 * prog

    # Map to characters
    chars = []
    for i in range(width):
        x = i / width
        # Create waveform shape
        if x < t:
            # Past: show the waveform
            y = p * 0.8
        else:
            # Future: baseline
            y = 0.3

        if y > 0.7:
            ch = "█"
        elif y > 0.5:
            ch = "▓"
        elif y > 0.35:
            ch = "▒"
        elif y > 0.2:
            ch = "░"
        else:
            ch = "─"

        chars.append(ch)

    return "".join(chars)


# ── Volume indicator ──────────────────────────────────────────

def _volume_bar(v: float, width: int = 20) -> str:
    """Volume as a bar gauge."""
    filled = int(v * width)
    return "█" * filled + "░" * (width - filled)


# ── Full display ──────────────────────────────────────────────

def render_cardiac_display(creature: Any, t: float, width: int = 78) -> list[str]:
    """Render complete cardiac cycle display."""
    hr = getattr(creature.heart, "heart_rate", 80)
    sv = getattr(creature.heart, "stroke_volume", 20)
    map_val = getattr(creature.heart, "mean_arterial_pressure", 100)
    co = hr * sv / 1000

    # Heart animation
    heart_lines = _render_heart(t)

    # Vital signs
    vitals = [
        f" HR    {hr:6.1f} bpm",
        f" MAP   {map_val:6.1f} mmHg",
        f" SV    {sv:6.1f} mL",
        f" CO    {co:6.2f} L/min",
    ]

    # Phase info
    phase = _phase_at(t)
    phase_prog = _phase_progress(t)
    phase_name = PHASE_NAMES[phase]

    # Volume
    v_vol = _ventricular_volume(t)
    a_vol = _atrial_volume(t)

    # Flow direction
    flow = _flow_direction(t)

    # Build display
    lines = []

    # Title
    lines.append(f"{'CARDIAC CYCLE SIMULATION':^{width}}")
    lines.append("")

    # Heart + vitals
    heart_w = max(len(h) for h in heart_lines) + 2
    for i in range(max(len(heart_lines), len(vitals))):
        left = heart_lines[i] if i < len(heart_lines) else " " * heart_w
        right = vitals[i] if i < len(vitals) else ""
        lines.append(f"  {left:<{heart_w}}  {right}")

    lines.append("")

    # Pressure waveform
    pressure = _pressure_line(t)
    if TC:
        pressure = f"{_fg(220, 60, 60)}{pressure}{RESET}"
    lines.append(f"  Pressure: [{pressure}]")

    # Volume bars
    v_bar = _volume_bar(v_vol)
    a_bar = _volume_bar(a_vol)
    if TC:
        v_bar = f"{_fg(60, 80, 180)}{v_bar}{RESET}"
        a_bar = f"{_fg(180, 100, 100)}{a_bar}{RESET}"
    lines.append(f"  Ventricular: [{v_bar}] {v_vol:.0%}")
    lines.append(f"  Atrial:      [{a_bar}] {a_vol:.0%}")

    # Phase indicator
    phase_bar_w = 30
    filled = int(phase_prog * phase_bar_w)
    phase_bar = "█" * filled + "░" * (phase_bar_w - filled)
    lines.append(f"  Phase: {phase_name:<28} [{phase_bar}]")
    lines.append(f"  Flow:  {flow}")

    return lines


# ── Interactive mode ──────────────────────────────────────────

def _curses_main(stdscr: Any, creature_fn: Any) -> None:
    curses.curs_set(0)
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_RED, -1)
    curses.init_pair(2, curses.COLOR_GREEN, -1)

    creature = creature_fn()
    t = 0.0
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
            t = 0.0

        if not paused:
            creature.step()
            hr = getattr(creature.heart, "heart_rate", 80)
            beat_period = 60.0 / max(hr, 1)
            # Advance time within beat
            t = (t + 0.02) % 1.0

        h, w = stdscr.getmaxyx()
        lines = render_cardiac_display(creature, t, w - 2)

        stdscr.erase()
        for i, line in enumerate(lines):
            if i >= h - 1:
                break
            try:
                stdscr.addstr(i, 0, line[:w-1])
            except curses.error:
                pass

        hr = getattr(creature.heart, "heart_rate", 80)
        status = "PAUSED" if paused else "BEATING"
        footer = f" HR={hr:.0f} | {status} | Q=quit Space=pause R=reset"
        try:
            stdscr.addstr(h-1, 0, footer[:w-1], curses.color_pair(1) | curses.A_REVERSE)
        except curses.error:
            pass

        stdscr.refresh()
        time.sleep(0.03)  # ~30fps


def run_interactive(disease_name: str = "pneumonia", severity: str = "moderate") -> None:
    if not HAS_CURSES:
        print("curses not available.", file=sys.stderr)
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
             steps: int = 600, frames: int = 20) -> str:
    from src.simulation import VirtualCreature
    from src.diseases import create_disease

    c = VirtualCreature(body_weight_kg=20.0, record_history=True)
    d = create_disease(disease_name, severity=severity)
    c.attach_disease(d)

    for _ in range(steps):
        c.step()

    output = []
    for i in range(frames):
        t = i / frames
        lines = render_cardiac_display(c, t)
        output.extend(lines)
        output.append("")

    return "\n".join(output)


# ── CLI ───────────────────────────────────────────────────────

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


def main():
    import argparse
    parser = argparse.ArgumentParser(prog="heart-realistic", description="Realistic cardiac cycle animation")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--disease", default="pneumonia")
    parser.add_argument("--severity", default="moderate")
    parser.add_argument("--steps", type=int, default=600)
    parser.add_argument("--frames", type=int, default=20)
    args = parser.parse_args()

    disease = _resolve_disease(args.disease)

    if args.once:
        print(snapshot(disease, args.severity, args.steps, args.frames))
    else:
        run_interactive(disease, args.severity)


if __name__ == "__main__":
    main()
