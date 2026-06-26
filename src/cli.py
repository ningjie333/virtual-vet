"""
vet-monitor — Unified CLI for Virtual Vet patient monitoring.

Usage:
    vet-monitor dashboard [--disease DKA] [--live]
    vet-monitor heart [--style realistic] [--disease DKA]
    vet-monitor snapshot [--format text|ansi]
    vet-monitor list-diseases
"""

from __future__ import annotations

import argparse
import sys


def main():
    parser = argparse.ArgumentParser(
        prog="vet-monitor",
        description="Virtual Vet — Terminal patient monitor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  vet-monitor dashboard --disease dka --live
  vet-monitor heart --style life --disease dka
  vet-monitor snapshot --disease dka --steps 3000
  vet-monitor list-diseases
""",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # ── dashboard ─────────────────────────────────────────────
    p_dash = subparsers.add_parser("dashboard", help="Patient vital signs dashboard")
    p_dash.add_argument("--disease", default="pneumonia", help="Disease name or alias")
    p_dash.add_argument("--severity", default="moderate", choices=["mild", "moderate", "severe"])
    p_dash.add_argument("--steps", type=int, default=0, help="Pre-simulate N steps")
    p_dash.add_argument("--live", action="store_true", help="Real-time interactive mode (Textual)")
    p_dash.add_argument("--once", action="store_true", help="Alias for snapshot mode (default)")
    p_dash.add_argument("--no-color", action="store_true", help="Disable ANSI colors")

    # ── heart ─────────────────────────────────────────────────
    p_heart = subparsers.add_parser("heart", help="Heart animation")
    p_heart.add_argument("--disease", default="pneumonia", help="Disease name or alias")
    p_heart.add_argument("--severity", default="moderate", choices=["mild", "moderate", "severe"])
    p_heart.add_argument("--steps", type=int, default=0, help="Pre-simulate N steps")
    p_heart.add_argument("--style", default="life",
                         choices=["life"],
                         help="Animation style (only 'life' supported)")
    p_heart.add_argument("--once", action="store_true", help="Snapshot mode")
    p_heart.add_argument("--frames", type=int, default=10, help="Frames in snapshot mode")

    # ── snapshot ──────────────────────────────────────────────
    p_snap = subparsers.add_parser("snapshot", help="Quick snapshot of patient state")
    p_snap.add_argument("--disease", default="pneumonia", help="Disease name or alias")
    p_snap.add_argument("--severity", default="moderate", choices=["mild", "moderate", "severe"])
    p_snap.add_argument("--steps", type=int, default=600, help="Simulation steps")
    p_snap.add_argument("--format", default="text", choices=["text", "ansi"],
                        help="Output format")

    # ── list-diseases ─────────────────────────────────────────
    subparsers.add_parser("list-diseases", help="List available diseases and aliases")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    # ── Dispatch ──────────────────────────────────────────────

    if args.command == "dashboard":
        _cmd_dashboard(args)
    elif args.command == "heart":
        _cmd_heart(args)
    elif args.command == "snapshot":
        _cmd_snapshot(args)
    elif args.command == "list-diseases":
        _cmd_list_diseases()


def _cmd_dashboard(args):
    from src.cli_common import create_creature, resolve_disease
    disease = resolve_disease(args.disease)
    creature = create_creature(disease, args.severity, steps=args.steps)

    if args.live:
        from src.textual_monitor import PatientMonitor
        app = PatientMonitor(creature, disease)
        app.run()
    else:
        from src.ascii_dashboard import build_dashboard
        lines = build_dashboard(creature, use_color=not args.no_color)
        print("\n".join(lines))


def _cmd_heart(args):
    from src.cli_common import create_creature, resolve_disease
    from src.heart_v2 import snapshot, run_interactive

    disease = resolve_disease(args.disease)
    creature = create_creature(disease, args.severity, steps=args.steps)

    if args.once:
        print(snapshot(disease, args.severity, 0, args.frames))
    else:
        run_interactive(disease, args.severity)


def _cmd_snapshot(args):
    from src.cli_common import create_creature, resolve_disease
    from src.ascii_dashboard import build_dashboard

    disease = resolve_disease(args.disease)
    creature = create_creature(disease, args.severity, steps=args.steps)
    use_color = args.format == "ansi"
    lines = build_dashboard(creature, use_color=use_color)
    print("\n".join(lines))


def _cmd_list_diseases():
    from src.cli_common import DISEASE_ALIASES
    from src.diseases import _DISEASE_REGISTRY

    print("Available diseases:")
    print()

    # Full names
    for name in sorted(_DISEASE_REGISTRY.keys()):
        aliases = [k for k, v in DISEASE_ALIASES.items() if v == name]
        alias_str = f" ({', '.join(aliases)})" if aliases else ""
        print(f"  {name}{alias_str}")

    print()
    print("Aliases:")
    for alias, full in sorted(DISEASE_ALIASES.items()):
        print(f"  {alias:8} → {full}")


if __name__ == "__main__":
    main()
