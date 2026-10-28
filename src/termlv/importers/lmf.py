from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from ..db import add_concept
from ..text import normalize
from .common import binary_xml, local_name


def _attr(node, *names: str) -> str | None:
    for name in names:
        value = node.attrib.get(name)
        if value:
            return value
    return None


def import_lmf(connection, release_id: int, path: str | Path, *, limit: int | None = None) -> int:
    """Import Global WordNet LMF lexical entries as semantic Latvian records."""
    count = 0
    synset_members: dict[str, list[tuple[int, list[str]]]] = {}
    with binary_xml(path) as stream:
        for _, entry in ET.iterparse(stream, events=("end",)):
            entry_type = local_name(entry.tag)
            if entry_type == "Synset":
                synset_id = _attr(entry, "id")
                definitions = []
                for node in entry.iter():
                    if local_name(node.tag) in {"Definition", "Gloss"}:
                        value = _attr(node, "definition", "gloss") or " ".join("".join(node.itertext()).split())
                        if value:
                            definitions.append(value)
                members = synset_members.get(synset_id or "", [])
                all_lemmas = list(dict.fromkeys(lemma for _, lemmas in members for lemma in lemmas))
                for concept_id, own_lemmas in members:
                    if definitions:
                        connection.execute("UPDATE concepts SET definition_lv=? WHERE id=?",
                                           (" | ".join(dict.fromkeys(definitions)), concept_id))
                    existing = {normalize(value) for value in own_lemmas}
                    for synonym in all_lemmas:
                        if normalize(synonym) in existing:
                            continue
                        connection.execute(
                            """INSERT INTO terms(concept_id,language,text,normalized,is_preferred,status,usage_note)
                               VALUES(?,?,?,?,0,'acceptable','WordNet synset synonym')""",
                            (concept_id, "lv", synonym, normalize(synonym)),
                        )
                entry.clear()
                continue
            if entry_type not in {"LexicalEntry", "LexicalConcept"}:
                continue
            lemmas: list[str] = []
            definitions: list[str] = []
            pos = _attr(entry, "partOfSpeech", "pos")
            sense_ids: list[str] = []
            synset_ids: list[str] = []
            for node in entry.iter():
                name = local_name(node.tag)
                if name in {"Lemma", "WordForm"}:
                    value = _attr(node, "writtenForm", "lemma", "form")
                    if value and value not in lemmas:
                        lemmas.append(value)
                    pos = pos or _attr(node, "partOfSpeech", "pos")
                elif name in {"Definition", "Gloss"}:
                    value = _attr(node, "definition", "gloss") or " ".join("".join(node.itertext()).split())
                    if value:
                        definitions.append(value)
                elif name == "Sense":
                    identifier = _attr(node, "id")
                    if identifier:
                        sense_ids.append(identifier)
                    synset_id = _attr(node, "synset")
                    if synset_id:
                        synset_ids.append(synset_id)
            if lemmas:
                variants = [{"text": term, "is_preferred": i == 0, "part_of_speech": pos,
                             "status": "unverified"} for i, term in enumerate(lemmas)]
                concept_id = add_concept(connection, release_id, {"lv": variants, "en": []},
                                         source_record_id=_attr(entry, "id"),
                                         definition_lv=" | ".join(definitions) or None,
                                         status="unverified",
                                         raw_json={"sense_ids": sense_ids, "synset_ids": synset_ids})
                for synset_id in synset_ids:
                    synset_members.setdefault(synset_id, []).append((concept_id, lemmas))
                count += 1
            entry.clear()
            if limit is not None and count >= limit:
                break
    return count

