from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from ..db import add_concept
from .common import binary_xml, local_name


def _text(node) -> str:
    return " ".join("".join(node.itertext()).split())


def import_tei(connection, release_id: int, path: str | Path, *, limit: int | None = None) -> int:
    """Stream TEI dictionary entries, retaining Latvian lemmas, variants and morphology."""
    count = 0
    with binary_xml(path) as stream:
        for _, entry in ET.iterparse(stream, events=("end",)):
            if local_name(entry.tag) != "entry":
                continue
            forms: list[dict] = []
            definitions: list[str] = []
            synonyms: list[str] = []
            grammar: dict[str, str] = {}
            for form in (node for node in list(entry) if local_name(node.tag) == "form"):
                form_type = (form.attrib.get("type") or "").casefold()
                for orth in (node for node in form.iter() if local_name(node.tag) == "orth"):
                    value = _text(orth)
                    if value:
                        forms.append({"text": value, "is_preferred": not forms and form_type == "lemma",
                                      "status": "unverified"})
                for gram in form.iter():
                    name = local_name(gram.tag)
                    value = _text(gram)
                    if name == "iType" and value:
                        grammar.setdefault("computational", value)
                    elif name == "gram" and value:
                        grammar[gram.attrib.get("type") or "gram"] = value
            for node in entry.iter():
                name, value = local_name(node.tag), _text(node)
                if name == "def" and value:
                    definitions.append(value)
                elif name in {"ref", "mentioned"} and value and (node.attrib.get("type") or "").casefold() in {"syn", "synonym"}:
                    synonyms.append(value)
            known = {item["text"].casefold() for item in forms}
            forms.extend({"text": value, "is_preferred": False, "status": "acceptable"}
                         for value in synonyms if value.casefold() not in known)
            if forms:
                for item in forms:
                    item["part_of_speech"] = grammar.get("Vārdšķira") or grammar.get("pos")
                    item["grammatical_gender"] = grammar.get("Dzimte") or grammar.get("gen")
                    item["grammatical_number"] = grammar.get("Skaitlis") or grammar.get("number")
                    item["grammar"] = grammar
                add_concept(connection, release_id, {"lv": forms, "en": []},
                            source_record_id=entry.attrib.get("{http://www.w3.org/XML/1998/namespace}id") or entry.attrib.get("id"),
                            domain=grammar.get("Joma"),
                            definition_lv=" | ".join(dict.fromkeys(definitions)) or None,
                            status="unverified", raw_json={"grammar": grammar, "synonyms": synonyms})
                count += 1
            entry.clear()
            if limit is not None and count >= limit:
                break
    return count

