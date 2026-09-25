#!/usr/bin/env python3
"""Validates priority.json: exactly all font packages, no duplicates.

Usage: check-priority.py priority.json <expected-name>...
Exits 1 with a message on mismatch, else prints OK.
"""

import json
import sys


def main():
    with open(sys.argv[1], encoding="utf-8") as f:
        pri = json.load(f)["priority"]
    expected = set(sys.argv[2:])
    if len(pri) != len(set(pri)):
        dups = sorted({n for n in pri if pri.count(n) > 1})
        print(f"check-priority: FAIL: duplicates: {dups}", file=sys.stderr)
        sys.exit(1)
    missing = sorted(expected - set(pri))
    extra = sorted(set(pri) - expected)
    if missing or extra:
        print(f"check-priority: FAIL: missing={missing} extra={extra}",
              file=sys.stderr)
        sys.exit(1)
    print(f"check-priority: OK: {len(pri)} fonts prioritized")


if __name__ == "__main__":
    main()
