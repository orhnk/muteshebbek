#!/usr/bin/env python3
"""Validates priority.json: subset of the font packages, no duplicates.

Fonts may be left out of the priority list on purpose: they then win no
size, are never upscaled and drop out of the merge. Only duplicates and
unknown (misspelled) names are errors.

Usage: check-priority.py priority.json <known-name>...
Exits 1 with a message on mismatch, else prints OK.
"""

import json
import sys


def main():
    with open(sys.argv[1], encoding="utf-8") as f:
        pri = json.load(f)["priority"]
    known = set(sys.argv[2:])
    if len(pri) != len(set(pri)):
        dups = sorted({n for n in pri if pri.count(n) > 1})
        print(f"check-priority: FAIL: duplicates: {dups}", file=sys.stderr)
        sys.exit(1)
    extra = sorted(set(pri) - known)
    if extra:
        print(f"check-priority: FAIL: unknown={extra}", file=sys.stderr)
        sys.exit(1)
    missing = sorted(known - set(pri))
    print(f"check-priority: OK: {len(pri)} fonts prioritized"
          + (f", {len(missing)} excluded" if missing else ""))
    if missing:
        print("check-priority: excluded from merge: " + ", ".join(missing))


if __name__ == "__main__":
    main()
