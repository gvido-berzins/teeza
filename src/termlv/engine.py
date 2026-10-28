from __future__ import annotations

from bisect import insort
import json
import re
import sqlite3
from difflib import SequenceMatcher
from typing import Any

from .db import utcnow
from .text import normalize, overlaps, protected_spans

AUTHORITY_WEIGHT = {
    "legal_definition": 65,
    "approved_terminology": 60,
    "legal_usage": 55,
    "institutional_terminology": 45,
    "vendor_terminology": 35,
    "institutional_usage": 30,
    "translation_memory": 15,
    "lexical_reference": 12,
    "semantic_reference": 10,
    "morphology_reference": 10,
    "reference": 5,
}
STATUS_WEIGHT = {"recommended": 30, "acceptable": 15, "unverified": 0, "deprecated": -80}

DOMAIN_ALIASES = {
    "cybersecurity": ("cybersecurity", "information and communication technology", "information technology",
                      "informatics", "network", "web security", "security"),
    "software engineering": ("software engineering", "software", "information technology", "informatics"),
    "networking": ("networking", "network", "telecommunication", "information and communication technology"),
    "api": ("api", "software", "information technology", "web security"),
}

ENGLISH_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "by", "for", "from",
    "has", "have", "in", "is", "it", "of", "on", "or", "that", "the", "this",
    "to", "was", "were", "with", "without",
}


def _fuzzy_typo_match(query: str, candidate: str) -> bool:
    """Accept typo recovery, but reject semantically different near-neighbours."""
    query_words = normalize(query).split()
    candidate_words = normalize(candidate).split()
    if len(query_words) != len(candidate_words):
        return False
    if SequenceMatcher(None, normalize(query), normalize(candidate)).ratio() < 0.78:
        return False
    return all(SequenceMatcher(None, left, right).ratio() >= 0.72
               for left, right in zip(query_words, candidate_words))


def _case_compatible(phrase: str, source_term: str) -> bool:
    """Do not apply acronym records such as IS/AND to ordinary lowercase prose."""
    phrase_words = re.findall(r"[^\W_]+", phrase, re.UNICODE)
    source_words = re.findall(r"[^\W_]+", source_term, re.UNICODE)
    for observed, recorded in zip(phrase_words, source_words):
        letters = "".join(character for character in recorded if character.isalpha())
        if len(letters) >= 2 and letters.isupper() and not observed.isupper():
            return False
    return True


def _domain_aliases(domain: str) -> tuple[str, ...]:
    cleaned = domain.casefold().strip()
    return DOMAIN_ALIASES.get(cleaned, (cleaned,))


class TerminologyEngine:
    def __init__(self, connection: sqlite3.Connection):
        self.db = connection

    def _active_clause(self) -> str:
        return "s.active_release_id=c.release_id"

    def search_term(self, query: str, *, source_language: str = "en", target_language: str | None = None,
                    domain: str | None = None, context: str | None = None,
                    mode: str = "all", limit: int = 10) -> list[dict[str, Any]]:
        target_language = target_language or ("lv" if source_language == "en" else "en")
        normalized = normalize(query)
        candidates: list[dict[str, Any]] = []

        overrides = self.db.execute(
            """SELECT id,source_text,target_text,domain,note,context_pattern FROM glossary_overrides
               WHERE source_language=? AND target_language=? AND source_normalized=?
                 AND (? IS NULL OR domain='' OR domain=?)""",
            (source_language, target_language, normalized, domain, domain),
        ).fetchall()
        for row in overrides:
            if row["context_pattern"]:
                if context is None:
                    continue
                try:
                    if not re.search(row["context_pattern"], context, re.IGNORECASE):
                        continue
                except re.error:
                    continue
            candidates.append({"source_term": row["source_text"], "target_term": row["target_text"],
                               "domain": row["domain"] or None, "status": "recommended",
                               "authority": "user_override", "source": "user-glossary",
                               "source_url": None, "definition_preview": None, "usage_note": row["note"],
                               "approval": "user-approved", "match": "exact", "score": 1000.0,
                               "concept_id": None, "source_record_id": f"override:{row['id']}"})

        sql = f"""
            SELECT st.text source_term,tt.text target_term,st.normalized,st.status source_status,
                   st.is_preferred source_is_preferred,st.usage_note,
                   tt.status target_status,tt.is_preferred target_is_preferred,tt.usage_note target_usage_note,
                   c.id concept_id,c.source_record_id,c.domain,c.subdomain,
                   c.definition_en,c.definition_lv,c.status concept_status,c.approval,
                   s.slug source,s.name source_name,s.homepage source_url,s.authority
            FROM terms st
            JOIN concepts c ON c.id=st.concept_id
            JOIN source_releases r ON r.id=c.release_id
            JOIN sources s ON s.id=r.source_id
            LEFT JOIN terms tt ON tt.concept_id=c.id AND tt.language=?
            WHERE st.language=? AND {self._active_clause()}
        """
        params: list[Any] = [target_language, source_language]
        if mode == "exact":
            sql += " AND st.normalized=?"
            params.append(normalized)
        elif mode == "prefix":
            sql += " AND st.normalized LIKE ? ESCAPE '\\'"
            params.append(normalized.replace("%", "\\%").replace("_", "\\_") + "%")
        else:
            sql += " AND (st.normalized=? OR st.normalized LIKE ? ESCAPE '\\')"
            params.extend([normalized, normalized.replace("%", "\\%").replace("_", "\\_") + "%"])
        if domain:
            aliases = _domain_aliases(domain)
            sql += " AND (c.domain IS NULL OR " + " OR ".join("lower(c.domain) LIKE ?" for _ in aliases) + ")"
            params.extend(f"%{alias}%" for alias in aliases)
        sql += " ORDER BY (tt.text IS NULL),st.normalized=? DESC,tt.is_preferred DESC,st.is_preferred DESC LIMIT ?"
        params.extend([normalized, max(limit * 8, 40)])
        rows = self.db.execute(sql, params).fetchall()

        if mode in {"all", "fuzzy"} and len(rows) < limit:
            fuzzy_sql = f"""SELECT st.text source_term,tt.text target_term,st.normalized,st.status source_status,
                       st.is_preferred source_is_preferred,st.usage_note,
                       tt.status target_status,tt.is_preferred target_is_preferred,tt.usage_note target_usage_note,
                       c.id concept_id,c.source_record_id,c.domain,c.subdomain,
                       c.definition_en,c.definition_lv,c.status concept_status,c.approval,
                       s.slug source,s.name source_name,s.homepage source_url,s.authority
                    FROM terms st JOIN concepts c ON c.id=st.concept_id
                    JOIN source_releases r ON r.id=c.release_id JOIN sources s ON s.id=r.source_id
                    LEFT JOIN terms tt ON tt.concept_id=c.id AND tt.language=?
                    WHERE st.language=? AND {self._active_clause()}
                      AND substr(st.normalized,1,1)=substr(?,1,1)"""
            fuzzy_params: list[Any] = [target_language, source_language, normalized]
            if domain:
                aliases = _domain_aliases(domain)
                fuzzy_sql += " AND (c.domain IS NULL OR " + " OR ".join(
                    "lower(c.domain) LIKE ?" for _ in aliases) + ")"
                fuzzy_params.extend(f"%{alias}%" for alias in aliases)
            fuzzy_sql += " ORDER BY (tt.text IS NULL),abs(length(st.normalized)-length(?)),st.normalized LIMIT 8000"
            fuzzy_params.append(len(normalized))
            fuzzy_rows = self.db.execute(fuzzy_sql, fuzzy_params).fetchall()
            seen = {(r["concept_id"], r["source_term"], r["target_term"]) for r in rows}
            scored_fuzzy = []
            for row in fuzzy_rows:
                key = (row["concept_id"], row["source_term"], row["target_term"])
                if key in seen:
                    continue
                similarity = SequenceMatcher(None, normalized, row["normalized"]).ratio()
                # Fuzzy search is typo recovery, not semantic substitution. A high
                # threshold prevents e.g. "vulnerability assessment" from silently
                # becoming "vulnerability scanner".
                if _fuzzy_typo_match(normalized, row["normalized"]):
                    scored_fuzzy.append((similarity, row))
            rows = [*rows, *(row for _, row in sorted(scored_fuzzy, reverse=True, key=lambda item: item[0])[:limit * 4])]

        for row in rows:
            match = "exact" if row["normalized"] == normalized else (
                "prefix" if row["normalized"].startswith(normalized) else "fuzzy")
            similarity = SequenceMatcher(None, normalized, row["normalized"]).ratio()
            score = {"exact": 300, "prefix": 220, "fuzzy": 120 * similarity}[match]
            score += AUTHORITY_WEIGHT.get(row["authority"], 0)
            candidate_status = row["target_status"] or row["source_status"]
            effective_status = ("deprecated" if row["source_status"] == "deprecated" else candidate_status)
            candidate_preferred = (row["target_is_preferred"] if row["target_term"] is not None
                                   else row["source_is_preferred"])
            score += STATUS_WEIGHT.get(effective_status, 0)
            score += 8 if candidate_preferred and effective_status != "deprecated" else 0
            if domain and row["domain"]:
                row_domain = row["domain"].casefold()
                if domain.casefold() in row_domain:
                    # A directly applicable domain can outweigh a more authoritative
                    # record from a different technical subfield.
                    score += 90
                elif any(alias in row_domain for alias in _domain_aliases(domain)):
                    score += 15
            definition = row["definition_lv"] if target_language == "lv" else row["definition_en"]
            definition_preview = None
            if definition:
                definition_preview = definition if len(definition) <= 240 else definition[:237].rstrip() + "..."
            usage_notes = list(dict.fromkeys(note for note in (row["target_usage_note"], row["usage_note"]) if note))
            candidates.append({
                "source_term": row["source_term"], "target_term": row["target_term"],
                "domain": row["domain"], "subdomain": row["subdomain"],
                "status": effective_status, "source_status": row["source_status"],
                "target_status": row["target_status"], "authority": row["authority"],
                "source": row["source"], "source_name": row["source_name"],
                "source_url": row["source_url"],
                "definition_preview": definition_preview,
                "usage_note": " | ".join(usage_notes) or None, "approval": row["approval"],
                "match": match, "score": round(score, 2), "concept_id": row["concept_id"],
                "source_record_id": row["source_record_id"],
            })
        candidates.sort(key=lambda item: (item["target_term"] is None, -item["score"], item["target_term"] or ""))
        return candidates[:limit]

    def translate_term(self, term: str, **options: Any) -> dict[str, Any]:
        results = self.search_term(term, **options)
        selected = next((result for result in results if result.get("target_term")), None)
        alternatives = [result for result in results if result is not selected]
        return {"query": term, "selected": selected,
                "alternatives": alternatives, "ambiguous": self._ambiguous(results)}

    @staticmethod
    def _ambiguous(results: list[dict[str, Any]]) -> bool:
        viable = [r for r in results if r.get("target_term") and r.get("status") != "deprecated"]
        return len({normalize(r["target_term"]) for r in viable[:4]}) > 1 and (
            len(viable) > 1 and viable[0]["score"] - viable[1]["score"] < 35)

    def explain_term(self, term: str, **options: Any) -> dict[str, Any]:
        result = self.translate_term(term, **options)
        concept_ids = [r["concept_id"] for r in [result.get("selected"), *result["alternatives"]]
                       if r and r.get("concept_id")]
        details = []
        for concept_id in dict.fromkeys(concept_ids):
            row = self.db.execute("SELECT raw_json,definition_en,definition_lv,source_note FROM concepts WHERE id=?",
                                  (concept_id,)).fetchone()
            details.append({"concept_id": concept_id, "definition_en": row["definition_en"],
                            "definition_lv": row["definition_lv"], "source_note": row["source_note"],
                            "provenance_record": json.loads(row["raw_json"] or "{}")})
        result["details"] = details
        return result

    def _recognize(self, text: str, source_language: str, domain: str | None) -> list[dict[str, Any]]:
        tokens = list(re.finditer(r"[^\W_]+(?:[-'][^\W_]+)*", text, re.UNICODE))
        protected = protected_spans(text)
        recognized: list[dict[str, Any]] = []
        occupied: list[tuple[int, int]] = []
        ngrams: list[tuple[tuple[int, int], str, tuple[str, ...]]] = []
        for size in range(min(8, len(tokens)), 0, -1):
            for start in range(0, len(tokens) - size + 1):
                span = (tokens[start].start(), tokens[start + size - 1].end())
                if overlaps(span, protected):
                    continue
                phrase = text[span[0]:span[1]]
                variants = [normalize(phrase)]
                if re.search(r"[-‐‑–—]", phrase):
                    variants.append(normalize(re.sub(r"[-‐‑–—]+", " ", phrase)))
                ngrams.append((span, phrase, tuple(dict.fromkeys(variants))))

        normalized_candidates = list(dict.fromkeys(value for _, _, variants in ngrams for value in variants))
        available: set[str] = set()
        for start in range(0, len(normalized_candidates), 400):
            chunk = normalized_candidates[start:start + 400]
            placeholders = ",".join("?" for _ in chunk)
            rows = self.db.execute(
                f"""SELECT DISTINCT st.normalized FROM terms st JOIN concepts c ON c.id=st.concept_id
                    JOIN source_releases r ON r.id=c.release_id JOIN sources s ON s.id=r.source_id
                    WHERE st.language=? AND s.active_release_id=c.release_id
                      AND st.normalized IN ({placeholders})""",
                [source_language, *chunk],
            ).fetchall()
            available.update(row[0] for row in rows)
        override_rows = self.db.execute(
            "SELECT source_normalized FROM glossary_overrides WHERE source_language=?",
            (source_language,),
        ).fetchall()
        available.update(row[0] for row in override_rows)

        for span, phrase, variants in ngrams:
            if overlaps(span, occupied) or not any(value in available for value in variants):
                continue
            if normalize(phrase) in ENGLISH_STOPWORDS:
                continue
            lookup_phrase = phrase
            if normalize(phrase) not in available:
                lookup_phrase = re.sub(r"[-‐‑–—]+", " ", phrase)
            results = self.search_term(lookup_phrase, source_language=source_language, domain=domain,
                                       context=text, mode="exact", limit=5)
            candidate = next((result for result in results if result.get("target_term")), None)
            if candidate and not _case_compatible(phrase, candidate["source_term"]):
                candidate = None
            if candidate:
                alternatives = [result for result in results if result is not candidate]
                recognized.append({"span": span, "text": phrase, "candidate": candidate,
                                   "alternatives": alternatives, "ambiguous": self._ambiguous(results)})
                insort(occupied, span)
        return sorted(recognized, key=lambda item: item["span"][0])

    def translate_text(self, text: str, *, source_language: str = "en", target_language: str = "lv",
                       domain: str | None = None, document_id: str | None = None,
                       record_history: bool = False) -> dict[str, Any]:
        recognized = self._recognize(text, source_language, domain)
        draft = text
        for item in reversed(recognized):
            start, end = item["span"]
            draft = draft[:start] + item["candidate"]["target_term"] + draft[end:]
        choices = [{"source": item["text"], "target": item["candidate"]["target_term"],
                    "source_name": item["candidate"]["source"], "status": item["candidate"]["status"],
                    "ambiguous": item["ambiguous"], "span": item["span"]} for item in recognized]
        form_guidance = []
        for choice in choices:
            morphology = self.morphology(choice["target"], limit=5)
            lexical_guidance = []
            seen_guidance = set()
            for item in morphology["lexical"]:
                if not item["grammar"] and not item["part_of_speech"]:
                    continue
                key = (item["part_of_speech"], item["grammatical_gender"], item["grammatical_number"],
                       json.dumps(item["grammar"], ensure_ascii=False, sort_keys=True))
                if key not in seen_guidance:
                    seen_guidance.add(key)
                    lexical_guidance.append(item)
            form_guidance.append({"term": choice["target"],
                                  "requires_contextual_inflection": True,
                                  "lexical": lexical_guidance[:3],
                                  "wordforms": morphology["wordforms"][:5]})
        memory = self.translation_memory(text, limit=3)
        exact_memory = next((item for item in memory if normalize(item["source_text"]) == normalize(text)), None)
        result = {"draft": draft, "mode": "terminology_substitution",
                  "warning": "This is a terminology-assisted draft, not full machine translation.",
                  "choices": choices, "protected": [text[a:b] for a, b in protected_spans(text)],
                  "form_guidance": form_guidance,
                  "sentence_suggestion": exact_memory["target_text"] if exact_memory else None,
                  "translation_memory": memory}
        if record_history:
            self.db.execute(
                """INSERT INTO translation_history(document_id,source_language,target_language,source_text,
                   target_text,choices_json,created_at) VALUES(?,?,?,?,?,?,?)""",
                (document_id, source_language, target_language, text, draft,
                 json.dumps(choices, ensure_ascii=False), utcnow()),
            )
            self.db.commit()
        return result

    def review_translation(self, source_text: str, target_text: str, *, domain: str | None = None) -> dict[str, Any]:
        expected = self._recognize(source_text, "en", domain)
        target_space = self._target_search_space(target_text)
        target_terms = {
            result["target_term"]
            for item in expected
            for result in (item["candidate"], *item["alternatives"])
            if result.get("target_term")
        }
        target_counts = {
            term: self._count_term(target_space, term)
            for term in target_terms
        }
        issues = []
        for item in expected:
            preferred = item["candidate"]["target_term"]
            alternatives = [r["target_term"] for r in item["alternatives"] if r.get("target_term")]
            if not target_counts.get(preferred, 0):
                used = next((alt for alt in alternatives if target_counts.get(alt, 0)), None)
                issues.append({"type": "nonpreferred_term" if used else "missing_term",
                               "source": item["text"], "expected": preferred, "found": used,
                               "authority": item["candidate"]["authority"],
                               "source_name": item["candidate"]["source"]})
        return {"ok": not issues, "issues": issues, "checked_terms": len(expected)}

    def check_consistency(self, source_text: str, target_text: str, *, domain: str | None = None) -> dict[str, Any]:
        occurrences: dict[str, dict[str, Any]] = {}
        target_space = self._target_search_space(target_text)
        recognized = self._recognize(source_text, "en", domain)
        target_terms = {
            result["target_term"]
            for item in recognized
            for result in (item["candidate"], *item["alternatives"])
            if result.get("target_term")
        }
        target_counts = {
            term: self._count_term(target_space, term)
            for term in target_terms
        }
        for item in recognized:
            key = normalize(item["text"])
            data = occurrences.setdefault(key, {"source": item["text"], "expected": item["candidate"]["target_term"],
                                                "count": 0, "variants_found": []})
            data["count"] += 1
            candidates = [item["candidate"], *item["alternatives"]]
            data["variants_found"].extend(r["target_term"] for r in candidates
                                          if r.get("target_term") and target_counts.get(r["target_term"], 0))
        issues = []
        for data in occurrences.values():
            data["variants_found"] = sorted(set(data["variants_found"]))
            if len(data["variants_found"]) > 1:
                issues.append({"type": "competing_translations", **data})
            elif not data["variants_found"]:
                issues.append({"type": "term_not_found_in_target", **data})
            elif sum(target_counts.get(variant, 0) for variant in data["variants_found"]) < data["count"]:
                issues.append({"type": "missing_term_occurrences", **data})
        return {"ok": not issues, "issues": issues, "terms": list(occurrences.values())}

    @staticmethod
    def _contains_term(normalized_text: str, term: str) -> bool:
        return TerminologyEngine._count_term(normalized_text, term) > 0

    @staticmethod
    def _count_term(normalized_text: str, term: str) -> int:
        needle = normalize(term)
        if not needle:
            return 0
        count = 0
        offset = 0
        while True:
            start = normalized_text.find(needle, offset)
            if start < 0:
                return count
            end = start + len(needle)
            left_boundary = start == 0 or not (
                normalized_text[start - 1].isalnum()
                or normalized_text[start - 1] == "_"
            )
            right_boundary = end == len(normalized_text) or not (
                normalized_text[end].isalnum()
                or normalized_text[end] == "_"
            )
            if left_boundary and right_boundary:
                count += 1
            offset = start + 1

    def _target_search_space(self, target_text: str) -> str:
        """Add locally known lemmas so inflected target words satisfy terminology checks."""
        base = normalize(target_text)
        tokens = re.findall(r"[^\W_]+", base, re.UNICODE)
        unique_tokens = list(dict.fromkeys(tokens))
        lemma_map: dict[str, list[str]] = {}
        for start in range(0, len(unique_tokens), 500):
            chunk = unique_tokens[start:start + 500]
            if not chunk:
                continue
            placeholders = ",".join("?" for _ in chunk)
            rows = self.db.execute(
                f"""SELECT DISTINCT w.normalized,w.lemma FROM wordforms w
                    JOIN source_releases r ON r.id=w.release_id JOIN sources s ON s.id=r.source_id
                    WHERE w.normalized IN ({placeholders}) AND s.active_release_id=w.release_id""", chunk
            ).fetchall()
            for row in rows:
                lemma_map.setdefault(row[0], []).append(normalize(row[1]))
        lemmas = [lemma for token in tokens for lemma in lemma_map.get(token, [])]
        return base + (" " + " ".join(lemmas) if lemmas else "")

    def add_override(self, source_text: str, target_text: str, *, source_language: str = "en",
                     target_language: str = "lv", domain: str = "", context_pattern: str | None = None,
                     note: str | None = None) -> dict[str, Any]:
        self.db.execute(
            """INSERT INTO glossary_overrides(source_language,target_language,source_text,source_normalized,
               target_text,domain,context_pattern,note,approved_at) VALUES(?,?,?,?,?,?,?,?,?)
               ON CONFLICT(source_language,target_language,source_normalized,domain) DO UPDATE SET
                 source_text=excluded.source_text,target_text=excluded.target_text,
                 context_pattern=excluded.context_pattern,note=excluded.note,approved_at=excluded.approved_at""",
            (source_language, target_language, source_text, normalize(source_text), target_text, domain,
             context_pattern, note, utcnow()),
        )
        self.db.commit()
        return {"source_text": source_text, "target_text": target_text, "domain": domain,
                "status": "user-approved"}

    def list_sources(self) -> list[dict[str, Any]]:
        rows = self.db.execute(
            """SELECT s.*,r.version active_version,r.record_count,r.checksum_sha256,r.acquired_at
               FROM sources s LEFT JOIN source_releases r ON r.id=s.active_release_id ORDER BY s.name"""
        ).fetchall()
        results = []
        for row in rows:
            item = dict(row)
            item["formats"] = json.loads(item["formats"] or "[]")
            results.append(item)
        return results

    def translation_memory(self, text: str, limit: int = 5) -> list[dict[str, Any]]:
        tokens = [t for t in re.findall(r"[^\W_]+", normalize(text)) if len(t) > 2]
        if not tokens:
            return []
        query = " OR ".join(f'"{t.replace(chr(34), chr(34) * 2)}"' for t in tokens[:12])
        try:
            rows = self.db.execute(
                """SELECT e.source_text,e.target_text,e.context,s.slug source,s.homepage source_url,bm25(examples_fts) rank
                   FROM examples_fts JOIN examples e ON e.id=examples_fts.rowid
                   JOIN source_releases r ON r.id=e.release_id JOIN sources s ON s.id=r.source_id
                   WHERE examples_fts MATCH ? AND s.active_release_id=e.release_id ORDER BY rank LIMIT ?""",
                (query, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            return []
        return [dict(row) for row in rows]

    def morphology(self, text: str, limit: int = 50) -> dict[str, Any]:
        normalized = normalize(text)
        rows = self.db.execute(
            """SELECT w.lemma,w.form,w.attributes_json,s.slug source,s.homepage source_url
               FROM wordforms w JOIN source_releases r ON r.id=w.release_id
               JOIN sources s ON s.id=r.source_id
               WHERE w.normalized=? AND s.active_release_id=w.release_id LIMIT ?""",
            (normalized, limit),
        ).fetchall()
        lexical = self.db.execute(
            f"""SELECT t.text,t.part_of_speech,t.grammatical_gender,t.grammatical_number,
                      t.grammar_json,s.slug source,s.homepage source_url
                 FROM terms t JOIN concepts c ON c.id=t.concept_id
                 JOIN source_releases r ON r.id=c.release_id JOIN sources s ON s.id=r.source_id
                 WHERE t.language='lv' AND t.normalized=? AND {self._active_clause()}
                 ORDER BY (t.grammar_json<>'{{}}') DESC,(t.part_of_speech IS NOT NULL) DESC LIMIT ?""",
            (normalized, limit),
        ).fetchall()
        return {
            "query": text,
            "wordforms": [{**dict(row), "attributes": json.loads(row["attributes_json"] or "{}")}
                          for row in rows],
            "lexical": [{**dict(row), "grammar": json.loads(row["grammar_json"] or "{}")}
                        for row in lexical],
            "offline": True,
        }
