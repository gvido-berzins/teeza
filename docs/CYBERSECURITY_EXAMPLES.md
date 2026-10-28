# Cybersecurity report examples

These examples show the desired workflow, not claims that every sentence is an official translation.

## Finding

English:

> Penetration testing identified a privilege-escalation vulnerability in the API. Exploitation required authentication but not administrative authorization. CVE-2026-12345 and `/api/v2/users/{id}` must remain unchanged.

Terminology evidence to query:

```sh
termlv translate-term "penetration testing" --domain cybersecurity
termlv translate-term "privilege escalation" --domain cybersecurity
termlv translate-term "vulnerability" --domain cybersecurity
termlv translate-term "exploitation" --domain cybersecurity
termlv translate-term "authentication" --domain cybersecurity
termlv translate-term "authorization" --domain cybersecurity
```

Natural Latvian draft after applying evidence:

> Ielaušanās testēšanā tika atklāta API ievainojamība, kas ļauj paaugstināt privilēģijas. Lai ievainojamību izmantotu, bija jāautentificējas, taču administratora autorizācija nebija nepieciešama. CVE-2026-12345 un `/api/v2/users/{id}` jāatstāj nemainīti.

The sentence restructures “privilege-escalation vulnerability” rather than forcing a word-for-word compound.

## Remediation

English:

> Enforce authorization on every object access, apply least privilege, rotate exposed credentials, and add rate limiting. Retest the remediation before deployment.

Possible Latvian draft:

> Veiciet autorizācijas pārbaudi ikreiz, kad notiek piekļuve objektam, ievērojiet mazāko privilēģiju principu, nomainiet atklātos piekļuves datus un ierobežojiet pieprasījumu biežumu. Pirms izmaiņu izvietošanas atkārtoti pārbaudiet, vai ievainojamība ir novērsta.

Use `explain-term` when `credentials`, `rate limiting`, `deployment`, or `remediation` has multiple context-dependent renderings.

## Consistency pass

```sh
termlv review-translation @finding.en.txt @finding.lv.txt --domain cybersecurity
termlv check-consistency @finding.en.txt @finding.lv.txt --domain cybersecurity
```

If the client mandates another rendering, save it as a scoped override rather than altering an imported source record.

