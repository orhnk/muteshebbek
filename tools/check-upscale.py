#!/usr/bin/env python3
"""Validates upscale.json: known packages only, integer factors >= 2.

Usage: check-upscale.py upscale.json <expected-name>...
Exits 1 with a message on mismatch, else prints OK.
"""

import json
import sys


def fail(msg):
    print(f"check-upscale: FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def main():
    with open(sys.argv[1], encoding="utf-8") as f:
        up = json.load(f).get("upscale")
    if not isinstance(up, dict):
        fail("missing 'upscale' object")
    expected = set(sys.argv[2:])
    unknown = sorted(set(up) - expected)
    if unknown:
        fail(f"unknown packages: {unknown}")
    for pkg, factors in sorted(up.items()):
        if (not isinstance(factors, list) or not factors
                or any(not isinstance(x, int) or x < 2 for x in factors)):
            fail(f"{pkg}: factors must be a non-empty list of ints >= 2, "
                 f"got {factors!r}")
    n = sum(len(v) for v in up.values())
    print(f"check-upscale: OK: {len(up)} packages, {n} extra scaled sizes")


if __name__ == "__main__":
    main()
