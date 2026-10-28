from __future__ import annotations

import csv
from pathlib import Path

from ..db import add_concept


def import_csv(connection, release_id: int, path: str | Path, *, en_column: str = "en",
               lv_column: str = "lv", delimiter: str = ",", domain_column: str | None = None,
               definition_en_column: str | None = None, definition_lv_column: str | None = None,
               status_column: str | None = None, encoding: str = "utf-8-sig") -> int:
    count = 0
    with Path(path).open(encoding=encoding, newline="") as stream:
        reader = csv.DictReader(stream, delimiter=delimiter)
        if not reader.fieldnames or en_column not in reader.fieldnames or lv_column not in reader.fieldnames:
            raise ValueError(f"CSV must contain columns {en_column!r} and {lv_column!r}")
        for row_number, row in enumerate(reader, start=2):
            en, lv = (row.get(en_column) or "").strip(), (row.get(lv_column) or "").strip()
            if not en and not lv:
                continue
            raw_status = ((row.get(status_column) if status_column else "") or "").casefold()
            status = raw_status if raw_status in {"recommended", "acceptable", "deprecated", "unverified"} else "unverified"
            add_concept(connection, release_id, {"en": [en] if en else [], "lv": [lv] if lv else []},
                        source_record_id=str(row_number), domain=row.get(domain_column) if domain_column else None,
                        definition_en=row.get(definition_en_column) if definition_en_column else None,
                        definition_lv=row.get(definition_lv_column) if definition_lv_column else None,
                        status=status, raw_json=row)
            count += 1
    return count
