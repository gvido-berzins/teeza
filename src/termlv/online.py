from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from typing import Any

from .db import utcnow


def _cached(connection, source_slug: str, operation: str, query: str) -> dict[str, Any] | None:
    row = connection.execute(
        """SELECT c.response_json,c.expires_at FROM online_cache c JOIN sources s ON s.id=c.source_id
           WHERE s.slug=? AND c.operation=? AND c.query=?""", (source_slug, operation, query)
    ).fetchone()
    if not row:
        return None
    if row["expires_at"] and datetime.fromisoformat(row["expires_at"]) < datetime.now(UTC):
        return None
    result = json.loads(row["response_json"])
    result["cache"] = "hit"
    return result


def _store(connection, source_slug: str, operation: str, query: str, response: dict[str, Any], days: int = 30) -> None:
    source = connection.execute("SELECT id FROM sources WHERE slug=?", (source_slug,)).fetchone()
    if not source:
        raise ValueError(f"unknown source {source_slug}")
    expires = (datetime.now(UTC) + timedelta(days=days)).replace(microsecond=0).isoformat()
    connection.execute(
        """INSERT INTO online_cache(source_id,operation,query,response_json,retrieved_at,expires_at)
           VALUES(?,?,?,?,?,?) ON CONFLICT(source_id,operation,query) DO UPDATE SET
           response_json=excluded.response_json,retrieved_at=excluded.retrieved_at,expires_at=excluded.expires_at""",
        (source["id"], operation, query, json.dumps(response, ensure_ascii=False), utcnow(), expires),
    )
    connection.commit()


def tezaurs_lookup(connection, query: str, *, mode: str = "exact", limit: int = 20,
                    header_name: str | None = None, api_key: str | None = None,
                    timeout: float = 15.0) -> dict[str, Any]:
    """Call only documented v2 search paths; require provider-supplied auth header configuration."""
    header_name = header_name or os.environ.get("TERMLV_TEZAURS_API_HEADER")
    api_key = api_key or os.environ.get("TERMLV_TEZAURS_API_KEY")
    if not header_name or not api_key:
        raise ValueError(
            "Tēzaurs documents that an API key is required but does not publish its header scheme. "
            "Set TERMLV_TEZAURS_API_HEADER and TERMLV_TEZAURS_API_KEY from provider instructions."
        )
    if mode not in {"exact", "prefix", "inflection"}:
        raise ValueError("mode must be exact, prefix, or inflection")
    operation = {"exact": "search", "prefix": "searchprefix", "inflection": "searchinfl"}[mode]
    cache_key = json.dumps({"q": query, "limit": limit}, ensure_ascii=False, sort_keys=True)
    hit = _cached(connection, "tezaurs-api", operation, cache_key)
    if hit:
        return hit
    url = "https://api.tezaurs.lv/api/v2/" + operation + "?" + urllib.parse.urlencode({"q": query, "limit": limit})
    request = urllib.request.Request(url, headers={header_name: api_key, "Accept": "application/json",
                                                   "User-Agent": "termlv/0.1"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.load(response)
    result = {"source": "tezaurs-api", "source_url": url, "retrieved_at": utcnow(),
              "provenance": "live", "result": payload, "cache": "miss"}
    _store(connection, "tezaurs-api", operation, cache_key, result)
    return result


def morphology_lookup(connection, text: str, *, operation: str = "analyze",
                      guess: bool = False, timeout: float = 15.0) -> dict[str, Any]:
    """Use documented public morphology endpoints; sends only the supplied word/phrase."""
    paths = {"analyze": "analyze_lvs/en", "inflect": "inflect_general_lvs/en"}
    if operation not in paths:
        raise ValueError("operation must be analyze or inflect")
    cache_key = json.dumps({"text": text, "guess": guess}, ensure_ascii=False, sort_keys=True)
    hit = _cached(connection, "tezaurs-api", f"morphology:{operation}", cache_key)
    if hit:
        return hit
    quoted = urllib.parse.quote(text, safe="")
    url = f"https://morpho-api.tezaurs.lv/{paths[operation]}/{quoted}?" + urllib.parse.urlencode(
        {"guess": str(guess).lower()})
    request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "termlv/0.1"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.load(response)
    result = {"source": "tezaurs-morphology-api", "source_url": url, "retrieved_at": utcnow(),
              "provenance": "live", "result": payload, "cache": "miss"}
    _store(connection, "tezaurs-api", f"morphology:{operation}", cache_key, result)
    return result
