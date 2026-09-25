#!/usr/bin/env python3
"""Validates the merged font against merged-report.json.

Checks: family branding, strike count, and every strike ppem present.
Usage: check-merged.py Muteshebbek.otb merged-report.json
"""

import json
import sys


def fail(msg):
    print(f"check-merged: FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def main():
    from fontTools.ttLib import TTFont
    font = TTFont(sys.argv[1])
    try:
        with open(sys.argv[2], encoding="utf-8") as f:
            report = json.load(f)
        fam = font["name"].getDebugName(16) or font["name"].getDebugName(1)
        if fam != report["family"]:
            fail(f"family {fam!r} != {report['family']!r}")
        if "EBLC" not in font and "CBLC" not in font:
            fail("no bitmap strikes table")
        tag = "EBLC" if "EBLC" in font else "CBLC"
        ppems = sorted({(s.bitmapSizeTable.ppemX, s.bitmapSizeTable.ppemY)
                        for s in font[tag].strikes})
        want = sorted({(s["px"], s["px"]) for s in report["strikes"]})
        if ppems != want:
            fail(f"strikes {ppems} != report {want}")
        print(f"check-merged: OK: {fam}, {len(ppems)} strikes "
              f"{sorted(p for p, _ in ppems)}px")
    finally:
        font.close()


if __name__ == "__main__":
    main()
