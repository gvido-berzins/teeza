from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

from ..text import normalize
from .common import binary_xml, local_name


def _text(node) -> str:
    return " ".join("".join(node.itertext()).split())


def import_wordforms(connection, release_id: int, path: str | Path, *, limit: int | None = None) -> int:
    """Stream the optional Tēzaurs wordforms TEI appendix without loading it in memory."""
    count = 0
    with binary_xml(path) as stream:
        for _, entry in ET.iterparse(stream, events=("end",)):
            if local_name(entry.tag) != "entry":
                continue
            forms: list[tuple[str, dict[str, str]]] = []
            lemma: str | None = None
            for form in (node for node in entry.iter() if local_name(node.tag) == "form"):
                orth = next((node for node in form.iter() if local_name(node.tag) == "orth"), None)
                value = _text(orth) if orth is not None else ""
                if not value:
                    continue
                kind = (form.attrib.get("type") or "").casefold()
                attrs = {node.attrib.get("type") or local_name(node.tag): _text(node)
                         for node in form.iter() if local_name(node.tag) in {"gram", "case", "number", "gen", "mood", "tense"}}
                if kind == "lemma" or lemma is None:
                    lemma = value
                forms.append((value, attrs))
            if lemma:
                for value, attrs in forms:
                    connection.execute(
                        "INSERT INTO wordforms(release_id,lemma,form,normalized,attributes_json) VALUES(?,?,?,?,?)",
                        (release_id, lemma, value, normalize(value), json.dumps(attrs, ensure_ascii=False)),
                    )
                    count += 1
                    if limit is not None and count >= limit:
                        break
            entry.clear()
            if limit is not None and count >= limit:
                break
    return count
