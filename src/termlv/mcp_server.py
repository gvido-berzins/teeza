from __future__ import annotations

from .catalog import install_catalog
from .db import connect, initialize
from .engine import TerminologyEngine
from .updates import check_updates


def build_server():
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise SystemExit("Install the MCP extra first: pip install 'termlv[mcp]'") from exc

    mcp = FastMCP("termlv")

    def engine() -> TerminologyEngine:
        db = connect()
        initialize(db)
        install_catalog(db)
        return TerminologyEngine(db)

    @mcp.tool()
    def search_term(query: str, source_language: str = "en", target_language: str = "lv",
                    domain: str | None = None, context: str | None = None,
                    mode: str = "all", limit: int = 10) -> list[dict]:
        """Search local terminology with exact, prefix and fuzzy ranking."""
        helper = engine()
        try:
            return helper.search_term(query, source_language=source_language,
                                      target_language=target_language, domain=domain, context=context,
                                      mode=mode, limit=limit)
        finally:
            helper.db.close()

    @mcp.tool()
    def translate_term(term: str, domain: str | None = None, source_language: str = "en",
                       target_language: str = "lv", context: str | None = None) -> dict:
        """Choose a sourced equivalent and return competing alternatives."""
        helper = engine()
        try:
            return helper.translate_term(term, source_language=source_language,
                                         target_language=target_language, domain=domain, context=context)
        finally:
            helper.db.close()

    @mcp.tool()
    def explain_term(term: str, domain: str | None = None, source_language: str = "en",
                     target_language: str = "lv", context: str | None = None) -> dict:
        """Return definitions, ambiguity and provenance for a term."""
        helper = engine()
        try:
            return helper.explain_term(term, source_language=source_language,
                                       target_language=target_language, domain=domain, context=context)
        finally:
            helper.db.close()

    @mcp.tool()
    def translate_text(text: str, domain: str | None = None, document_id: str | None = None) -> dict:
        """Produce an offline terminology-substitution draft while preserving identifiers."""
        helper = engine()
        try:
            return helper.translate_text(text, domain=domain, document_id=document_id)
        finally:
            helper.db.close()

    @mcp.tool()
    def review_translation(source_text: str, target_text: str, domain: str | None = None) -> dict:
        """Review whether a Latvian translation uses expected sourced terminology."""
        helper = engine()
        try:
            return helper.review_translation(source_text, target_text, domain=domain)
        finally:
            helper.db.close()

    @mcp.tool()
    def check_consistency(source_text: str, target_text: str, domain: str | None = None) -> dict:
        """Detect missing or competing translations of recognized terms."""
        helper = engine()
        try:
            return helper.check_consistency(source_text, target_text, domain=domain)
        finally:
            helper.db.close()

    @mcp.tool()
    def suggest_alternatives(term: str, domain: str | None = None, limit: int = 10) -> list[dict]:
        """Return ranked alternative Latvian equivalents with attribution."""
        helper = engine()
        try:
            return helper.search_term(term, domain=domain, limit=limit)
        finally:
            helper.db.close()

    @mcp.tool()
    def add_glossary_override(source_text: str, target_text: str, domain: str = "",
                              note: str | None = None, context_pattern: str | None = None) -> dict:
        """Save an explicit user-approved local terminology override."""
        helper = engine()
        try:
            return helper.add_override(source_text, target_text, domain=domain, note=note,
                                       context_pattern=context_pattern)
        finally:
            helper.db.close()

    @mcp.tool()
    def list_sources() -> list[dict]:
        """List source metadata, licences, restrictions and active releases."""
        helper = engine()
        try:
            return helper.list_sources()
        finally:
            helper.db.close()

    @mcp.tool()
    def update_sources() -> list[dict]:
        """Check documented official URLs with HEAD; do not download or modify data."""
        helper = engine()
        try:
            return check_updates(helper.db)
        finally:
            helper.db.close()

    return mcp


def main() -> None:
    build_server().run(transport="stdio")


if __name__ == "__main__":
    main()
