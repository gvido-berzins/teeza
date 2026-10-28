# Source acquisition and reuse audit

Verified 2026-10-25. “Downloadable” does not imply “redistributable”; the database records those facts separately.

| Source | Verified access and freshness | Formats | Reuse and integration decision |
|---|---|---|---|
| [National Terminology Portal, ITTEA protocols (97)](https://termini.gov.lv/kolekcijas/97) | 6,995 ICT records; official detailed export works at `https://termini.gov.lv/svc/termsvc/collection/export/97?format=tbx&type=full` | detailed/simple TBX, CSV, XLSX | Records say `approved` and contain protocol/ISO usage notes. No portal-wide content licence was found. Local import is supported; do not redistribute the export without confirming rights. |
| [National Terminology Portal, ITTEA database (85)](https://termini.gov.lv/kolekcijas/85) | Separate 4,971-record collection | TBX, CSV, XLSX | Same licensing caution. Do not conflate collections 85 and 97. |
| [Tēzaurs 2026 Autumn](https://repository.clarin.lv/repository/xmlui/handle/20.500.12574/162) | Issued 2026-09-23; 415,514 entries | TEI/XML, wordforms TEI, PostgreSQL, ispell | CC BY-SA 4.0. Core TEI ZIP MD5 `40668c6d4492b0cf324662937dca9e95`. The 12 GB expanded wordforms archive is optional; core TEI is the default lexical import. |
| [Latvian WordNet](https://wordnet.ailab.lv/data/) | Landing page still labels its link Spring 2026, but the newer Autumn LMF is in the CLARIN record above | Global WordNet LMF/XML | CC BY-SA 4.0 under the CLARIN record. Autumn LMF ZIP MD5 `185be88e0f8463a51623b99f56bab356`. Use for sense/semantic evidence, not bilingual approval. |
| [IATE](https://iate.europa.eu/) | Filtered download requires registration/EU Login; generated export remains for seven days | TBX, CSV | Manual authenticated import. Record export filters/time and the accepted Conditions of Use. No public Search API specification was verified. |
| [Microsoft Terminology](https://learn.microsoft.com/en-us/globalization/reference/microsoft-terminology) | Official archive last modified 2025-02-06; verified `LATVIAN.tbx` member | TBX inside ZIP | Local automated import supported, subject to the [Microsoft licence](https://learn.microsoft.com/en-us/globalization/license-agreement). Preserve the required notice. Do not republish the whole corpus/material for others to copy. Vendor usage is not Latvian official approval. |
| [VVC term lists](https://www.vvc.gov.lv/lv/terminu-saraksti) | Individual lists updated into 2026; no bulk interface | mostly PDF/document tables | Manual import after conversion. No bulk API/export or explicit site-wide corpus reuse licence was found. Preserve list title, URL, date, and any actual approval statement. |
| [DGT Translation Memory](https://joint-research-centre.ec.europa.eu/language-technology-resources/dgt-translation-memory_en) | Latest release actually linked is 2021, containing 2020 material; five large volumes | TMX 1.1 (compatible with 1.4b), UTF-16LE | Reusable under Commission Decision 2011/833/EU with required attribution. Post-2011 alignments are automatic rather than manually verified. Import as sentence examples, not approved terms. The official volume host failed DNS resolution from this build environment on 2026-10-25, so no DGT records are bundled; the multi-file ZIP importer is implemented and tested independently. |
| [CERT.LV guide](https://cert.lv/uploads/aktualitates/Celvedis-macibspekiem_20112025.pdf) | November 2025; printed page 26/PDF page 27 has exactly 20 awareness-oriented entries | PDF | No explicit reuse licence was found. Manual/local extraction only; label pairs `institutional_usage`, never approved terminology. |
| [CERT.LV CVD terms](https://cvd.cert.lv/statictexts/view/terms-and-conditions) and [out-of-scope examples](https://cvd.cert.lv/statictexts/view/out-of-scope) | Bilingual platform rules effective 2026-08-01; practical vulnerability wording | HTML | No bulk export or reuse licence. Use for manual contextual evidence. Legal definitions cited from statute should point to statute. |
| [National Cybersecurity Law](https://likumi.lv/ta/id/353390) | In force from 2024-09-01; consolidated text includes 2026 amendments | official HTML | Latvian Copyright Law §6 excludes legislation and official state documents from copyright protection. Statutory definitions may be locally seeded with exact section/consolidation provenance. Do not invent English equivalents. |
| [MK Regulation No. 397](https://likumi.lv/ta/id/361481) | Adopted 2025-06-25, effective 2025-07-02 | official HTML | Reusable official text; valuable legal usage for penetration tests, scanning, MFA, least privilege, segmentation, and incident classification. |
| [AkadTerm](https://www.akadterm.lv/term.php) | Public search UI; no documented API or bulk export found | UI only | Human supplementary lookup only. Do not scrape. |
| [Official Tēzaurs API](https://api.tezaurs.lv/openapi) | v2.0-alpha; exact/prefix/inflection search and entry/sense/lexeme/release operations are documented | JSON | Documentation requires a key requested from `api@tezaurs.lv`, but the public OpenAPI document does not define its header scheme. `termlv` requires the user to configure the provider-specified header and key; it guesses neither. |
| [Tēzaurs morphology service](https://morpho-api.tezaurs.lv/) | Public documented paths for analysis, inflection, tokenization and phrase operations | JSON/text | Optional term-sized calls only, cached locally. Its packaged toolkit has CC BY-NC-SA 4.0 licensing; online service terms were not separately stated. |

## CERT.LV evidence level

The guide directly uses `pikšķerēšana`, `smikšķerēšana`, `vikšķerēšana`, `ļaunprogrammatūra`, `izspiedējvīruss`, `ugunsmūris`, `paroļu pārvaldnieks`, `datu noplūde`, `šifrēšana`, `rezerves kopija`, and `mākoņpakalpojums`. These are institutional usage only unless an independent approved source supports the same pair.

The CVD out-of-scope page uses Latvian wording for CSRF, CORS, CSV injection, open redirect, prototype pollution, privilege escalation, rate limiting, tabnabbing, broken-link hijacking, and social engineering. Because no reuse licence or export exists, the project does not bundle the page or its definitions.

The National Cybersecurity Law defines Latvian concepts such as `ievainojamība`, `kiberapdraudējums`, `kiberdrošības incidents`, `kiberhigiēna`, `kiberrisks`, `kiberuzbrukums`, and `koordinēta ievainojamību atklāšana`. MK Regulation No. 397 establishes official Latvian legal usage including `ielaušanās tests`, `drošības skenēšana`, `daudzfaktoru autentifikācija`, `mazāko privilēģiju princips`, and `kompromitēšanas indikators`. Those texts alone do not establish an English pairing.

## Acquisition policy

- Prefer the listed official export/bitstream. Never crawl a search UI to reconstruct a corpus.
- Verify a provided digest when the publisher supplies one and store SHA-256 for every local artifact.
- Import in a single transaction; the old release remains active if parsing fails.
- Keep raw source IDs, notes, definitions, grammatical fields, record JSON, release metadata, and source-level licensing.
- Large sources are never injected into agent context. Search returns compact ranked rows; raw provenance is retrieved only by `explain-term`.
- Online cache entries retain source URL and retrieval time. Confidential documents stay local; optional services receive only the explicit word or phrase.

