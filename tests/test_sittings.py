import pytest

from eu_verbatim.client import ApiClient
from eu_verbatim.sittings import list_sittings, sitting_from_record

HELD = {
    "activity_id": "MTG-PL-2026-10-05",
    "activity_date": "2026-10-05",
    "had_activity_type": "def/ep-activities/PLENARY_SITTING",
    "hasLocality": "http://publications.europa.eu/resource/authority/place/FRA_SXB",
    "parliamentary_term": "org/ep-10",
    "activity_label": {"en": "Monday, 5 October 2026"},
    "number_of_attendees": 595,
    "recorded_in_a_realization_of": ["eli/dl/doc/PV-10-2026-10-05"],
}
SCHEDULED = {
    "activity_id": "MTG-PL-2026-11-11",
    "activity_date": "2026-11-11",
    "had_activity_type": "def/ep-activities/PLENARY_SITTING",
    "hasLocality": "http://publications.europa.eu/resource/authority/place/BEL_BRU",
    "parliamentary_term": "org/ep-10",
    "activity_label": {"en": "Wednesday, 11 November 2026"},
}


def test_held_sitting():
    assert sitting_from_record(HELD) == {
        "date": "2026-10-05",
        "weekday": "Monday",
        "id": "MTG-PL-2026-10-05",
        "location": "Strasbourg",
        "parliamentary_term": 10,
        "status": "held",
        "attendees": 595,
        "verbatim_url": "https://www.europarl.europa.eu/doceo/document/CRE-10-2026-10-05_EN.html",
    }


def test_scheduled_sitting():
    sitting = sitting_from_record(SCHEDULED)
    assert sitting["status"] == "scheduled"
    assert sitting["location"] == "Brussels"
    assert sitting["attendees"] is None


@pytest.mark.live
def test_sittings_2026(tmp_path):
    client = ApiClient(cache_dir=tmp_path)
    try:
        sittings = list_sittings(2026, client)
    finally:
        client.close()
    dates = [s["date"] for s in sittings]
    assert dates == sorted(dates)
    assert all(d.startswith("2026-") for d in dates)
    assert {"2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08"} <= set(dates)
    assert "2026-10-04" not in dates
