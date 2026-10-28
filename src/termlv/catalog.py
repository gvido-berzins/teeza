from __future__ import annotations

import json
from importlib.resources import files

from .db import upsert_source


def load_catalog() -> list[dict]:
    return json.loads(files("termlv").joinpath("sources.json").read_text(encoding="utf-8"))


def install_catalog(connection) -> int:
    for source in load_catalog():
        upsert_source(connection, source)
    connection.commit()
    return len(load_catalog())

