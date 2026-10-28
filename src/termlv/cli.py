from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .catalog import install_catalog
from .db import connect, initialize, rollback_source
from .engine import TerminologyEngine
from .online import morphology_lookup, tezaurs_lookup
from .server import serve
from .updates import check_updates, download, import_file, release_diff


def emit(value) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="termlv", description="Offline EN-LV terminology assistant")
    root.add_argument("--db", type=Path, help="SQLite database (or set TERMLV_DB)")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="Initialize the database and verified source catalog")

    search = commands.add_parser("search-term", aliases=["search"])
    search.add_argument("query")
    search.add_argument("--from", dest="source_language", choices=("en", "lv"), default="en")
    search.add_argument("--to", dest="target_language", choices=("en", "lv"))
    search.add_argument("--domain")
    search.add_argument("--context", help="Short local context used for scoped overrides")
    search.add_argument("--mode", choices=("all", "exact", "prefix", "fuzzy"), default="all")
    search.add_argument("--limit", type=int, default=10)

    for name in ("translate-term", "explain-term", "suggest-alternatives"):
        item = commands.add_parser(name)
        item.add_argument("term")
        item.add_argument("--from", dest="source_language", choices=("en", "lv"), default="en")
        item.add_argument("--to", dest="target_language", choices=("en", "lv"))
        item.add_argument("--domain")
        item.add_argument("--context", help="Short local context used for scoped overrides")
        item.add_argument("--limit", type=int, default=10)

    translate = commands.add_parser("translate-text")
    translate.add_argument("text", nargs="?", help="Text; omit to read stdin")
    translate.add_argument("--domain")
    translate.add_argument("--document-id")
    translate.add_argument("--record-history", action="store_true")

    for name in ("review-translation", "check-consistency"):
        item = commands.add_parser(name)
        item.add_argument("source", help="English source text or @file")
        item.add_argument("target", help="Latvian target text or @file")
        item.add_argument("--domain")

    override = commands.add_parser("add-glossary-override", aliases=["override"])
    override.add_argument("source")
    override.add_argument("target")
    override.add_argument("--domain", default="")
    override.add_argument("--note")
    override.add_argument("--context-pattern", help="Optional regular expression restricting this override")

    commands.add_parser("list-sources", aliases=["sources"])
    commands.add_parser("update-sources", aliases=["check-updates"], help="Online HEAD checks only; never downloads implicitly")

    live = commands.add_parser("live-lookup", help="Optional documented Tēzaurs API lookup; requires provider key settings")
    live.add_argument("query")
    live.add_argument("--mode", choices=("exact", "prefix", "inflection"), default="exact")
    live.add_argument("--limit", type=int, default=20)

    morphology = commands.add_parser("morphology", help="Offline morphology lookup with optional online fallback")
    morphology.add_argument("text")
    morphology.add_argument("--operation", choices=("analyze", "inflect"), default="analyze")
    morphology.add_argument("--guess", action="store_true")
    morphology.add_argument("--online-fallback", action="store_true")

    frontend = commands.add_parser("serve", help="Run the offline local web frontend")
    frontend.add_argument("--host", default="127.0.0.1")
    frontend.add_argument("--port", type=int, default=8876)
    frontend.add_argument("--open", action="store_true", help="Open the frontend in the default browser")

    importer = commands.add_parser("import")
    importer.add_argument("source_slug")
    importer.add_argument("path", type=Path)
    importer.add_argument("--format", required=True, choices=("tbx", "csv", "tei", "lmf", "tmx", "wordforms"))
    importer.add_argument("--version", required=True)
    importer.add_argument("--release-date")
    importer.add_argument("--domain")
    importer.add_argument("--member", help="Exact member path for a multi-file ZIP")
    importer.add_argument("--limit", type=int, help="Test/subset limit for TEI/LMF/TMX")
    importer.add_argument("--en-column", default="en")
    importer.add_argument("--lv-column", default="lv")
    importer.add_argument("--delimiter", default=",")
    importer.add_argument("--domain-column")
    importer.add_argument("--status-column")
    importer.add_argument("--definition-en-column")
    importer.add_argument("--definition-lv-column")

    rollback = commands.add_parser("rollback")
    rollback.add_argument("source_slug")
    rollback.add_argument("--release-id", type=int)

    diff = commands.add_parser("release-diff")
    diff.add_argument("old_release_id", type=int)
    diff.add_argument("new_release_id", type=int)

    fetch = commands.add_parser("download", help="Explicitly download a documented official export URL")
    fetch.add_argument("url")
    fetch.add_argument("destination", type=Path)
    fetch.add_argument("--sha256")
    return root


def read_argument(value: str) -> str:
    if value.startswith("@"):
        return Path(value[1:]).read_text(encoding="utf-8")
    return value


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "download":
        try:
            emit(download(args.url, args.destination, expected_sha256=args.sha256))
            return 0
        except (ValueError, OSError) as exc:
            print(f"termlv: {exc}", file=sys.stderr)
            return 2
    if args.command == "serve":
        try:
            serve(args.host, args.port, args.db, open_browser=args.open)
            return 0
        except OSError as exc:
            print(f"termlv: could not start frontend: {exc}. Try --port 8890", file=sys.stderr)
            return 2
    db = connect(args.db)
    initialize(db)
    install_catalog(db)
    engine = TerminologyEngine(db)
    try:
        if args.command == "init":
            emit({"database": str(args.db or "default"), "sources": len(engine.list_sources())})
        elif args.command in {"search-term", "search"}:
            emit(engine.search_term(args.query, source_language=args.source_language,
                                    target_language=args.target_language, domain=args.domain,
                                    context=args.context, mode=args.mode, limit=args.limit))
        elif args.command == "translate-term":
            emit(engine.translate_term(args.term, source_language=args.source_language,
                                       target_language=args.target_language, domain=args.domain,
                                       context=args.context, limit=args.limit))
        elif args.command == "explain-term":
            emit(engine.explain_term(args.term, source_language=args.source_language,
                                     target_language=args.target_language, domain=args.domain,
                                     context=args.context, limit=args.limit))
        elif args.command == "suggest-alternatives":
            emit(engine.search_term(args.term, source_language=args.source_language,
                                    target_language=args.target_language, domain=args.domain,
                                    context=args.context, mode="all", limit=args.limit))
        elif args.command == "translate-text":
            text = args.text if args.text is not None else sys.stdin.read()
            emit(engine.translate_text(text, domain=args.domain, document_id=args.document_id,
                                       record_history=args.record_history))
        elif args.command == "review-translation":
            emit(engine.review_translation(read_argument(args.source), read_argument(args.target), domain=args.domain))
        elif args.command == "check-consistency":
            emit(engine.check_consistency(read_argument(args.source), read_argument(args.target), domain=args.domain))
        elif args.command in {"add-glossary-override", "override"}:
            emit(engine.add_override(args.source, args.target, domain=args.domain, note=args.note,
                                     context_pattern=args.context_pattern))
        elif args.command in {"list-sources", "sources"}:
            emit(engine.list_sources())
        elif args.command in {"update-sources", "check-updates"}:
            emit(check_updates(db))
        elif args.command == "live-lookup":
            emit(tezaurs_lookup(db, args.query, mode=args.mode, limit=args.limit))
        elif args.command == "morphology":
            local = engine.morphology(args.text)
            if args.online_fallback and not local["wordforms"] and not local["lexical"]:
                emit(morphology_lookup(db, args.text, operation=args.operation, guess=args.guess))
            else:
                emit(local)
        elif args.command == "import":
            options = {}
            if args.limit is not None:
                options["limit"] = args.limit
            if args.format == "csv":
                options.update(en_column=args.en_column, lv_column=args.lv_column,
                               delimiter=args.delimiter, domain_column=args.domain_column,
                               status_column=args.status_column,
                               definition_en_column=args.definition_en_column,
                               definition_lv_column=args.definition_lv_column)
            emit(import_file(db, source_slug=args.source_slug, path=args.path,
                             import_format=args.format, version=args.version,
                             release_date=args.release_date, domain=args.domain,
                             member=args.member, options=options))
        elif args.command == "rollback":
            emit(rollback_source(db, args.source_slug, args.release_id))
        elif args.command == "release-diff":
            emit(release_diff(db, args.old_release_id, args.new_release_id))
        return 0
    except (ValueError, OSError) as exc:
        print(f"termlv: {exc}", file=sys.stderr)
        return 2
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
