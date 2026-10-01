#!/usr/bin/env python3
"""Validates the outline TTF compatibility layer.

The OTB is an sfnt whose scalable glyphs are blank, so apps that ignore
embedded bitmap strikes (EBLC/EBDT) draw nothing. This check proves the
companion .ttf carries real outlines for every covered glyph AND still
ships the bitmap strikes (so bitmap-aware renderers keep the native size).

Renders the test string with bitmaps disabled (FT_LOAD_NO_BITMAP) at every
strike size to prove the outlines actually produce ink.

Usage: check-ttf.py Muteshebbek.ttf merged-report.json
Requires: fonttools, freetype-py
"""

import json
import sys

TEST_STRING = "Hello World 0123 Il1O0[]{}"


def fail(msg):
    print(f"check-ttf: FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def main():
    from fontTools.ttLib import TTFont

    path, report_path = sys.argv[1], sys.argv[2]
    with open(report_path, encoding="utf-8") as f:
        report = json.load(f)

    font = TTFont(path)
    try:
        if "glyf" not in font:
            fail("no glyf table (outlines missing)")
        if "EBLC" not in font and "CBLC" not in font:
            fail("no bitmap strike table (bitmaps must stay in the TTF)")
        fam = font["name"].getDebugName(16) or font["name"].getDebugName(1)
        if fam != report["family"]:
            fail(f"family {fam!r} != report {report['family']!r}")
        glyf = font["glyf"]
        cmap = font.getBestCmap()
        blank = []
        for ch in TEST_STRING:
            if ch == " ":  # space legitimately has no ink
                continue
            name = cmap.get(ord(ch))
            if name is None or not glyf[name].numberOfContours:
                blank.append(ch)
        if blank:
            fail("no outline for test glyph(s): " + " ".join(blank))
        outlined = sum(1 for name in cmap.values()
                       if glyf[name].numberOfContours)
        if outlined < 0.5 * len(cmap):
            fail(f"only {outlined}/{len(cmap)} mapped glyphs have outlines")
        print(f"check-ttf: outlines for {outlined}/{len(cmap)} mapped glyphs")
    finally:
        font.close()

    import freetype

    face = freetype.Face(path)
    flags = (freetype.FT_LOAD_RENDER | freetype.FT_LOAD_TARGET_MONO
             | freetype.FT_LOAD_NO_BITMAP)
    for s in report["strikes"]:
        px = s["px"]
        face.set_pixel_sizes(0, px)
        ink = 0
        for ch in TEST_STRING:
            try:
                face.load_char(ch, flags)
            except freetype.ft_errors.FT_Exception as exc:  # noqa: BLE001
                fail(f"{px}px cannot load {ch!r}: {exc}")
            ink += sum(1 for b in bytes(face.glyph.bitmap.buffer) if b)
        if not ink:
            fail(f"{px}px: no ink from outlines with bitmaps disabled")
        print(f"check-ttf: {px:>3}px outlines render ({ink} ink bytes)")
    print(f"check-ttf: OK: TTF outlines work without bitmap support "
          f"({len(report['strikes'])} sizes)")


if __name__ == "__main__":
    main()
