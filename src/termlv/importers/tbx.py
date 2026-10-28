from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from ..db import add_concept
from .common import binary_xml, local_name

XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"
TERM_ANNOTATION_RE = re.compile(
    r"\s*\((deprecated|obsolete|abbreviation|admitted|not recommended)\)\s*$", re.IGNORECASE
)


def _type(element) -> str:
    return (element.attrib.get("type") or element.attrib.get("name") or "").casefold()


def _value(element) -> str:
    return " ".join("".join(element.itertext()).split())


def _status(value: str | None) -> str:
    cleaned = (value or "").casefold()
    if any(x in cleaned for x in ("deprecat", "obsolete", "rejected")):
        return "deprecated"
    if any(x in cleaned for x in ("approved", "preferred", "recommended")):
        return "recommended"
    if "admitted" in cleaned or "acceptable" in cleaned:
        return "acceptable"
    return "unverified"


def import_tbx(connection, release_id: int, path: str | Path, *, domain: str | None = None) -> int:
    count = 0
    with binary_xml(path) as stream:
        for _, element in ET.iterparse(stream, events=("end",)):
            if local_name(element.tag) != "termEntry":
                continue
            terms: dict[str, list[dict]] = {"en": [], "lv": []}
            definitions: dict[str, str] = {}
            domains: list[str] = []
            raw_notes: list[dict[str, str]] = []
            for desc in element.iter():
                kind, typ, value = local_name(desc.tag), _type(desc), _value(desc)
                if not value:
                    continue
                if kind in {"descrip", "termNote", "admin"}:
                    raw_notes.append({"tag": kind, "type": typ, "value": value})
                if "subjectfield" in typ or typ in {"domain", "subdomain"}:
                    domains.append(value)
            for langset in (n for n in element.iter() if local_name(n.tag) == "langSet"):
                language = (langset.attrib.get(XML_LANG) or langset.attrib.get("lang") or "").split("-")[0].casefold()
                if language not in terms:
                    continue
                for desc in langset.iter():
                    if local_name(desc.tag) == "descrip" and "definition" in _type(desc):
                        definitions.setdefault(language, _value(desc))
                containers = [n for n in list(langset) if local_name(n.tag) in {"tig", "ntig"}] or [langset]
                for index, container in enumerate(containers):
                    term_node = next((n for n in container.iter() if local_name(n.tag) == "term"), None)
                    if term_node is None or not _value(term_node):
                        continue
                    notes = {_type(n): _value(n) for n in container.iter()
                             if local_name(n.tag) in {"termNote", "admin"} and _type(n)}
                    status_value = notes.get("status") or notes.get("administrative status") or next(
                        (value for key, value in notes.items() if "status" in key), None)
                    status = _status(status_value)
                    original_term = _value(term_node)
                    annotation_match = TERM_ANNOTATION_RE.search(original_term)
                    annotation = annotation_match.group(1).casefold() if annotation_match else None
                    term_text = TERM_ANNOTATION_RE.sub("", original_term).strip()
                    if annotation in {"deprecated", "obsolete", "not recommended"}:
                        status = "deprecated"
                    usage_note = notes.get("usagenote") or notes.get("usage note") or notes.get("context")
                    if annotation:
                        usage_note = "; ".join(filter(None, (usage_note, f"lexical annotation: {annotation}")))
                    terms[language].append({
                        "text": term_text, "is_preferred": index == 0 and status != "deprecated",
                        "status": status,
                        "part_of_speech": notes.get("partofspeech") or notes.get("part of speech"),
                        "grammatical_gender": notes.get("grammaticalgender") or notes.get("grammatical gender"),
                        "grammatical_number": notes.get("grammaticalnumber") or notes.get("grammatical number"),
                        "usage_note": usage_note,
                    })
            if terms["en"] or terms["lv"]:
                statuses = [i["status"] for variants in terms.values() for i in variants]
                concept_status = "recommended" if "recommended" in statuses else (
                    "acceptable" if "acceptable" in statuses else "unverified")
                add_concept(connection, release_id, terms, source_record_id=element.attrib.get("id"),
                            domain=domain or (domains[0] if domains else None),
                            subdomain="; ".join(domains[1:]) or None,
                            definition_en=definitions.get("en"), definition_lv=definitions.get("lv"),
                            status=concept_status, approval="approved" if concept_status == "recommended" else None,
                            raw_json={"notes": raw_notes})
                count += 1
            element.clear()
    return count
