"""Turn /speeches API records into clean interventions in the speaker's original language.

Each record carries its text under recorded_in_a_realization_of[0]["api:xmlFragment"],
a dict of language -> XML. Only the original-language version is the verbatim; the
others are machine translations (their blockContainer xml:lang ends in "-mtec").
Speeches mixing several languages are stored under the "mul" key.
"""

import re
import xml.etree.ElementTree as ET

from .codes import language_code, last_segment

XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"
MACHINE_TRANSLATION = re.compile(r'xml:lang="[^"]*-mtec')


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace(" ", " ")).strip()


def select_original_fragment(realization: dict) -> tuple[str, str]:
    """Return (key, xml) of the fragment holding the original-language verbatim."""
    fragments = realization.get("api:xmlFragment") or {}
    if not fragments:
        return "", ""
    candidates = ["mul"] + [language_code(u) for u in realization.get("originalLanguage", [])]
    for key in candidates:
        xml = fragments.get(key)
        if xml and not MACHINE_TRANSLATION.search(xml):
            return key, xml
    # Fall back to any fragment that is not machine translated.
    for key, xml in fragments.items():
        if not MACHINE_TRANSLATION.search(xml):
            return key, xml
    key = next((k for k in candidates if k in fragments), next(iter(fragments)))
    return key, fragments[key]


def _lang(element: ET.Element, default: str | None) -> str | None:
    return element.get(XML_LANG) or default


def _text(element: ET.Element | None) -> str | None:
    return clean("".join(element.itertext())) if element is not None else None


def parse_fragment(xml: str) -> dict:
    """Extract speaker header and paragraphs (with their language) from an XML fragment.

    <oralStatements> contains <speech>, or <question>/<answer> for blue-card exchanges;
    <communication> holds chair announcements and narrative notes.
    """
    result = {
        "statement_type": None,
        "speaker_label": None,
        "speaker_name": None,
        "speaker_role": None,
        "speaker_process": None,
        "paragraphs": [],
    }
    if not xml:
        return result
    root = ET.fromstring(xml)
    paragraphs = result["paragraphs"]

    if root.tag == "oralStatements":
        for statement in root:
            result["statement_type"] = result["statement_type"] or statement.tag
            statement_lang = _lang(statement, None)
            sender = statement.find("from")
            if sender is not None and result["speaker_label"] is None:
                result["speaker_label"] = _text(sender)
                result["speaker_name"] = _text(sender.find("person"))
                result["speaker_role"] = _text(sender.find("role"))
                result["speaker_process"] = _text(sender.find("process"))
            for block in statement.iter("blockContainer"):
                block_lang = _lang(block, statement_lang)
                for p in block.iter("p"):
                    text = _text(p)
                    if text:
                        paragraphs.append({"lang": block_lang, "text": text})
    else:
        # <communication>: chair announcements ("IN THE CHAIR: ...") and notes ("(The sitting was suspended)").
        result["statement_type"] = root.tag
        lang = _lang(root, None)
        for child in root:
            text = _text(child)
            if text:
                paragraphs.append({"lang": _lang(child, lang), "text": text})
    return result


def build_intervention(record: dict) -> dict:
    """Flatten one /speeches record into an intervention (without speaker enrichment)."""
    realization = (record.get("recorded_in_a_realization_of") or [{}])[0]
    participation = record.get("had_participation") or {}
    persons = participation.get("had_participant_person") or []
    key, xml = select_original_fragment(realization)
    parsed = parse_fragment(xml)
    return {
        "id": record.get("activity_id"),
        "speech_id": realization.get("notation_speechId"),
        "document_id": realization.get("identifier"),
        "agenda_item_id": last_segment(realization.get("is_part_of")),
        "number": realization.get("number"),
        "order": realization.get("numbering"),
        "activity_type": last_segment(record.get("had_activity_type")),
        "statement_type": parsed["statement_type"],
        "participation_role": last_segment(participation.get("participation_role")),
        "start_time": record.get("activity_start_date"),
        "end_time": record.get("activity_end_date"),
        "speaker_person_id": last_segment(persons[0]) if persons else None,
        "speaker_label": parsed["speaker_label"],
        "speaker_name_in_transcript": parsed["speaker_name"],
        "speaker_role_in_transcript": parsed["speaker_role"],
        "speaker_process_in_transcript": parsed["speaker_process"],
        "on_behalf_of_group": last_segment(participation.get("participation_in_name_of")),
        "original_languages": [language_code(u) for u in realization.get("originalLanguage", [])],
        "text_source": key,
        "paragraphs": parsed["paragraphs"],
        "text": "\n\n".join(p["text"] for p in parsed["paragraphs"]),
    }
