#!/usr/bin/env python3
"""Validates upscale.json: known packages only, sane factors/sources.

Value per package is either a list of factors (applies to all native
sizes) or a dict {source_px: [factors]} for selected sizes only.
Factors must be ints >= 2, source sizes positive ints.

Usage: check-upscale.py upscale.json <expected-name>...
Exits 1 with a message on mismatch, else prints OK.
"""

import json
import sys


def fail(msg):
    print(f"check-upscale: FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def check_factors(pkg, factors):
    if (not isinstance(factors, list) or not factors
            or any(not isinstance(x, int) or x < 2 for x in factors)):
        fail(f"{pkg}: factors must be a non-empty list of ints >= 2, "
             f"got {factors!r}")


def main():
    with open(sys.argv[1], encoding="utf-8") as f:
        up = json.load(f).get("upscale")
    if not isinstance(up, dict):
        fail("missing 'upscale' object")
    expected = set(sys.argv[2:])
    unknown = sorted(set(up) - expected)
    if unknown:
        fail(f"unknown packages: {unknown}")
    n = 0
    for pkg, spec in sorted(up.items()):
        if isinstance(spec, list):
            check_factors(pkg, spec)
            n += len(spec)
        elif isinstance(spec, dict) and spec:
            for src, factors in spec.items():
                try:
                    px = int(src)
                except (TypeError, ValueError):
                    px = -1
                if px <= 0:
                    fail(f"{pkg}: source size keys must be positive ints, "
                         f"got {src!r}")
                check_factors(f"{pkg}[{px}]", factors)
                n += len(factors)
        else:
            fail(f"{pkg}: value must be a factor list or "
                 f"{{source_px: [factors]}} dict, got {spec!r}")
    print(f"check-upscale: OK: {len(up)} packages, {n} extra scaled sizes")


if __name__ == "__main__":
    main()
