from __future__ import annotations

from bisect import bisect_left
import re
import unicodedata

PROTECTED_RE = re.compile(
    r"(?:https?://[^\s,;!?()<>]+(?<![.])|\bCVE-\d{4}-\d{4,}\b|\b(?:RFC|ISO|IEC|NIST)\s*[-:]?\s*\d[\w.-]*\b|"
    r"\b(?-i:[A-Z]{2,}[A-Z0-9.-]*|[0-9]+FA)\b|`[^`]+`|"
    r"\b(?-i:[A-Z][a-z0-9]+(?:[A-Z][A-Za-z0-9]*)+)\b|"
    r"\b[A-Za-z_][A-Za-z0-9_.:/-]*\([^\n)]*\)|"
    r"\b[A-Za-z0-9_.-]+(?:[/\\][A-Za-z0-9_.{}*:-]+)+\b|"
    r"\b[A-Za-z0-9_-]+\.(?:cs|java|cpp|h|json|xml|config|md|py|js|ts|dll|exe|asmx|svc)\b|"
    r"\b\d+(?:\.\d+){1,3}\b)",
    re.IGNORECASE,
)


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFC", value).casefold().strip()
    value = re.sub(r"[\s\u00a0]+", " ", value)
    return value


def fts_query(value: str, prefix: bool = False) -> str:
    tokens = re.findall(r"[^\W_]+", normalize(value), re.UNICODE)
    if not tokens:
        return '""'
    escaped = [token.replace('"', '""') for token in tokens]
    if prefix:
        return " AND ".join(f'"{token}"*' for token in escaped)
    return " AND ".join(f'"{token}"' for token in escaped)


def protected_spans(text: str) -> list[tuple[int, int]]:
    return [match.span() for match in PROTECTED_RE.finditer(text)]


def overlaps(span: tuple[int, int], protected: list[tuple[int, int]]) -> bool:
    """Return whether *span* overlaps sorted, non-overlapping protected spans.

    ``protected_spans`` already returns intervals in this form.  Recognition
    keeps its occupied intervals in the same order, so a binary predecessor
    lookup replaces the former full scan for every generated n-gram.
    """
    if not protected or span[0] >= span[1]:
        return False
    index = bisect_left(protected, (span[1],))
    if index == 0:
        return False
    start, end = protected[index - 1]
    return span[0] < end and span[1] > start
