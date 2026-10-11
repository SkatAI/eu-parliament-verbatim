"""List the plenary sittings of a year, from the /meetings endpoint.

    eu-sittings 2026
    eu-sittings 2026 --held --dates-only
"""

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path

from .client import ApiClient
from .cli import PROJECT_ROOT, setup_logging
from .codes import last_segment

PLACES = {"FRA_SXB": "Strasbourg", "BEL_BRU": "Brussels", "LUX_LUX": "Luxembourg"}
VERBATIM_URL = "https://www.europarl.europa.eu/doceo/document/CRE-{term}-{date}_EN.html"


def sitting_from_record(record: dict) -> dict:
    sitting_date = record["activity_date"]
    term = (last_segment(record.get("parliamentary_term")) or "").removeprefix("ep-")
    term = int(term) if term.isdigit() else None
    place = last_segment(record.get("hasLocality"))
    # Sittings that took place have minutes/verbatim records attached; future ones only exist on the calendar.
    held = bool(record.get("recorded_in_a_realization_of"))
    return {
        "date": sitting_date,
        "weekday": date.fromisoformat(sitting_date).strftime("%A"),
        "id": record.get("activity_id"),
        "location": PLACES.get(place, place),
        "parliamentary_term": term,
        "status": "held" if held else "scheduled",
        "attendees": record.get("number_of_attendees"),
        "verbatim_url": VERBATIM_URL.format(term=term, date=sitting_date) if held and term else None,
    }


def list_sittings(year: int, client: ApiClient) -> list[dict]:
    sittings = [
        sitting_from_record(r)
        for r in client.meetings(year)
        if r.get("had_activity_type") == "def/ep-activities/PLENARY_SITTING"
        and r.get("activity_date", "").startswith(f"{year}-")
    ]
    return sorted(sittings, key=lambda s: s["date"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="eu-sittings", description="List the European Parliament plenary sitting days of a year."
    )
    parser.add_argument("year", type=int, help="year, e.g. 2026")
    parser.add_argument("--held", action="store_true", help="only sittings that already took place")
    parser.add_argument("--dates-only", action="store_true", help="print one date per line, nothing else")
    parser.add_argument("--json", type=Path, metavar="PATH", help="also write the list to a JSON file")
    parser.add_argument("--logs-dir", type=Path, default=PROJECT_ROOT / "logs", help="API log folder (default: logs/)")
    args = parser.parse_args(argv)

    log_file = setup_logging(args.logs_dir)
    client = ApiClient()
    try:
        sittings = list_sittings(args.year, client)
    finally:
        client.close()
        logging.getLogger("eu_verbatim").info("eu-sittings %d: %d API requests", args.year, client.request_count)
    if args.held:
        sittings = [s for s in sittings if s["status"] == "held"]

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps({"year": args.year, "sittings": sittings}, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    if args.dates_only:
        print("\n".join(s["date"] for s in sittings))
        return 0

    if not sittings:
        print(f"No plenary sitting found for {args.year}")
        return 0
    for s in sittings:
        print(f"{s['date']}  {s['weekday']:<9}  {s['location']:<10}  {s['status']}")
    held = sum(s["status"] == "held" for s in sittings)
    print(f"\n{len(sittings)} sitting days in {args.year} ({held} held, {len(sittings) - held} scheduled)")
    if args.json:
        print(f"written to {args.json}")
    print(f"log: {log_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
