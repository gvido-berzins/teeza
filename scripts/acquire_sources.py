#!/usr/bin/env python3
"""Explicit acquisition helper for verified official exports.

Nothing is downloaded unless its flag is supplied. Restricted/unclear-licence
sources are clearly marked and require an additional acknowledgement flag.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import urllib.request
from pathlib import Path

SOURCES = {
    "tezaurs": {
        "url": "https://repository.clarin.lv/repository/xmlui/bitstream/handle/20.500.12574/162/tezaurs_2026_4_tei.xml.zip?sequence=1&isAllowed=y",
        "file": "tezaurs_2026_4_tei.xml.zip",
        "md5": "40668c6d4492b0cf324662937dca9e95",
        "restricted": False,
    },
    "wordnet": {
        "url": "https://repository.clarin.lv/repository/xmlui/bitstream/handle/20.500.12574/162/tezaurs_2026_4_lmf.xml.zip?sequence=3&isAllowed=y",
        "file": "tezaurs_2026_4_lmf.xml.zip",
        "md5": "185be88e0f8463a51623b99f56bab356",
        "restricted": False,
    },
    "ittea": {
        "url": "https://termini.gov.lv/svc/termsvc/collection/export/97?format=tbx&type=full",
        "file": "termini-97-full.tbx",
        "restricted": True,
        "reason": "No portal-wide redistribution licence was verified; keep the export local.",
    },
    "microsoft": {
        "url": "https://download.microsoft.com/download/b/2/d/b2db7a7c-8d33-47f3-b2c1-ee5e6445cf45/MicrosoftTermCollection.zip",
        "file": "MicrosoftTermCollection.zip",
        "restricted": True,
        "reason": "Microsoft licence/notice restrictions apply; do not republish the full material.",
    },
}


def digest(path: Path, algorithm: str) -> str:
    value = hashlib.new(algorithm)
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def fetch(name: str, output: Path, acknowledge_restrictions: bool) -> None:
    source = SOURCES[name]
    if source.get("restricted") and not acknowledge_restrictions:
        raise ValueError(f"{name}: {source['reason']} Pass --acknowledge-restrictions for local acquisition.")
    output.mkdir(parents=True, exist_ok=True)
    target = output / source["file"]
    partial = target.with_suffix(target.suffix + ".part")
    request = urllib.request.Request(source["url"], headers={"User-Agent": "termlv-source-acquisition/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=180) as response, partial.open("wb") as stream:
            while chunk := response.read(1024 * 1024):
                stream.write(chunk)
        if source.get("md5") and digest(partial, "md5") != source["md5"]:
            raise ValueError(f"{name}: publisher MD5 mismatch")
        partial.replace(target)
        print(f"{name}: {target} sha256={digest(target, 'sha256')}")
    except Exception:
        partial.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path(".termlv/downloads"))
    parser.add_argument("--acknowledge-restrictions", action="store_true")
    for name in SOURCES:
        parser.add_argument(f"--{name}", action="store_true")
    args = parser.parse_args()
    selected = [name for name in SOURCES if getattr(args, name)]
    if not selected:
        parser.error("select at least one source flag")
    try:
        for name in selected:
            fetch(name, args.output, args.acknowledge_restrictions)
    except (OSError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

