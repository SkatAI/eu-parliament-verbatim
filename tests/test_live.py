"""Live tests against the European Parliament Open Data API (run with: uv run pytest -m live)."""

import json
from pathlib import Path

import pytest

from eu_verbatim.build import build_day
from eu_verbatim.client import ApiClient
from test_parse import as_html_paragraphs, norm

pytestmark = pytest.mark.live

FIXTURES = Path(__file__).parent / "fixtures"
DATE = "2026-10-05"
ITEM = "CRE-10-2026-10-05-ITM-012"


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    c = ApiClient(cache_dir=tmp_path_factory.mktemp("cache"))
    yield c
    c.close()


@pytest.fixture(scope="module")
def day(client):
    return build_day(DATE, client)


def test_no_session_returns_none(client):
    assert build_day("2026-10-04", client) is None  # Sunday


def test_all_records_retrieved(day, client):
    ids = client.speech_ids_for_date(DATE)
    got = [i["id"] for item in day["agenda_items"] for i in item["interventions"]]
    assert sorted(got) == sorted(ids)


def test_every_intervention_has_text(day):
    empty = [i["id"] for item in day["agenda_items"] for i in item["interventions"] if not i["text"]]
    assert empty == []


def test_debate_matches_html_page(day):
    item = next(i for i in day["agenda_items"] if i["id"] == ITEM)
    assert item["title"] == "Humanitarian situation in Ukraine (debate)"
    expected = json.loads((FIXTURES / f"{ITEM}_html.json").read_text())["interventions"]
    assert len(item["interventions"]) == len(expected)
    for got, paragraphs in zip(item["interventions"], expected, strict=True):
        assert [norm(p) for p in as_html_paragraphs(got)] == [norm(p) for p in paragraphs]


def test_speakers_are_enriched(day):
    item = next(i for i in day["agenda_items"] if i["id"] == ITEM)
    halicki = item["interventions"][1]["speaker"]
    assert halicki["first_name"] == "Andrzej"
    assert halicki["last_name"] == "Halicki"
    assert halicki["nationality"] == {"code": "POL", "name": "Poland"}
    assert halicki["political_group"]["label"] == "PPE"
    neuhoff = item["interventions"][-2]["speaker"]
    assert (neuhoff["first_name"], neuhoff["last_name"]) == ("Hans", "Neuhoff")
    assert neuhoff["nationality"]["code"] == "DEU"
    assert neuhoff["political_group"]["label"] == "ESN"
