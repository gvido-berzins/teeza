from __future__ import annotations

import json
import mimetypes
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .catalog import install_catalog
from .db import connect, initialize
from .engine import TerminologyEngine

MAX_BODY = 5 * 1024 * 1024


def _first(query: dict[str, list[str]], name: str, default: str | None = None) -> str | None:
    values = query.get(name)
    return values[0] if values else default


class TerminologyWebServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, handler, db_path: str | Path | None = None):
        super().__init__(address, handler)
        self.db_path = Path(db_path) if db_path else None


class Handler(BaseHTTPRequestHandler):
    server_version = "termlv/0.1"
    sys_version = ""

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[termlv-web] {self.address_string()} {format % args}")

    def _engine(self) -> TerminologyEngine:
        db = connect(self.server.db_path)  # type: ignore[attr-defined]
        return TerminologyEngine(db)

    def _json(self, value: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        payload = json.dumps(value, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(payload)

    def _body(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("invalid Content-Length") from exc
        if length <= 0 or length > MAX_BODY:
            raise ValueError("request body must be between 1 byte and 5 MiB")
        try:
            value = json.loads(self.rfile.read(length))
        except json.JSONDecodeError as exc:
            raise ValueError("invalid JSON body") from exc
        if not isinstance(value, dict):
            raise ValueError("JSON body must be an object")
        return value

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self._api_get(parsed.path, parse_qs(parsed.query))
            return
        self._static(parsed.path)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/"):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            body = self._body()
            helper = self._engine()
            try:
                if parsed.path == "/api/translate-text":
                    result = helper.translate_text(str(body.get("text", "")),
                                                   domain=body.get("domain") or None,
                                                   document_id=body.get("document_id") or None,
                                                   record_history=bool(body.get("record_history", False)))
                elif parsed.path == "/api/review":
                    result = helper.review_translation(str(body.get("source", "")),
                                                       str(body.get("target", "")),
                                                       domain=body.get("domain") or None)
                elif parsed.path == "/api/consistency":
                    result = helper.check_consistency(str(body.get("source", "")),
                                                      str(body.get("target", "")),
                                                      domain=body.get("domain") or None)
                elif parsed.path == "/api/override":
                    source = str(body.get("source", "")).strip()
                    target = str(body.get("target", "")).strip()
                    if not source or not target:
                        raise ValueError("source and target are required")
                    result = helper.add_override(source, target, domain=str(body.get("domain", "")),
                                                 context_pattern=body.get("context_pattern") or None,
                                                 note=body.get("note") or None)
                else:
                    self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
                    return
            finally:
                helper.db.close()
            self._json(result)
        except ValueError as exc:
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:  # prevent local UI crashes from leaking a traceback
            self._json({"error": f"request failed: {type(exc).__name__}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def _api_get(self, path: str, query: dict[str, list[str]]) -> None:
        helper = self._engine()
        try:
            if path == "/api/health":
                result = {"ok": True, "offline": True, "sources": len(helper.list_sources())}
            elif path == "/api/search":
                term = (_first(query, "q", "") or "").strip()
                if not term:
                    raise ValueError("q is required")
                try:
                    limit = min(max(int(_first(query, "limit", "12") or "12"), 1), 50)
                except ValueError as exc:
                    raise ValueError("limit must be an integer") from exc
                result = helper.search_term(
                    term, source_language=_first(query, "from", "en") or "en",
                    target_language=_first(query, "to"), domain=_first(query, "domain"),
                    context=_first(query, "context"), mode=_first(query, "mode", "all") or "all",
                    limit=limit,
                )
            elif path == "/api/explain":
                term = (_first(query, "q", "") or "").strip()
                if not term:
                    raise ValueError("q is required")
                result = helper.explain_term(
                    term, source_language=_first(query, "from", "en") or "en",
                    target_language=_first(query, "to"), domain=_first(query, "domain"),
                    context=_first(query, "context"), limit=12,
                )
            elif path == "/api/sources":
                result = helper.list_sources()
            else:
                self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
                return
            self._json(result)
        except ValueError as exc:
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        finally:
            helper.db.close()

    def _static(self, path: str) -> None:
        requested = "index.html" if path in {"", "/"} else path.lstrip("/")
        if requested not in {"index.html", "styles.css", "app.js"}:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        resource = files("termlv").joinpath("web", requested)
        payload = resource.read_bytes()
        content_type = mimetypes.guess_type(requested)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(payload)


def create_server(host: str = "127.0.0.1", port: int = 8876,
                  db_path: str | Path | None = None) -> TerminologyWebServer:
    db = connect(db_path)
    try:
        initialize(db)
        install_catalog(db)
    finally:
        db.close()
    return TerminologyWebServer((host, port), Handler, db_path)


def serve(host: str = "127.0.0.1", port: int = 8876, db_path: str | Path | None = None,
          *, open_browser: bool = False) -> None:
    server = create_server(host, port, db_path)
    url = f"http://{host}:{server.server_address[1]}"
    print(f"termlv frontend: {url}")
    print("Press Ctrl+C to stop. Normal lookups remain offline.")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
