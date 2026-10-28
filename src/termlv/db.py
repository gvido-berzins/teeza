from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path
from typing import Any, Iterator

from .text import normalize


def utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def default_db_path() -> Path:
    configured = os.environ.get("TERMLV_DB")
    if configured:
        return Path(configured).expanduser()
    data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    return data_home / "termlv" / "termlv.sqlite3"


def connect(path: str | Path | None = None, *, readonly: bool = False) -> sqlite3.Connection:
    db_path = Path(path) if path else default_db_path()
    if not readonly:
        db_path.parent.mkdir(parents=True, exist_ok=True)
    uri = f"file:{db_path}?mode=ro" if readonly else str(db_path)
    connection = sqlite3.connect(uri, uri=readonly)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=5000")
    return connection


def initialize(connection: sqlite3.Connection) -> None:
    schema = files("termlv").joinpath("schema.sql").read_text(encoding="utf-8")
    connection.executescript(schema)
    connection.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('schema_version','1')")
    connection.commit()


@contextmanager
def transaction(connection: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    try:
        connection.execute("BEGIN IMMEDIATE")
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def upsert_source(connection: sqlite3.Connection, source: dict[str, Any]) -> int:
    keys = (
        "slug", "name", "homepage", "authority", "license_name", "license_url",
        "redistribution", "access_method", "formats", "release_date", "last_checked",
        "update_url", "notes",
    )
    defaults = {"authority": "reference", "redistribution": "unknown", "access_method": "manual",
                "formats": [], "homepage": ""}
    values = [json.dumps(source.get(k, defaults.get(k)), ensure_ascii=False) if k == "formats"
              else source.get(k, defaults.get(k)) for k in keys]
    connection.execute(
        f"""INSERT INTO sources({','.join(keys)}) VALUES({','.join('?' for _ in keys)})
        ON CONFLICT(slug) DO UPDATE SET
          name=excluded.name,homepage=excluded.homepage,authority=excluded.authority,
          license_name=excluded.license_name,license_url=excluded.license_url,
          redistribution=excluded.redistribution,access_method=excluded.access_method,
          formats=excluded.formats,release_date=excluded.release_date,
          last_checked=excluded.last_checked,update_url=excluded.update_url,notes=excluded.notes""",
        values,
    )
    return int(connection.execute("SELECT id FROM sources WHERE slug=?", (source["slug"],)).fetchone()[0])


def begin_release(
    connection: sqlite3.Connection, source_id: int, version: str, import_format: str, *,
    release_date: str | None = None, checksum: str | None = None,
    artifact_path: str | None = None, metadata: dict[str, Any] | None = None,
) -> int:
    cursor = connection.execute(
        """INSERT INTO source_releases(source_id,version,release_date,acquired_at,
           checksum_sha256,artifact_path,import_format,metadata_json) VALUES(?,?,?,?,?,?,?,?)""",
        (source_id, version, release_date, utcnow(), checksum, artifact_path, import_format,
         json.dumps(metadata or {}, ensure_ascii=False)),
    )
    return int(cursor.lastrowid)


def finish_release(connection: sqlite3.Connection, release_id: int, count: int) -> None:
    row = connection.execute("SELECT source_id FROM source_releases WHERE id=?", (release_id,)).fetchone()
    if row is None:
        raise ValueError(f"unknown release {release_id}")
    source_id = int(row[0])
    old = connection.execute("SELECT active_release_id FROM sources WHERE id=?", (source_id,)).fetchone()[0]
    connection.execute("UPDATE source_releases SET record_count=? WHERE id=?", (count, release_id))
    connection.execute("UPDATE sources SET active_release_id=? WHERE id=?", (release_id, source_id))
    connection.execute(
        """INSERT INTO update_events(source_id,old_release_id,new_release_id,action,summary_json,created_at)
           VALUES(?,?,?,?,?,?)""",
        (source_id, old, release_id, "activate", json.dumps({"record_count": count}), utcnow()),
    )


def add_concept(
    connection: sqlite3.Connection, release_id: int,
    terms: dict[str, list[dict[str, Any] | str]], **fields: Any,
) -> int:
    allowed = {"source_record_id", "domain", "subdomain", "definition_en", "definition_lv",
               "status", "approval", "source_note", "raw_json"}
    payload = {key: value for key, value in fields.items() if key in allowed}
    if isinstance(payload.get("raw_json"), dict):
        payload["raw_json"] = json.dumps(payload["raw_json"], ensure_ascii=False)
    columns = ["release_id", *payload]
    cursor = connection.execute(
        f"INSERT INTO concepts({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",
        [release_id, *payload.values()],
    )
    concept_id = int(cursor.lastrowid)
    for language, variants in terms.items():
        for index, variant in enumerate(variants):
            item = {"text": variant} if isinstance(variant, str) else variant
            text = str(item["text"]).strip()
            if not text:
                continue
            connection.execute(
                """INSERT INTO terms(concept_id,language,text,normalized,is_preferred,status,
                   part_of_speech,grammatical_gender,grammatical_number,grammar_json,usage_note)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (concept_id, language, text, normalize(text), int(item.get("is_preferred", index == 0)),
                 item.get("status", payload.get("status", "unverified")), item.get("part_of_speech"),
                 item.get("grammatical_gender"), item.get("grammatical_number"),
                 json.dumps(item.get("grammar", {}), ensure_ascii=False), item.get("usage_note")),
            )
    return concept_id


def rollback_source(connection: sqlite3.Connection, slug: str, release_id: int | None = None) -> dict[str, Any]:
    source = connection.execute("SELECT id,active_release_id FROM sources WHERE slug=?", (slug,)).fetchone()
    if source is None:
        raise ValueError(f"unknown source: {slug}")
    if release_id is None:
        target = connection.execute(
            "SELECT id FROM source_releases WHERE source_id=? AND id<>? ORDER BY acquired_at DESC,id DESC LIMIT 1",
            (source["id"], source["active_release_id"]),
        ).fetchone()
        if target is None:
            raise ValueError(f"source {slug} has no previous release")
        release_id = int(target[0])
    valid = connection.execute("SELECT 1 FROM source_releases WHERE id=? AND source_id=?",
                               (release_id, source["id"])).fetchone()
    if not valid:
        raise ValueError(f"release {release_id} does not belong to {slug}")
    old = source["active_release_id"]
    connection.execute("UPDATE sources SET active_release_id=? WHERE id=?", (release_id, source["id"]))
    connection.execute(
        """INSERT INTO update_events(source_id,old_release_id,new_release_id,action,summary_json,created_at)
           VALUES(?,?,?,?,?,?)""",
        (source["id"], old, release_id, "rollback", "{}", utcnow()),
    )
    connection.commit()
    return {"source": slug, "old_release_id": old, "active_release_id": release_id}
