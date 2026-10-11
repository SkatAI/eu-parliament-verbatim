"""Assemble the dataset for one sitting day."""

import re
from datetime import datetime, timezone

from .client import BASE_URL, SORT, ApiClient
from .enrich import SpeakerEnricher
from .parse import build_intervention

HTML_URL = "https://www.europarl.europa.eu/doceo/document/{}_EN.html"


def item_numbers(item_id: str | None) -> tuple[int, int | None]:
    """'CRE-10-2026-10-06-ITM-009-07' -> (9, 7); 'CRE-10-2026-10-05-ITM-012' -> (12, None)."""
    match = re.search(r"ITM-(\d+)(?:-(\d+))?$", item_id or "")
    if not match:
        return 10**6, None
    return int(match.group(1)), int(match.group(2)) if match.group(2) else None


def build_day(date: str, client: ApiClient) -> dict | None:
    """Return the dataset for a sitting date, or None when there was no plenary sitting."""
    records = client.speeches_with_text(date)
    if not records:
        return None

    enricher = SpeakerEnricher(client)
    items: dict[str, dict] = {}
    for record in records:
        intervention = build_intervention(record)
        intervention["speaker"] = enricher.speaker(
            intervention["speaker_person_id"], date, intervention["speaker_name_in_transcript"]
        )
        item_id = intervention["agenda_item_id"]
        item = items.setdefault(
            item_id,
            {
                "id": item_id,
                "item_number": item_numbers(item_id)[0],
                "sub_item_number": item_numbers(item_id)[1],
                "title": None,
                "titles": {},
                "url": HTML_URL.format(item_id) if item_id else None,
                "interventions": [],
            },
        )
        labels = record.get("activity_label") or {}
        if labels and not item["titles"]:
            item["titles"] = labels
            item["title"] = labels.get("en") or next(iter(labels.values()))
        item["interventions"].append(intervention)

    agenda = sorted(items.values(), key=lambda i: (i["item_number"], i["sub_item_number"] or 0))
    for item in agenda:
        item["interventions"].sort(key=lambda i: i["order"] if i["order"] is not None else 10**9)

    interventions = [i for item in agenda for i in item["interventions"]]
    term = re.match(r"CRE-(\d+)-", agenda[0]["id"] or "")
    return {
        "date": date,
        "parliamentary_term": int(term.group(1)) if term else None,
        "url": f"https://www.europarl.europa.eu/doceo/document/CRE-{term.group(1)}-{date}_EN.html" if term else None,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": {
            "api": BASE_URL,
            "endpoints": ["/speeches", "/meps", "/corporate-bodies"],
            "speeches_params": {
                "sitting-date": date,
                "sort-by": SORT,
                "include-output": "xml_fragment",
                "language-filter": "mul",
            },
        },
        "stats": {
            "agenda_items": len(agenda),
            "interventions": len(interventions),
            "speakers": len({i["speaker_person_id"] for i in interventions if i["speaker_person_id"]}),
            "words": sum(len(i["text"].split()) for i in interventions),
        },
        "agenda_items": agenda,
    }
