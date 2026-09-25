#!/usr/bin/env python3
"""Render proof: every strike must rasterize 100% crisp (no gray pixels).

A gray pixel would mean FreeType scaled an outline instead of using the
native bitmap strike. Exits 1 on any antialiasing or empty rendering.
Usage: check-render.py Muteshebbek.otb merged-report.json
"""

import sys

TEST_STRING = "Hello World 0123 Il1O0[]{}"


def main():
    from PIL import Image, ImageDraw, ImageFont
    with open(sys.argv[2], encoding="utf-8") as f:
        import json
        report = json.load(f)
    failures = []
    for s in report["strikes"]:
        px = s["px"]
        font = ImageFont.truetype(sys.argv[1], px)
        img = Image.new("L", (1200, 300), 255)
        ImageDraw.Draw(img).text((5, 5), TEST_STRING, font=font, fill=0,
                                 anchor="lt")
        data = list(img.getdata())
        black = sum(1 for v in data if v == 0)
        gray = sum(1 for v in data if v not in (0, 255))
        status = "crisp" if black and not gray else "FAIL"
        print(f"check-render: {px:>3}px black={black:>5} gray={gray} {status}")
        if not black or gray:
            failures.append(px)
    if failures:
        print(f"check-render: FAIL: sizes {failures}", file=sys.stderr)
        sys.exit(1)
    print(f"check-render: OK: {len(report['strikes'])} strikes pixel-perfect")


if __name__ == "__main__":
    main()
