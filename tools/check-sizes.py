#!/usr/bin/env python3
"""Quality gates for sizes.json (runs in `nix flake check`).

Fails on structural problems; content mismatches vs fonts.json are only
reported (see sizes-compare.txt) and never fail the build.
"""

import json
import sys

KNOWN_FORMATS = {"bdf", "pcf", "otb", "otf", "ttf", "ttc", "woff", "woff2",
                 "psf", "fon", "dfont", "fnt"}


def fail(msg):
    print(f"check-sizes: FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def main():
    with open(sys.argv[1], encoding="utf-8") as f:
        db = json.load(f)
    files = db.get("files")
    if not isinstance(files, list) or not files:
        fail("no files list")
    seen = set()
    for e in files:
        for key in ("package", "path", "format", "sha256"):
            if not e.get(key):
                fail(f"missing {key} in {e}")
        if e["format"] not in KNOWN_FORMATS:
            fail(f"unknown format {e['format']} in {e['path']}")
        if e["format"] in ("bdf", "pcf"):
            # Pixel size is mandatory unless the header genuinely lacks it
            # (e.g. leggie.bdf: empty XLFD px field, no PIXEL_SIZE prop).
            # A documented note is required -- silent gaps fail.
            if not isinstance(e.get("pixel_size"), int) and not e.get("parse_note"):
                fail(f"{e['package']}/{e['path']}: no pixel_size and no note")
        for s in e.get("strikes") or []:
            if not isinstance(s, dict) or "ppem" not in s:
                fail(f"bad strike in {e['path']}")
        key = (e["package"], e["path"])
        if key in seen:
            fail(f"duplicate entry {key}")
        seen.add(key)
    pkgs = {e["package"] for e in files}
    print(f"check-sizes: OK: {len(files)} files, {len(pkgs)} packages")


if __name__ == "__main__":
    main()
