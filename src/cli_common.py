"""
CLI Common — Shared code for all vet-monitor subcommands.

Extracts:
  - Disease aliases
  - Creature factory
  - ANSI/curses helpers
  - Common argparse patterns
"""

from __future__ import annotations

import os
import sys
from typing import Any

# Ensure both project root and src/ are on sys.path
# (src/ is needed because simulation.py uses 'from blood import ...')
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_PROJECT_ROOT, "src")
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)


# ── Disease aliases ────────────────────────────────────────────

DISEASE_ALIASES = {
    "dka": "diabetic_ketoacidosis",
    "arf": "acute_renal_failure",
    "dcm": "dilated_cardiomyopathy",
    "gdv": "gastric_dilatation_volvulus",
    "imha": "immune_mediated_hemolytic_anemia",
    "dic": "disseminated_intravascular_coagulation",
    "ckd": "ckd_anemia",
    "bloat": "gastric_dilatation_volvulus",
    "ivdd": "ivdd",
}


def resolve_disease(name: str) -> str:
    """Resolve disease alias to full name."""
    return DISEASE_ALIASES.get(name.lower(), name)


# ── Creature factory ──────────────────────────────────────────

def create_creature(disease_name: str, severity: str = "moderate",
                    weight: float = 20.0, steps: int = 0) -> Any:
    """Create a VirtualCreature with disease attached and optionally pre-simulate."""
    from src.simulation import VirtualCreature
    from src.diseases import create_disease

    c = VirtualCreature(body_weight_kg=weight, record_history=True)
    d = create_disease(resolve_disease(disease_name), severity=severity)
    c.attach_disease(d)

    for _ in range(steps):
        c.step()

    return c


# ── ANSI helpers ──────────────────────────────────────────────

def has_truecolor() -> bool:
    """Check if terminal supports 24-bit color."""
    ct = os.environ.get("COLORTERM", "")
    wt = os.environ.get("WT_SESSION", "")
    return ct in ("truecolor", "24bit") or bool(wt)


TC = has_truecolor()

def fg(r: int, g: int, b: int) -> str:
    return f"\033[38;2;{r};{g};{b}m" if TC else ""

def bg(r: int, g: int, b: int) -> str:
    return f"\033[48;2;{r};{g};{b}m" if TC else ""

RESET = "\033[0m" if TC else ""
BOLD = "\033[1m" if TC else ""
DIM = "\033[2m" if TC else ""


# ── Curses helpers ────────────────────────────────────────────

def has_curses() -> bool:
    """Check if curses is available."""
    try:
        import curses
        return True
    except ImportError:
        try:
            import _curses
            import curses
            return True
        except ImportError:
            return False


def init_curses_colors(stdscr: Any) -> None:
    """Initialize standard curses color pairs."""
    import curses
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_RED, -1)
    curses.init_pair(2, curses.COLOR_GREEN, -1)
    curses.init_pair(3, curses.COLOR_YELLOW, -1)
    curses.init_pair(4, curses.COLOR_BLUE, -1)
    curses.init_pair(5, curses.COLOR_MAGENTA, -1)
    curses.init_pair(6, curses.COLOR_CYAN, -1)
    curses.init_pair(7, curses.COLOR_WHITE, -1)


# ── Colormap (thermal) ───────────────────────────────────────

def thermal_color(frac: float) -> tuple[int, int, int]:
    """Map 0..1 to thermal colormap RGB."""
    if frac < 0.25:
        return (30, 30, int(100 + 155 * frac * 4))
    elif frac < 0.5:
        t = (frac - 0.25) * 4
        return (30, int(30 + 170 * t), int(255 - 55 * t))
    elif frac < 0.75:
        t = (frac - 0.5) * 4
        return (int(30 + 225 * t), int(200 + 55 * t), int(200 - 160 * t))
    else:
        t = (frac - 0.75) * 4
        return (255, int(255 - 155 * t), int(40 - 20 * t))


def vital_color(value: float, lo: float, hi: float,
                crit_lo: float, crit_hi: float) -> str:
    """Map vital sign value to hex color string."""
    if value < crit_lo or value > crit_hi:
        return "#ff3030"
    elif value < lo or value > hi:
        return "#ffb020"
    else:
        return "#40c060"


# ── Density ramp (from life-simulator) ───────────────────────

DENSITY_RAMP = " ·∙░▒▓█"

def density_char(val: float) -> str:
    """Map 0..1 to density glyph."""
    idx = int(val * (len(DENSITY_RAMP) - 1))
    return DENSITY_RAMP[max(0, min(len(DENSITY_RAMP) - 1, idx))]


# ── Common argparse ───────────────────────────────────────────

def add_disease_args(parser: Any) -> None:
    """Add common disease-related arguments to a parser."""
    parser.add_argument("--disease", default="pneumonia",
                        help="Disease name or alias (dka, arf, dcm, gdv, etc.)")
    parser.add_argument("--severity", default="moderate",
                        choices=["mild", "moderate", "severe"],
                        help="Disease severity")
    parser.add_argument("--steps", type=int, default=0,
                        help="Pre-simulate N steps before display")


def add_display_args(parser: Any) -> None:
    """Add common display-related arguments to a parser."""
    parser.add_argument("--once", action="store_true",
                        help="Single snapshot mode (pipe-friendly)")
    parser.add_argument("--no-color", action="store_true",
                        help="Disable ANSI colors")
