import argparse
from pathlib import Path

from bioflow.core.logging import setup_logging, event
from bioflow.core.version import ENGINE_VERSION
from bioflow.engine.runner import run_template_from_json_file, run_template_by_db_id

DEFAULT_DB = Path("data/bioflow.db")


def main():
    setup_logging()
    event("engine_boot", engine_version=ENGINE_VERSION)

    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=False)

    run_file = sub.add_parser("run-file")
    run_file.add_argument("json_path")
    run_file.add_argument("--db", default=str(DEFAULT_DB))
    run_file.add_argument("--dt", type=float, default=0.01)
    run_file.add_argument("--duration", type=float, default=1.0)
    run_file.add_argument("--sample-rate", type=float, default=10.0)

    run_id = sub.add_parser("run-id")
    run_id.add_argument("template_id", type=int)
    run_id.add_argument("--db", default=str(DEFAULT_DB))
    run_id.add_argument("--dt", type=float, default=0.01)
    run_id.add_argument("--duration", type=float, default=1.0)
    run_id.add_argument("--sample-rate", type=float, default=10.0)

    args = p.parse_args()

    if args.cmd is None:
        return

    if args.cmd == "run-file":
        out = run_template_from_json_file(
            json_path=args.json_path,
            db_path=args.db,
            dt=args.dt,
            duration_s=args.duration,
            sample_rate_hz=args.sample_rate,
        )
        print(out)

    if args.cmd == "run-id":
        out = run_template_by_db_id(
            template_id=args.template_id,
            db_path=args.db,
            dt=args.dt,
            duration_s=args.duration,
            sample_rate_hz=args.sample_rate,
        )
        print(out)


if __name__ == "__main__":
    main()
