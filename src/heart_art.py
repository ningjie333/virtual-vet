"""
Realistic ASCII Heart — Anatomically suggestive beating heart with blood flow.

Features:
  - 4-chamber anatomy (RA, LA, RV, LV)
  - Sequential contraction: atria → ventricles (realistic timing)
  - Blood flow particles (● flowing through chambers)
  - Valve motion (open/close)
  - Color: deoxygenated (blue) right side, oxygenated (red) left side
  - ECG waveform synchronized with contraction

Frames (12 per cycle, ~0.8s at 80 bpm):
  0-2:   Atrial systole (atria contract, AV valves open)
  3-5:   Isovolumetric contraction (all valves closed)
  6-8:   Ventricular ejection (SL valves open, blood out)
  9-11:  Isovolumetric relaxation + filling
"""

from __future__ import annotations

import os
import sys
from typing import Any

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

try:
    import curses
    HAS_CURSES = True
except ImportError:
    HAS_CURSES = False


# ── ANSI color helpers ────────────────────────────────────────

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
BOLD = "\033[1m" if TC else ""
DIM = "\033[2m" if TC else ""

# Blood colors
ARTERY_R, ARTERY_G, ARTERY_B = 220, 40, 40    # oxygenated (red)
VEIN_R, VEIN_G, VEIN_B = 60, 80, 180           # deoxygenated (blue)
MUSCLE_R, MUSCLE_G, MUSCLE_B = 180, 100, 100   # myocardium (pink-brown)


# ── Heart anatomy frames ─────────────────────────────────────
# Each frame is a list of (char, color_type) tuples
# color_type: 'a'=artery(red), 'v'=vein(blue), 'm'=muscle, ' '=empty

def _heart_frame(phase: int, contract: float) -> list[str]:
    """
    Generate one frame of the heart animation.

    Args:
        phase: 0-11, position in cardiac cycle
        contract: 0.0=relaxed, 1.0=fully contracted (ventricles)
    """
    # Ventricular contraction curve (sine wave, peaks at phase 6-8)
    import math
    v_contract = max(0, math.sin(phase * math.pi / 6))  # 0→1→0 over 0-12
    a_contract = max(0, math.sin((phase + 3) * math.pi / 3))  # atria contract first

    # Chamber widths based on contraction
    lv_w = int(8 - v_contract * 3)  # left ventricle
    rv_w = int(6 - v_contract * 2)  # right ventricle
    la_w = int(5 - a_contract * 1)  # left atrium
    ra_w = int(5 - a_contract * 1)  # right atrium

    # Blood flow particles
    flow_chars = "●○◉"
    if phase < 3:  # atrial systole: blood flows A→V
        flow = flow_chars[phase % 3]
    elif phase < 6:  # isovolumetric: no flow
        flow = "·"
    elif phase < 9:  # ejection: blood flows V→arteries
        flow = flow_chars[(phase - 6) % 3]
    else:  # filling: blood flows veins→A
        flow = flow_chars[(phase - 9) % 3]

    # Build heart lines
    lines = []

    # Great vessels (top)
    lines.append("      ╔══╗  ╔══╗      ")
    lines.append("      ║AA║  ║VV║      ")
    lines.append("      ║AA║  ║VV║      ")

    # Atria
    la = "█" * la_w
    ra = "█" * ra_w
    lines.append(f"   ╔══{la:^{la_w}}══╗╔══{ra:^{ra_w}}══╗   ")

    # AV valves (open/closed)
    av_l = "│" if v_contract < 0.3 else "─"
    av_r = "│" if v_contract < 0.3 else "─"
    lines.append(f"   ║  {av_l}  ║║  {av_r}  ║   ")

    # Ventricles
    lv = "█" * lv_w
    rv = "█" * rv_w
    lines.append(f"   ╔══{lv:^{lv_w}}══╗╔══{rv:^{rv_w}}══╗   ")
    lines.append(f"   ║  {lv:^{lv_w}}  ║║  {rv:^{rv_w}}  ║   ")
    lines.append(f"   ╚══{lv:^{lv_w}}══╝╚══{rv:^{rv_w}}══╝   ")

    # Bottom (apex)
    lines.append(f"      ╲{'█' * (lv_w + rv_w - 2):^{lv_w + rv_w - 2}}╱      ")
    lines.append(f"       ╲{'█' * (lv_w + rv_w - 4):^{lv_w + rv_w - 4}}╱       ")
    lines.append(f"        ╲{'█' * (lv_w + rv_w - 6):^{lv_w + rv_w - 6}}╱        ")

    return lines


# ── ECG waveform ─────────────────────────────────────────────

def _ecg_line(phase: int, width: int = 40) -> str:
    """Generate one line of ECG waveform at the given phase."""
    import math

    # P wave (atrial depolarization): phase 0-2
    # QRS complex (ventricular depolarization): phase 3-5
    # T wave (ventricular repolarization): phase 8-10

    chars = []
    for i in range(width):
        t = (i / width + phase / 12) % 1.0

        # P wave
        if 0.0 <= t < 0.15:
            y = 0.3 * math.sin((t / 0.15) * math.pi)
        # PR segment
        elif 0.15 <= t < 0.25:
            y = 0
        # Q wave
        elif 0.25 <= t < 0.30:
            y = -0.2 * math.sin(((t - 0.25) / 0.05) * math.pi)
        # R wave
        elif 0.30 <= t < 0.38:
            y = 1.0 * math.sin(((t - 0.30) / 0.08) * math.pi)
        # S wave
        elif 0.38 <= t < 0.43:
            y = -0.3 * math.sin(((t - 0.38) / 0.05) * math.pi)
        # ST segment
        elif 0.43 <= t < 0.55:
            y = 0.05
        # T wave
        elif 0.55 <= t < 0.75:
            y = 0.4 * math.sin(((t - 0.55) / 0.20) * math.pi)
        # Baseline
        else:
            y = 0

        # Map y to character
        if y > 0.7:
            ch = "█"
        elif y > 0.4:
            ch = "▓"
        elif y > 0.15:
            ch = "▒"
        elif y > 0.02:
            ch = "░"
        elif y < -0.15:
            ch = "▄"
        else:
            ch = "─"

        chars.append(ch)

    return "".join(chars)


# ── Full heart display ────────────────────────────────────────

def render_heart_display(creature: Any, phase: int, width: int = 78) -> list[str]:
    """Render the full heart display with anatomy, ECG, and vital signs."""
    hr = getattr(creature.heart, "heart_rate", 80)
    sv = getattr(creature.heart, "stroke_volume", 20)
    map_val = getattr(creature.heart, "mean_arterial_pressure", 100)
    co = hr * sv / 1000
    contractility = getattr(creature.heart, "contractility_factor", 1.0)

    # Contractile state
    import math
    v_contract = max(0, math.sin(phase * math.pi / 6))

    # Heart anatomy
    heart_lines = _heart_frame(phase, v_contract)

    # Color the heart based on contractility
    intensity = min(1.0, contractility)
    if TC:
        r = int(180 + 75 * intensity)
        g = int(60 + 40 * intensity)
        b = int(60 + 20 * intensity)
        heart_color = _fg(r, g, b)
    else:
        heart_color = ""

    # Vital signs
    vitals = [
        f" HR   {hr:6.1f} bpm",
        f" MAP  {map_val:6.1f} mmHg",
        f" SV   {sv:6.1f} mL",
        f" CO   {co:6.2f} L/min",
    ]

    # Disease
    disease = getattr(creature, "disease", None)
    if disease:
        name = getattr(disease, "name", type(disease).__name__)
        vitals.append(f" {name}")

    # ECG line
    ecg = _ecg_line(phase, 40)
    if TC:
        ecg = f"{_fg(40, 200, 80)}{ecg}{RESET}"

    # Combine
    lines = []

    # Title
    lines.append(f"{'CARDIAC CYCLE':^{width}}")
    lines.append("")

    # Heart + vitals side by side
    heart_w = max(len(h) for h in heart_lines) + 2
    for i in range(max(len(heart_lines), len(vitals))):
        left = ""
        if i < len(heart_lines):
            row = heart_lines[i]
            left = f"{heart_color}{row}{RESET}"
        left_padded = left + " " * (heart_w - len(heart_lines[i]) if i < len(heart_lines) else 0)

        right = vitals[i] if i < len(vitals) else ""
        lines.append(f"  {left_padded}  {right}")

    lines.append("")

    # ECG waveform
    lines.append(f"  ECG: [{ecg}]")
    lines.append("")

    # Phase indicator
    phase_names = [
        "Atrial systole", "Atrial systole", "Atrial systole",
        "Isovolumetric contraction", "Isovolumetric contraction", "Isovolumetric contraction",
        "Ventricular ejection", "Ventricular ejection", "Ventricular ejection",
        "Relaxation", "Filling", "Filling",
    ]
    current_phase = phase_names[phase % 12]

    # Progress bar for cardiac cycle
    bar_w = 30
    filled = int((phase / 12) * bar_w)
    bar = "█" * filled + "░" * (bar_w - filled)
    lines.append(f"  Phase: {current_phase:<30} [{bar}]")

    return lines


# ── Interactive mode ──────────────────────────────────────────

def _curses_main(stdscr: Any, creature_fn: Any) -> None:
    curses.curs_set(0)
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_RED, -1)
    curses.init_pair(2, curses.COLOR_GREEN, -1)
    curses.init_pair(3, curses.COLOR_BLUE, -1)

    creature = creature_fn()
    phase = 0
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
            hr = getattr(creature.heart, "heart_rate", 80)
            # Advance phase based on HR
            phase = (phase + 1) % 12

        h, w = stdscr.getmaxyx()
        lines = render_heart_display(creature, phase, w - 2)

        stdscr.erase()
        for i, line in enumerate(lines):
            if i >= h - 1:
                break
            try:
                stdscr.addstr(i, 0, line[:w-1])
            except curses.error:
                pass

        status = f" HR={getattr(creature.heart, 'heart_rate', 80):.0f} | {'PAUSED' if paused else 'BEATING'} | Q=quit Space=pause R=reset"
        try:
            stdscr.addstr(h-1, 0, status[:w-1], curses.color_pair(1) | curses.A_REVERSE)
        except curses.error:
            pass

        stdscr.refresh()
        import time
        hr = getattr(creature.heart, "heart_rate", 80)
        beat_period = 60.0 / max(hr, 1)
        time.sleep(beat_period / 12)


def _ansi_loop(creature_fn: Any) -> None:
    """ANSI-based interactive loop (works on Windows Terminal)."""
    import time
    import sys

    # Platform-specific non-blocking key read
    if sys.platform == "win32":
        import msvcrt
        def _key_ready():
            return msvcrt.kbhit()
        def _read_key():
            return msvcrt.getch().decode("utf-8", errors="ignore").lower()
    else:
        import select
        def _key_ready():
            return select.select([sys.stdin], [], [], 0)[0]
        def _read_key():
            return sys.stdin.read(1).lower()

    creature = creature_fn()
    phase = 0
    paused = False

    # Hide cursor
    print("\033[?25l", end="", flush=True)

    try:
        while True:
            # Check for keypress (non-blocking)
            if _key_ready():
                key = _read_key()
                if key == "q":
                    break
                elif key == " ":
                    paused = not paused
                elif key == "r":
                    creature = creature_fn()

            if not paused:
                creature.step()
                phase = (phase + 1) % 12

            # Render
            lines = render_heart_display(creature, phase)
            output = "\033[H"
            for line in lines:
                output += line + "\033[K\n"

            hr = getattr(creature.heart, "heart_rate", 80)
            status = "PAUSED" if paused else "BEATING"
            output += f"\033[K  HR={hr:.0f} | {status} | Q=quit Space=pause R=reset\033[K"

            print(output, end="", flush=True)

            # Sleep based on HR
            beat_period = 60.0 / max(hr, 1)
            time.sleep(beat_period / 12)

    finally:
        # Show cursor
        print("\033[?25h", end="", flush=True)


def run_interactive(disease_name: str = "pneumonia", severity: str = "moderate") -> None:
    from src.simulation import VirtualCreature
    from src.diseases import create_disease

    def make():
        c = VirtualCreature(body_weight_kg=20.0, record_history=True)
        d = create_disease(disease_name, severity=severity)
        c.attach_disease(d)
        return c

    if HAS_CURSES:
        curses.wrapper(lambda s: _curses_main(s, make))
    else:
        # ANSI fallback for Windows
        print("\033[2J", end="", flush=True)  # clear screen
        _ansi_loop(make)


# ── Snapshot ──────────────────────────────────────────────────

def snapshot(disease_name: str = "pneumonia", severity: str = "moderate",
             steps: int = 600, cycles: int = 2) -> str:
    from src.simulation import VirtualCreature
    from src.diseases import create_disease

    c = VirtualCreature(body_weight_kg=20.0, record_history=True)
    d = create_disease(disease_name, severity=severity)
    c.attach_disease(d)

    for _ in range(steps):
        c.step()

    output = []
    for _ in range(cycles):
        for phase in range(12):
            lines = render_heart_display(c, phase)
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
    parser = argparse.ArgumentParser(prog="heart-art", description="Realistic ASCII heart animation")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--disease", default="pneumonia")
    parser.add_argument("--severity", default="moderate")
    parser.add_argument("--steps", type=int, default=600)
    parser.add_argument("--cycles", type=int, default=2)
    args = parser.parse_args()

    disease = _resolve_disease(args.disease)

    if args.once:
        print(snapshot(disease, args.severity, args.steps, args.cycles))
    else:
        run_interactive(disease, args.severity)


if __name__ == "__main__":
    main()
