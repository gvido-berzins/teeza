# Architecture

## Data model

`sources` stores authority, access, licence and redistribution independently. `source_releases` is immutable; `sources.active_release_id` selects the current release and makes rollback a pointer change. `concepts` retain source IDs, definitions, domains, approval evidence, and raw structured notes. `terms` retains every language variant and its own preferred/status/grammar fields. Translation-memory examples, user overrides, history, live cache and update events are separate tables.

FTS5 indexes term text and examples. Exact lookup uses a normalized B-tree index, prefix lookup uses escaped `LIKE`, and fuzzy lookup applies bounded similarity only to active terms sharing an initial. This avoids loading dictionaries into agent context.

## Ranking

The ranking is deterministic and inspectable:

1. Exact user-approved override.
2. Exact before prefix before fuzzy match.
3. Legal definition and approved terminology before legal/institutional/vendor usage.
4. Matching domain bonus.
5. Recommended/preferred bonus and strong deprecated penalty.

Source authority never changes a record's explicit status. A result cannot become “officially approved” merely because it ranks first.

## Translation assistance

`translate-text` recognizes longest multiword expressions first, excludes overlapping matches, and protects URLs, CVEs, common standard identifiers, versions and code-like spans. It substitutes only recognized sourced terms and emits every choice. It deliberately leaves surrounding English untouched rather than fabricating a fluent translation.

`review-translation` checks whether expected terms appear in the target. `check-consistency` detects competing target renderings. Translation memory is a separate sentence-example signal and does not grant terminology approval.

## Import/update safety

TBX, TEI, LMF and TMX use streaming XML parsing. CSV is row-streamed. ZIP inputs are read without permanent expansion when they contain one XML member; multi-file archives require an exact `--member`. Imports are transactional, checksummed and idempotent by source/version/checksum. Update checks are read-only HEAD requests to catalogued URLs. Downloading always requires an explicit command.

## Known boundaries

- Natural Latvian sentence generation is outside the zero-dependency engine. Codex uses the evidence to write/revise prose.
- Offline inflection quality depends on imported Tēzaurs grammatical data. The optional morphology service improves word forms but is never called implicitly.
- XLSX/PDF/DOC sources use explicit manual conversion because robust parsing would otherwise add large dependencies and risk silently losing structure.
- IATE authentication and Conditions of Use prevent unattended bootstrap.
- AkadTerm and VVC expose no verified bulk API.

