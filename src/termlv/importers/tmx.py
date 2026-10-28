from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from .common import local_name

XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"


def import_tmx(connection, release_id: int, path: str | Path, *, source_language: str = "en",
               target_language: str = "lv", limit: int | None = None) -> int:
    source = Path(path)
    count = 0

    def parse(stream, document_hint: str | None = None) -> int:
        nonlocal count
        for _, unit in ET.iterparse(stream, events=("end",)):
            if local_name(unit.tag) != "tu":
                continue
            segments: dict[str, str] = {}
            for tuv in (n for n in unit if local_name(n.tag) == "tuv"):
                language = (tuv.attrib.get(XML_LANG) or tuv.attrib.get("lang") or "").split("-")[0].casefold()
                seg = next((n for n in tuv.iter() if local_name(n.tag) == "seg"), None)
                if seg is not None:
                    segments[language] = " ".join("".join(seg.itertext()).split())
            if segments.get(source_language) and segments.get(target_language):
                connection.execute(
                    """INSERT INTO examples(release_id,source_language,target_language,source_text,target_text,document_id)
                       VALUES(?,?,?,?,?,?)""",
                    (release_id, source_language, target_language, segments[source_language], segments[target_language],
                     unit.attrib.get("tuid") or document_hint),
                )
                count += 1
            unit.clear()
            if limit is not None and count >= limit:
                break
        return count

    if source.suffix.casefold() == ".zip":
        with zipfile.ZipFile(source) as archive:
            members = [name for name in archive.namelist() if name.casefold().endswith(".tmx")]
            if not members:
                raise ValueError(f"no TMX files found in {source}")
            for member in members:
                with archive.open(member) as stream:
                    parse(stream, Path(member).stem)
                if limit is not None and count >= limit:
                    break
    else:
        with source.open("rb") as stream:
            parse(stream)
    return count
