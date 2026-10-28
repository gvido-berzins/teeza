from __future__ import annotations

import json
import shutil
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

from .db import begin_release, finish_release, sha256_file, transaction
from .importers import import_csv, import_lmf, import_tbx, import_tei, import_tmx, import_wordforms


def import_file(connection, *, source_slug: str, path: str | Path, import_format: str,
                version: str, release_date: str | None = None, domain: str | None = None,
                member: str | None = None, options: dict[str, Any] | None = None) -> dict[str, Any]:
    source = connection.execute("SELECT id FROM sources WHERE slug=?", (source_slug,)).fetchone()
    if source is None:
        raise ValueError(f"unknown source {source_slug!r}; run `termlv init` first")
    artifact = Path(path).resolve()
    checksum = sha256_file(artifact)
    duplicate = connection.execute(
        "SELECT id,record_count FROM source_releases WHERE source_id=? AND version=? AND checksum_sha256=?",
        (source["id"], version, checksum),
    ).fetchone()
    if duplicate:
        return {"release_id": duplicate["id"], "record_count": duplicate["record_count"],
                "checksum_sha256": checksum, "unchanged": True}
    actual_path = artifact
    temporary: tempfile.TemporaryDirectory[str] | None = None
    if member:
        temporary = tempfile.TemporaryDirectory(prefix="termlv-")
        with zipfile.ZipFile(artifact) as archive:
            if member not in archive.namelist():
                raise ValueError(f"archive member not found: {member}")
            destination = Path(temporary.name) / Path(member).name
            with archive.open(member) as src, destination.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            actual_path = destination
    try:
        with transaction(connection):
            release_metadata: dict[str, Any] = {"import_options": options or {}}
            if member:
                release_metadata["member"] = member
            release_id = begin_release(connection, int(source["id"]), version, import_format,
                                       release_date=release_date, checksum=checksum,
                                       artifact_path=str(artifact), metadata=release_metadata)
            kwargs = options or {}
            if import_format == "tbx":
                count = import_tbx(connection, release_id, actual_path, domain=domain)
            elif import_format == "csv":
                count = import_csv(connection, release_id, actual_path, **kwargs)
            elif import_format == "tei":
                count = import_tei(connection, release_id, actual_path, **kwargs)
            elif import_format == "lmf":
                count = import_lmf(connection, release_id, actual_path, **kwargs)
            elif import_format == "tmx":
                count = import_tmx(connection, release_id, actual_path, **kwargs)
            elif import_format == "wordforms":
                count = import_wordforms(connection, release_id, actual_path, **kwargs)
            else:
                raise ValueError(f"unsupported import format: {import_format}")
            finish_release(connection, release_id, count)
        return {"release_id": release_id, "record_count": count,
                "checksum_sha256": checksum, "unchanged": False}
    finally:
        if temporary:
            temporary.cleanup()


def check_updates(connection, *, timeout: float = 15.0) -> list[dict[str, Any]]:
    """Use HEAD only on catalogued official URLs; never guesses or scrapes endpoints."""
    results = []
    for row in connection.execute("SELECT slug,update_url,active_release_id FROM sources ORDER BY slug"):
        if not row["update_url"]:
            results.append({"source": row["slug"], "status": "manual_only"})
            continue
        request = urllib.request.Request(row["update_url"], method="HEAD",
                                         headers={"User-Agent": "termlv/0.1 source-update-check"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                results.append({"source": row["slug"], "status": "available",
                                "http_status": response.status,
                                "etag": response.headers.get("ETag"),
                                "last_modified": response.headers.get("Last-Modified"),
                                "content_length": response.headers.get("Content-Length"),
                                "url": response.geturl()})
        except (urllib.error.URLError, TimeoutError) as exc:
            results.append({"source": row["slug"], "status": "unreachable", "error": str(exc)})
    return results


def release_diff(connection, old_release_id: int, new_release_id: int) -> dict[str, Any]:
    query = """SELECT st.language,st.normalized,coalesce(tt.normalized,'') target,
                      st.status,st.is_preferred,coalesce(tt.status,''),coalesce(tt.is_preferred,0),
                      coalesce(c.domain,''),c.status,coalesce(c.approval,''),
                      coalesce(c.definition_en,''),coalesce(c.definition_lv,''),
                      st.grammar_json,coalesce(st.usage_note,''),coalesce(c.source_note,'')
               FROM terms st JOIN concepts c ON c.id=st.concept_id
               LEFT JOIN terms tt ON tt.concept_id=c.id AND tt.language<>st.language
               WHERE c.release_id=?"""
    old = {tuple(row) for row in connection.execute(query, (old_release_id,))}
    new = {tuple(row) for row in connection.execute(query, (new_release_id,))}
    return {"added": len(new - old), "removed": len(old - new), "unchanged": len(old & new),
            "comparison": "term pair plus status, preference, domain, approval, definitions, grammar and notes",
            "added_sample": list(sorted(new - old))[:20], "removed_sample": list(sorted(old - new))[:20]}


def download(url: str, destination: str | Path, *, expected_sha256: str | None = None,
             timeout: float = 120.0) -> dict[str, Any]:
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "termlv/0.1 official-source-downloader"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response, partial.open("wb") as stream:
            shutil.copyfileobj(response, stream)
        checksum = sha256_file(partial)
        if expected_sha256 and checksum.casefold() != expected_sha256.casefold():
            partial.unlink(missing_ok=True)
            raise ValueError("download checksum mismatch")
        partial.replace(target)
        return {"path": str(target), "sha256": checksum, "bytes": target.stat().st_size}
    except Exception:
        partial.unlink(missing_ok=True)
        raise
