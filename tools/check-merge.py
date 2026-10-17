#!/usr/bin/env python3
"""Validates merge.json (the merged-font build configuration).

Usage: check-merge.py merge.json
Exits 1 with a message on a bad value, else prints OK.
"""

import json
import sys

SCOPES = {"both", "otb", "ttf"}
UPSCALE_SCOPES = {"all", "winners"}


def fail(msg):
    print(f"check-merge: FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def main():
    with open(sys.argv[1], encoding="utf-8") as f:
        cfg = json.load(f)
    if not isinstance(cfg, dict):
        fail("merge.json must hold an object")

    lo = cfg.get("min_size_px")
    hi = cfg.get("max_size_px")
    for name, val in (("min_size_px", lo), ("max_size_px", hi)):
        if not isinstance(val, int) or isinstance(val, bool) or val < 1:
            fail(f"{name} must be a positive int, got {val!r}")
    if lo >= hi:
        fail(f"min_size_px ({lo}) must be < max_size_px ({hi})")
    if hi > 1024:
        fail(f"max_size_px ({hi}) implausibly large (keep <= 1024)")

    if not isinstance(cfg.get("native_beats_scaled"), bool):
        fail("native_beats_scaled must be a boolean")
    if cfg.get("upscale_scope") not in UPSCALE_SCOPES:
        fail(f"upscale_scope must be one of {sorted(UPSCALE_SCOPES)}, "
             f"got {cfg.get('upscale_scope')!r}")

    filler = cfg.get("filler", {})
    if not isinstance(filler, dict):
        fail("filler must be an object")
    if not isinstance(filler.get("enabled"), bool):
        fail("filler.enabled must be a boolean")
    if filler.get("scope") not in SCOPES:
        fail(f"filler.scope must be one of {sorted(SCOPES)}, "
             f"got {filler.get('scope')!r}")

    for key in ("max_strikes", "max_output_mb"):
        val = cfg.get(key, 0)
        if not isinstance(val, int) or isinstance(val, bool) or val < 0:
            fail(f"{key} must be an int >= 0 (0 = disabled), got {val!r}")

    pri = cfg.get("priority")
    if not isinstance(pri, list) or not pri \
            or not all(isinstance(p, str) for p in pri):
        fail("priority must be a non-empty list of package names")
    if len(pri) != len(set(pri)):
        dups = sorted({n for n in pri if pri.count(n) > 1})
        fail(f"priority has duplicates: {dups}")

    print(f"check-merge: OK: {lo}-{hi}px, native_beats_scaled="
          f"{cfg['native_beats_scaled']}, upscale_scope={cfg['upscale_scope']}, "
          f"filler={filler.get('scope')}, {len(pri)} priority entries")


if __name__ == "__main__":
    main()
