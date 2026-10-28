---
name: latvian-terminology
description: Use the local termlv database to translate or review English-Latvian technical, cybersecurity, software, networking, API, report, and formal-business terminology. Do not use for unrelated languages.
---

# Latvian terminology assistance

Query the local database for specialized or potentially ambiguous terms before drafting Latvian prose:

```sh
./termlv translate-term "TERM" --domain cybersecurity
./termlv explain-term "TERM" --domain cybersecurity
```

For a completed document, use `./termlv review-translation` and `./termlv check-consistency` with file arguments (`@path`). Do not paste a confidential full document into an online command. `translate-text` only substitutes recognized terms and is not complete machine translation.

Ranking order is user-approved override, context-applicable legal/approved terminology, institutional or vendor terminology, then lexical and semantic evidence. Preserve competing records and cite the returned source. A `recommended` result is only official when its source record carries approval evidence; never upgrade `institutional_usage` or `unverified` evidence.

Keep identifiers, code, URLs, CVEs, standards, product names, commands, API fields, and numeric specifications unchanged unless translation is clearly appropriate. Prefer natural Latvian syntax over word-by-word replacement and use Tēzaurs/WordNet details for sense checking, not as proof of an English-Latvian official equivalent.

Use `termlv list-sources` when provenance or freshness matters. Optional live lookup is term-sized only and requires documented provider configuration; local lookup remains the default.

When the user wants an interactive dictionary rather than an agent workflow, start the repository-local frontend with `./termlv serve --open`.

