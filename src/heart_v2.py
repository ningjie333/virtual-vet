"""
Heart Animation v2 — life-simulator style ASCII art.

Inspired by life-simulator's angiogenesis/active_matter rendering:
  - Density ramp: ·∙░▒▓█ for blood volume
  - RBC particles: ● flowing through chambers
  - Heatmap colors: blue→cyan→green→yellow→red for pressure
  - Direction arrows: →↗↑↖←↙↓↘ for flow
  - Wall thickness: █▓▒░ based on contraction

Usage:
    uv run python src/heart_v2.py --once --disease dka
    uv run python src/heart_v2.py  # interactive
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


# ── Glyph sets (from life-simulator) ─────────────────────────

DENSITY_RAMP = " ·∙░▒▓█"           # 8 levels: empty → full
WALL_RAMP = [" ", "░", "▒", "▓", "█"]  # wall thickness
FLOW_ARROWS = ["→", "↗", "↑", "↖", "←", "↙", "↓", "↘"]  # 8 directions
BLOOD_PARTICLE = "●"
BLOOD_EMPTY = "○"

# Color pairs (curses)
# 1=red(artery), 2=green(normal), 3=yellow(warn), 4=blue(vein)
# 5=magenta(low-flow), 6=cyan(medium), 7=white(high)


# ── Cardiac cycle math ───────────────────────────────────────

PHASE_FRAC = [0.10, 0.05, 0.20, 0.15, 0.05, 0.30, 0.15]
PHASE_NAME = [
    "Atrial systole", "Isovolumetric CT", "Rapid ejection",
    "Reduced ejection", "Isovolumetric RT", "Rapid filling", "Reduced filling",
]

def _phase_at(t: float) -> tuple[int, float]:
    """Return (phase_index, progress_within_phase)."""
    cum = 0.0
    for i, f in enumerate(PHASE_FRAC):
        if t < cum + f:
            return i, (t - cum) / f
        cum += f
    return 6, 1.0


def _ventricular_volume(t: float) -> float:
    """Normalized ventricular volume (0=empty, 1=full)."""
    phase, prog = _phase_at(t)
    if phase == 0:   return 0.85 + 0.15 * prog          # atrial fill
    if phase == 1:   return 1.0                          # isovolumetric
    if phase == 2:   return 1.0 - 0.55 * prog            # rapid ejection
    if phase == 3:   return 0.45 - 0.10 * prog            # reduced ejection
    if phase == 4:   return 0.35                          # isovolumetric RT
    if phase == 5:   return 0.35 + 0.45 * prog            # rapid fill
    return 0.80 + 0.05 * prog                             # reduced fill


def _atrial_volume(t: float) -> float:
    """Normalized atrial volume."""
    phase, prog = _phase_at(t)
    if phase == 0:   return 0.9 - 0.5 * prog
    if phase <= 4:   return 0.4 + 0.1 * (phase - 1 + prog) / 4
    if phase == 5:   return 0.5 + 0.3 * prog
    return 0.8 + 0.1 * prog


def _av_open(t: float) -> bool:
    return _phase_at(t)[0] in (0, 5, 6)


def _sl_open(t: float) -> bool:
    return _phase_at(t)[0] in (2, 3)


# ── Pressure waveform ────────────────────────────────────────

def _pressure(t: float) -> float:
    """Arterial pressure 0..1."""
    phase, prog = _phase_at(t)
    if phase == 0:   return 0.6 + 0.05 * math.sin(prog * math.pi)
    if phase == 1:   return 0.65 + 0.35 * prog
    if phase == 2:   return 1.0 - 0.15 * prog
    if phase == 3:   return 0.85 - 0.25 * prog
    if phase == 4:   return 0.6 - 0.15 * prog
    if phase == 5:   return 0.45 + 0.1 * math.sin(prog * math.pi * 2)
    return 0.55 + 0.05 * prog


# ── Render engine ─────────────────────────────────────────────

def _density_char(val: float) -> str:
    """Map 0..1 to density glyph."""
    idx = int(val * (len(DENSITY_RAMP) - 1))
    return DENSITY_RAMP[max(0, min(len(DENSITY_RAMP) - 1, idx))]


def _wall_char(thickness: float) -> str:
    """Map 0..1 to wall glyph."""
    idx = int(thickness * (len(WALL_RAMP) - 1))
    return WALL_RAMP[max(0, min(len(WALL_RAMP) - 1, idx))]


def _heat_color(val: float) -> int:
    """Map 0..1 to curses color pair (blue→cyan→green→yellow→red)."""
    if val < 0.2:   return 4   # blue
    if val < 0.4:   return 6   # cyan
    if val < 0.6:   return 2   # green
    if val < 0.8:   return 3   # yellow
    return 1                   # red


def render_frame(stdscr: Any, creature: Any, t: float, max_y: int, max_x: int):
    """Render one frame of the heart animation."""
    hr = getattr(creature.heart, "heart_rate", 80)
    sv = getattr(creature.heart, "stroke_volume", 20)
    map_val = getattr(creature.heart, "mean_arterial_pressure", 100)
    co = hr * sv / 1000

    v_vol = _ventricular_volume(t)
    a_vol = _atrial_volume(t)
    av_open = _av_open(t)
    sl_open = _sl_open(t)
    pressure = _pressure(t)
    phase, prog = _phase_at(t)

    # Grid dimensions
    grid_h = min(20, max_y - 8)
    grid_w = min(50, max_x - 30)

    # Layout
    ox, oy = 2, 1  # origin

    # ── Draw heart anatomy ──

    # Great vessels (top)
    for c in range(8):
        stdscr.addstr(oy, ox + c, "█", curses.color_pair(1))  # aorta
        stdscr.addstr(oy, ox + grid_w - 8 + c, "█", curses.color_pair(4))  # vena cava

    # Atria
    a_fill = int(a_vol * 6)
    for r in range(3):
        for c in range(grid_w):
            # Left atrium
            if 2 <= c < 2 + a_fill:
                ch = BLOOD_PARTICLE if a_vol > 0.5 else BLOOD_EMPTY
                cp = _heat_color(a_vol)
            elif c == 1 or c == 2 + a_fill:
                ch = _wall_char(0.7)
                cp = 7
            else:
                ch = " "
                cp = 0

            # Right atrium
            ra_start = grid_w // 2 + 2
            if ra_start <= c < ra_start + a_fill:
                ch = BLOOD_PARTICLE if a_vol > 0.5 else BLOOD_EMPTY
                cp = _heat_color(a_vol * 0.8)  # venous = lower O2
            elif c == ra_start - 1 or c == ra_start + a_fill:
                ch = _wall_char(0.7)
                cp = 7

            try:
                stdscr.addstr(oy + 1 + r, ox + c, ch, curses.color_pair(cp))
            except curses.error:
                pass

    # AV valves
    av_y = oy + 4
    for c in range(grid_w):
        if c == grid_w // 4 or c == 3 * grid_w // 4:
            ch = "│" if av_open else "═"
            cp = 2 if av_open else 7
            try:
                stdscr.addstr(av_y, ox + c, ch, curses.color_pair(cp))
            except curses.error:
                pass

    # Ventricles
    v_fill = int(v_vol * (grid_w // 2 - 4))
    wall_t = 1.0 - v_vol  # thicker wall when contracted

    for r in range(grid_h - 8):
        for c in range(grid_w):
            # Left ventricle
            lv_start = 3
            if lv_start <= c < lv_start + v_fill:
                ch = BLOOD_PARTICLE if v_vol > 0.5 else BLOOD_EMPTY
                cp = _heat_color(pressure)
            elif c == lv_start - 1 or c == lv_start + v_fill:
                ch = _wall_char(wall_t)
                cp = 7
            else:
                ch = " "
                cp = 0

            # Right ventricle
            rv_start = grid_w // 2 + 3
            if rv_start <= c < rv_start + v_fill - 2:
                ch = BLOOD_PARTICLE if v_vol > 0.5 else BLOOD_EMPTY
                cp = _heat_color(pressure * 0.7)
            elif c == rv_start - 1 or c == rv_start + v_fill - 2:
                ch = _wall_char(wall_t)
                cp = 7

            try:
                stdscr.addstr(av_y + 1 + r, ox + c, ch, curses.color_pair(cp))
            except curses.error:
                pass

    # Apex
    apex_y = av_y + grid_h - 7
    apex_w = v_fill * 2
    for c in range(apex_w):
        ch = _wall_char(wall_t)
        try:
            stdscr.addstr(apex_y, ox + grid_w // 2 - apex_w // 2 + c, ch, curses.color_pair(7))
        except curses.error:
            pass

    # ── Vital signs panel ──
    vx = ox + grid_w + 3
    vy = oy

    def _add(y, x, text, cp=7):
        try:
            stdscr.addstr(y, x, text, curses.color_pair(cp))
        except curses.error:
            pass

    _add(vy, vx, f"═══ CARDIAC CYCLE ═══", 3)
    _add(vy + 2, vx, f" HR   {hr:6.1f} bpm", 2 if 60 <= hr <= 140 else 1)
    _add(vy + 3, vx, f" MAP  {map_val:6.1f} mmHg", 2 if 70 <= map_val <= 120 else 1)
    _add(vy + 4, vx, f" SV   {sv:6.1f} mL", 6)
    _add(vy + 5, vx, f" CO   {co:6.2f} L/min", 6)

    # Volume bars
    v_bar = _density_char(v_vol) * 15
    a_bar = _density_char(a_vol) * 15
    _add(vy + 7, vx, f" Ventricle [{v_bar}] {v_vol:.0%}", _heat_color(v_vol))
    _add(vy + 8, vx, f" Atrium    [{a_bar}] {a_vol:.0%}", _heat_color(a_vol))

    # Pressure bar
    p_bar = _density_char(pressure) * 15
    _add(vy + 10, vx, f" Pressure  [{p_bar}] {pressure:.0%}", _heat_color(pressure))

    # Phase
    _add(vy + 12, vx, f" Phase: {PHASE_NAME[phase]}", 3)
    prog_bar = "█" * int(prog * 20) + "░" * (20 - int(prog * 20))
    _add(vy + 13, vx, f" [{prog_bar}]", 6)

    # Flow direction
    if phase == 0:
        flow = "A → V (filling)"
    elif phase in (2, 3):
        flow = "V → A (ejection)"
    elif phase in (5, 6):
        flow = "V ← A (venous return)"
    else:
        flow = "── (no flow)"
    _add(vy + 15, vx, f" Flow: {flow}", 2)

    # Disease
    disease = getattr(creature, "disease", None)
    if disease:
        name = getattr(disease, "name", type(disease).__name__)
        _add(vy + 17, vx, f" Disease: {name}", 3)

    # Time
    t_s = getattr(creature, "current_time_s", 0)
    _add(vy + 18, vx, f" Time: {t_s/60:.0f}h {(t_s%3600)/60:.0f}m", 6)


# ── Interactive loop ──────────────────────────────────────────

def _curses_main(stdscr: Any, creature_fn: Any) -> None:
    curses.curs_set(0)
    curses.start_color()
    curses.use_default_colors()

    # Color pairs
    curses.init_pair(1, curses.COLOR_RED, -1)
    curses.init_pair(2, curses.COLOR_GREEN, -1)
    curses.init_pair(3, curses.COLOR_YELLOW, -1)
    curses.init_pair(4, curses.COLOR_BLUE, -1)
    curses.init_pair(5, curses.COLOR_MAGENTA, -1)
    curses.init_pair(6, curses.COLOR_CYAN, -1)
    curses.init_pair(7, curses.COLOR_WHITE, -1)

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
            t = (t + 0.02) % 1.0

        h, w = stdscr.getmaxyx()
        stdscr.erase()
        render_frame(stdscr, creature, t, h, w)

        # Footer
        hr = getattr(creature.heart, "heart_rate", 80)
        status = "PAUSED" if paused else "BEATING"
        footer = f" HR={hr:.0f} | {status} | Q=quit Space=pause R=reset"
        try:
            stdscr.addstr(h - 1, 0, footer[:w - 1],
                          curses.color_pair(3) | curses.A_REVERSE)
        except curses.error:
            pass

        stdscr.refresh()
        time.sleep(0.03)


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
             steps: int = 600, frames: int = 10) -> str:
    from src.simulation import VirtualCreature
    from src.diseases import create_disease

    c = VirtualCreature(body_weight_kg=20.0, record_history=True)
    d = create_disease(disease_name, severity=severity)
    c.attach_disease(d)

    for _ in range(steps):
        c.step()

    # Use curses to capture output
    import io
    buf = io.StringIO()

    for i in range(frames):
        t = i / frames
        phase, prog = _phase_at(t)
        v_vol = _ventricular_volume(t)
        a_vol = _atrial_volume(t)
        pressure = _pressure(t)

        hr = getattr(c.heart, "heart_rate", 80)
        sv = getattr(c.heart, "stroke_volume", 20)
        map_val = getattr(c.heart, "mean_arterial_pressure", 100)
        co = hr * sv / 1000

        buf.write(f"═══ CARDIAC CYCLE ({PHASE_NAME[phase]}) ═══\n")
        buf.write(f"\n")

        # Heart visualization (text mode)
        v_fill = int(v_vol * 20)
        a_fill = int(a_vol * 10)
        wall = _wall_char(1.0 - v_vol)

        # Atria
        la = BLOOD_PARTICLE * a_fill + " " * (10 - a_fill)
        ra = BLOOD_PARTICLE * a_fill + " " * (10 - a_fill)
        buf.write(f"   ╔{wall * 3}{la:^{10}}{wall * 3}╗╔{wall * 3}{ra:^{10}}{wall * 3}╗\n")

        # AV valves
        av = "│" if _av_open(t) else "═"
        buf.write(f"   ║  {av}  ║║  {av}  ║\n")

        # Ventricles
        lv = BLOOD_PARTICLE * v_fill + " " * (20 - v_fill)
        rv = BLOOD_PARTICLE * (v_fill - 2) + " " * (18 - v_fill + 2)
        for _ in range(4):
            buf.write(f"   ╔{wall * 3}{lv:^{20}}{wall * 3}╗╔{wall * 3}{rv:^{18}}{wall * 3}╗\n")

        # Apex
        apex = BLOOD_PARTICLE * (v_fill * 2)
        buf.write(f"      ╲{apex}╱\n")
        buf.write(f"\n")

        # Vitals
        buf.write(f" HR   {hr:6.1f} bpm    Ventricle: {_density_char(v_vol)} {v_vol:.0%}\n")
        buf.write(f" MAP  {map_val:6.1f} mmHg   Atrium:    {_density_char(a_vol)} {a_vol:.0%}\n")
        buf.write(f" SV   {sv:6.1f} mL     Pressure:  {_density_char(pressure)} {pressure:.0%}\n")
        buf.write(f" CO   {co:6.2f} L/min\n")
        buf.write(f"\n")

    return buf.getvalue()


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
    parser = argparse.ArgumentParser(prog="heart-v2", description="life-simulator style heart animation")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--disease", default="pneumonia")
    parser.add_argument("--severity", default="moderate")
    parser.add_argument("--steps", type=int, default=600)
    parser.add_argument("--frames", type=int, default=10)
    args = parser.parse_args()

    disease = _resolve_disease(args.disease)

    if args.once:
        print(snapshot(disease, args.severity, args.steps, args.frames))
    else:
        run_interactive(disease, args.severity)


if __name__ == "__main__":
    main()
