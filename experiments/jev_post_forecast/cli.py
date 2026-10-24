"""Command-line entry point for the local experiment."""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

from .pipeline import DEFAULT_TICKERS, ExperimentRunner, require_runtime_credentials
from .report import write_artifacts
from .storage import DEFAULT_ARTIFACT_DIR, DEFAULT_CACHE_DIR, PROJECT_ROOT, JsonCache, load_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the local Jev post-Kronos research experiment")
    parser.add_argument("--mode", choices=("live", "historical", "all", "report-only"), default="all")
    parser.add_argument("--tickers", default=",".join(DEFAULT_TICKERS), help="Comma-separated B3 tickers")
    parser.add_argument("--horizon", type=int, default=10, help="Trading-candle forecast horizon (1-60)")
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--offline", action="store_true", help="Forbid network/model calls and require cached inputs")
    parser.add_argument("--refresh", action="store_true", help="Bypass JSON caches and refresh network/model inputs")
    parser.add_argument("--output", type=Path, help="Artifact directory; defaults to artifacts/jev-post-forecast/<run-id>")
    parser.add_argument("--input", type=Path, help="Saved run.json used by report-only mode")
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR, help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not 1 <= args.horizon <= 60:
        raise SystemExit("--horizon must be between 1 and 60")
    if args.offline and args.refresh:
        raise SystemExit("--offline and --refresh cannot be combined")
    try:
        if args.mode == "report-only":
            if args.input is None:
                raise ValueError("--input PATH/TO/run.json is required for report-only mode")
            input_path = args.input.expanduser().resolve()
            run = load_json(input_path)
            output_dir = args.output.expanduser().resolve() if args.output else input_path.parent
            paths = write_artifacts(run, output_dir, write_run=output_dir != input_path.parent)
        else:
            require_runtime_credentials(args.mode, args.offline)
            tickers = [item.strip().upper() for item in args.tickers.split(",") if item.strip()]
            if not tickers:
                raise ValueError("At least one ticker is required")
            run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            output_dir = args.output.expanduser().resolve() if args.output else DEFAULT_ARTIFACT_DIR / run_id
            cache = JsonCache(args.cache_dir.expanduser().resolve(), offline=args.offline, refresh=args.refresh)
            runner = ExperimentRunner(project_root=PROJECT_ROOT, cache=cache, seed=args.seed)
            run = runner.run(mode=args.mode, tickers=tickers, horizon=args.horizon, run_id=run_id)
            paths = write_artifacts(run, output_dir)
    except Exception as exc:
        print(f"Experiment failed: {exc}", file=sys.stderr)
        return 2
    print(f"Report: {paths['html']}")
    print(f"Run data: {paths['run']}")
    print(f"Candidate CSV: {paths['csv']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
