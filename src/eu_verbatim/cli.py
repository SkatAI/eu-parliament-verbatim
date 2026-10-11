"""Command line entry point.

    eu-verbatim 2026-10-05
    eu-verbatim --from 2026-10-05 --to 2026-10-08
"""

import argparse
import json
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from .build import build_day
from .client import ApiClient

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid date {value!r}, expected YYYY-MM-DD")


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="eu-verbatim",
        description="Download the verbatim reports of European Parliament plenary sittings as JSON (one file per day).",
    )
    parser.add_argument("date", nargs="?", type=iso_date, help="single sitting date (YYYY-MM-DD)")
    parser.add_argument("--from", dest="from_date", type=iso_date, help="first date of a range (included)")
    parser.add_argument("--to", dest="to_date", type=iso_date, help="last date of a range (included)")
    parser.add_argument("--data-dir", type=Path, default=PROJECT_ROOT / "data", help="output folder (default: data/)")
    parser.add_argument("--logs-dir", type=Path, default=PROJECT_ROOT / "logs", help="API log folder (default: logs/)")
    parser.add_argument("--cache-dir", type=Path, default=PROJECT_ROOT / ".cache", help="MEP/organisation cache")
    parser.add_argument("--no-cache", action="store_true", help="do not use the MEP/organisation cache")
    parser.add_argument("--overwrite", action="store_true", help="rebuild days that already have a JSON file")
    parser.add_argument("--max-requests", type=int, default=480, help="max API requests per 5 minutes (API cap: 500)")
    args = parser.parse_args(argv)

    if args.date and (args.from_date or args.to_date):
        parser.error("give either a single date or --from/--to, not both")
    if not args.date and not (args.from_date and args.to_date):
        parser.error("give a date, or both --from and --to")
    if args.from_date and args.to_date and args.from_date > args.to_date:
        parser.error("--from must be before or equal to --to")
    return args


def setup_logging(logs_dir: Path) -> Path:
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / f"api_{datetime.now():%Y%m%d-%H%M%S}.log"
    handler = logging.FileHandler(log_file, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root = logging.getLogger("eu_verbatim")
    root.setLevel(logging.DEBUG)
    root.addHandler(handler)
    return log_file


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.date:
        days = [args.date]
    else:
        days = [args.from_date + timedelta(n) for n in range((args.to_date - args.from_date).days + 1)]

    log_file = setup_logging(args.logs_dir)
    log = logging.getLogger("eu_verbatim")
    args.data_dir.mkdir(parents=True, exist_ok=True)
    client = ApiClient(max_calls=args.max_requests, cache_dir=None if args.no_cache else args.cache_dir)
    written = 0
    try:
        for day in days:
            out = args.data_dir / f"{day.isoformat()}.json"
            if out.exists() and not args.overwrite:
                print(f"{day}: {out.name} already exists, skipping (use --overwrite to rebuild)")
                continue
            log.info("building %s", day)
            dataset = build_day(day.isoformat(), client)
            if dataset is None:
                print(f"{day}: no plenary session, no file written")
                log.info("%s: no plenary session", day)
                continue
            out.write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8")
            written += 1
            stats = dataset["stats"]
            print(
                f"{day}: {stats['interventions']} interventions in {stats['agenda_items']} agenda items, "
                f"{stats['speakers']} speakers -> {out}"
            )
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130
    finally:
        client.close()
        log.info("done: %d files written, %d API requests", written, client.request_count)
    print(f"{written} file(s) written, {client.request_count} API requests, log: {log_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
