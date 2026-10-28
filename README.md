# termlv

`termlv` is an offline-first English–Latvian terminology and translation-assistance system. It stores source releases without flattening conflicts, ranks terms by context and evidence, recognizes multiword expressions, protects technical literals, and reviews terminology consistency. SQLite FTS5 keeps retrieval local and compact.

The tool does not pretend that dictionary substitution is full machine translation. `translate-text` produces an auditable terminology draft; a writer or Codex still supplies natural Latvian syntax and grammar.

## Install and initialize

Python 3.11+ and an SQLite build with FTS5 are required.

The checked-in `./termlv` wrapper works immediately from this repository and selects the populated database automatically:

```sh
./termlv serve --open

# Or use the CLI directly:
./termlv translate-term "penetration testing" --domain cybersecurity
```

The frontend opens at `http://127.0.0.1:8876` and provides dictionary search, term evidence, translation assistance, translation review, consistency checks, glossary overrides and source/release browsing. It binds to loopback by default and ordinary use makes no external requests.

For a conventional installation:

```sh
python -m venv .venv
.venv/bin/pip install -e .
export PATH="$PWD/.venv/bin:$PATH"
export TERMLV_DB="$PWD/data/termlv.sqlite3"
termlv init
```

The delivered workspace database is `data/termlv.sqlite3`. It is intentionally git-ignored because the local ITTEA export has no verified redistribution licence. Change `TERMLV_DB` to keep a private per-user database elsewhere.

## Everyday use

```sh
termlv search-term "privilege escalation" --domain cybersecurity
termlv translate-term "penetration testing" --domain cybersecurity
termlv explain-term "vulnerability assessment" --domain cybersecurity
termlv translate-text "The penetration test found CVE-2026-12345." --domain cybersecurity
termlv review-translation @report.en.txt @report.lv.txt --domain cybersecurity
termlv check-consistency @report.en.txt @report.lv.txt --domain cybersecurity
termlv add-glossary-override "lateral movement" "laterālā pārvietošanās" --domain cybersecurity
termlv list-sources
```

All commands return UTF-8 JSON suitable for Codex and scripts. Search returns a small ranked set; `explain-term` retrieves larger provenance details on demand.

Overrides can be restricted to a local regular-expression context with `--context-pattern`; pass the relevant short context to term lookup with `--context`. Text translation applies scoped overrides against the local source text. When an exact translation-memory sentence exists, `translate-text` returns it separately as `sentence_suggestion`; lemma substitutions remain clearly labeled and include `form_guidance` for grammatical revision.

## Import data

Imports are transactional. A successful import becomes active while the previous release stays available for comparison and rollback.

The explicit acquisition helper verifies publisher MD5 values for the CC datasets and refuses restricted/unclear-licence downloads until acknowledged:

```sh
python scripts/acquire_sources.py --tezaurs --wordnet
python scripts/acquire_sources.py --ittea --acknowledge-restrictions
```

```sh
termlv import termini-ittea-protocols export.tbx \
  --format tbx --version 2026-10-25 --domain "information and communication technology"

termlv import tezaurs-2026-autumn tezaurs_2026_4_tei.xml.zip \
  --format tei --version 2026-autumn --release-date 2026-09-23

termlv import latvian-wordnet-2026-autumn tezaurs_2026_4_lmf.xml.zip \
  --format lmf --version 2026-autumn --release-date 2026-09-23

# Optional large inflection appendix; it is streamed from the ZIP.
termlv import tezaurs-wordforms-2026-autumn tezaurs_2026_4_wordforms_tei.xml.zip \
  --format wordforms --version 2026-autumn --release-date 2026-09-23

termlv import microsoft-terminology MicrosoftTermCollection.zip \
  --member LATVIAN.tbx --format tbx --version 2025-02-06

termlv import iate iate-export.tbx --format tbx --version 2026-10-25
termlv import dgt-tm-2021 volume.tmx --format tmx --version 2021
```

Generic CSV needs `en` and `lv` columns by default; customize with `--en-column`, `--lv-column`, `--delimiter`, and `--domain-column`. XLSX is intentionally treated as a manual conversion path because CSV/TBX preserve the supported fields more predictably without adding a spreadsheet dependency.

Use `termlv release-diff OLD NEW` for a change summary and `termlv rollback SOURCE [--release-id ID]` for rollback. Duplicate version/checksum imports are idempotent.

## Optional online access

`termlv update-sources` only performs HEAD checks against catalogued official URLs; it never downloads implicitly. `termlv morphology WORD --operation analyze|inflect` calls the documented public Tēzaurs morphology service and caches the result. It sends only the supplied word or phrase.

The official Tēzaurs v2 API says an API key is required but does not publish the key-header scheme. After obtaining provider instructions from `api@tezaurs.lv`, set both values explicitly:

```sh
export TERMLV_TEZAURS_API_HEADER='provider-specified-header'
export TERMLV_TEZAURS_API_KEY='secret'
termlv live-lookup ugunsmūris --mode exact
```

No AkadTerm, IATE, or undocumented endpoint is guessed or scraped.

## Local MCP server

```sh
python -m pip install -e '.[mcp]'
termlv-mcp
```

The stdio server exposes `search_term`, `translate_term`, `explain_term`, `translate_text`, `review_translation`, `check_consistency`, `suggest_alternatives`, `add_glossary_override`, `list_sources`, and `update_sources`. Configure it as a local stdio MCP command in the consuming Codex installation. The CLI remains the zero-dependency integration.

See [source status](docs/SOURCES.md), [architecture](docs/ARCHITECTURE.md), and [cybersecurity examples](docs/CYBERSECURITY_EXAMPLES.md).

## Verification

```sh
PYTHONPATH=src python -m unittest discover -s tests -v
```

Tests are network-free. They cover synthetic importer/conflict fixtures plus smoke checks against the delivered populated database.

