from __future__ import annotations

import io
import zipfile
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO, Iterator


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


@contextmanager
def binary_xml(path: str | Path) -> Iterator[BinaryIO]:
    source = Path(path)
    if source.suffix.casefold() != ".zip":
        with source.open("rb") as stream:
            yield stream
        return
    with zipfile.ZipFile(source) as archive:
        members = [n for n in archive.namelist() if n.casefold().endswith((".xml", ".tbx", ".tmx"))]
        if len(members) != 1:
            raise ValueError(f"expected one XML-like file in {source}, found {len(members)}")
        with archive.open(members[0]) as raw:
            yield io.BufferedReader(raw)
