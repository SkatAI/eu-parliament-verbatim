"""Offline tests: the API fixture for CRE-10-2026-10-05-ITM-012 must reproduce
the verbatim text published on the europarl.europa.eu HTML page."""

import json
import re
from pathlib import Path

import pytest

from eu_verbatim.parse import build_intervention, parse_fragment, select_original_fragment

FIXTURES = Path(__file__).parent / "fixtures"
ITEM = "CRE-10-2026-10-05-ITM-012"


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace(" ", " ")).strip()


@pytest.fixture(scope="module")
def api_records():
    return json.loads((FIXTURES / f"{ITEM}_api.json").read_text())


@pytest.fixture(scope="module")
def html_reference():
    return json.loads((FIXTURES / f"{ITEM}_html.json").read_text())["interventions"]


@pytest.fixture(scope="module")
def interventions(api_records):
    return sorted((build_intervention(r) for r in api_records), key=lambda i: i["order"])


def as_html_paragraphs(intervention: dict) -> list[str]:
    """Render an intervention the way the HTML page does: '<speaker label> – <first paragraph>'."""
    paras = [p["text"] for p in intervention["paragraphs"]]
    return [f"{intervention['speaker_label']} – {paras[0]}", *paras[1:]]


def test_same_number_of_interventions(interventions, html_reference):
    assert len(interventions) == len(html_reference) == 10


def test_first_and_last_interventions(interventions):
    assert as_html_paragraphs(interventions[0])[0].startswith("Przewodnicząca. – Kolejnym punktem porządku")
    assert as_html_paragraphs(interventions[-1]) == ["Przewodnicząca. – Zamykam debatę."]


def test_api_text_matches_html_page(interventions, html_reference):
    for got, expected in zip(interventions, html_reference, strict=True):
        assert [norm(p) for p in as_html_paragraphs(got)] == [norm(p) for p in expected], got["id"]


def test_original_language_is_used(interventions):
    by_speaker = {i["speaker_label"].split(",")[0]: i for i in interventions}
    assert by_speaker["Viktória Ferenc"]["original_languages"] == ["hu"]
    assert {p["lang"] for p in by_speaker["Viktória Ferenc"]["paragraphs"]} == {"hu"}
    # Halicki switches from English to Polish mid-speech: the multilingual fragment is used.
    halicki = by_speaker["Andrzej Halicki"]
    assert halicki["text_source"] == "mul"
    assert [p["lang"] for p in halicki["paragraphs"]] == ["en", "en", "pl", "pl", "pl"]


def test_no_machine_translation_selected(api_records):
    for record in api_records:
        key, xml = select_original_fragment(record["recorded_in_a_realization_of"][0])
        assert "-mtec" not in xml, key


def test_word_timestamps_are_stripped():
    xml = (
        '<oralStatements><speech xml:lang="de"><from xml:lang="de"><person refersTo="epdata:person/1">A B</person>.'
        '</from><blockContainer><p><recordedTime time="t" type="startEvent"/><time time="t1">Frau</time> '
        '<time time="t2">Präsidentin!</time><recordedTime time="t" type="endEvent"/></p></blockContainer>'
        "</speech></oralStatements>"
    )
    parsed = parse_fragment(xml)
    assert parsed["speaker_label"] == "A B."
    assert parsed["paragraphs"] == [{"lang": "de", "text": "Frau Präsidentin!"}]


def test_intervention_metadata(interventions):
    neuhoff = interventions[-2]
    assert neuhoff["speaker_person_id"] == "256944"
    assert neuhoff["on_behalf_of_group"] == "ESN"
    assert neuhoff["agenda_item_id"] == ITEM
    assert neuhoff["start_time"] == "2026-10-05T17:48:07.999+02:00"
    assert neuhoff["activity_type"] == "PLENARY_DEBATE_SPEECH"


def test_blue_card_question_and_answer_are_parsed():
    xml = (
        '<oralStatements><question xml:lang="fr"><from xml:lang="fr" xml:space="preserve">'
        '<person refersTo="epdata:person/256875">Matthieu Valet</person> '
        '(<organization refersTo="epdata:org/7150">PfE</organization>), '
        '<process refersTo="">question «carton bleu»</process>.</from>'
        "<blockContainer><p>Monsieur Smith, ...</p></blockContainer></question></oralStatements>"
    )
    parsed = parse_fragment(xml)
    assert parsed["statement_type"] == "question"
    assert parsed["speaker_label"] == "Matthieu Valet (PfE), question «carton bleu»."
    assert parsed["speaker_process"] == "question «carton bleu»"
    assert parsed["paragraphs"] == [{"lang": "fr", "text": "Monsieur Smith, ..."}]
