# Latvian terminology workflow

For English-to-Latvian technical translation or review, query the local terminology system before choosing specialized terms:

```sh
./termlv translate-term "penetration testing" --domain cybersecurity
./termlv explain-term "vulnerability assessment" --domain cybersecurity
./termlv review-translation @source.txt @translation.txt --domain cybersecurity
./termlv check-consistency @source.txt @translation.txt --domain cybersecurity
```

Treat `translate-text` as a terminology-substitution draft, not complete machine translation. Write the Latvian sentence naturally, use source definitions and translation-memory examples as evidence, and explain genuinely ambiguous choices. Prefer user overrides, then applicable approved or legal terminology, then institutional usage; never infer official approval from a source's reputation alone.

Keep code, identifiers, URLs, CVEs, standards, versions, product names, commands, field names, and protocol literals unchanged unless context clearly calls for translation. Do not send confidential documents to live services. Online commands are opt-in and should receive only the missing term or phrase.

The repository wrapper selects the populated local database automatically; `TERMLV_DB` can override it. Run `./termlv list-sources` to inspect licences, freshness, restrictions, and active releases. If a result lacks a target term or has `unverified` status, present it as lexical/contextual evidence rather than an approved translation.

For interactive human use, start the local frontend with `./termlv serve --open`. It binds to `127.0.0.1` and uses the same offline database.

