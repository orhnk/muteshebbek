#!/usr/bin/env python3
"""Render a preview gallery for every font at every native pixel size.

For each logical package, picks the most regular BDF/PCF file per pixel
size (same rule as tools/build-merged.py) and renders two sample lines
with Pillow/FreeType at the native size: once 1:1, once magnified 3x
(nearest-neighbor, still pixel-exact). Also renders every strike of the
merged Muteshebbek OTB. Unrenderable strikes are recorded, not fatal.

Outputs into --outdir: png/<package>-<px>px.png, index.html, previews.json.

Usage:
  render-previews.py --pkgmap pkgmap.txt --sizes sizes.json \\
      --merged-otb Muteshebbek.otb --merged-report merged-report.json \\
      --outdir previews/
Requires: pillow, fonttools.
"""

import argparse
import html
import json
import os
import re
import sys

SAMPLE_LINES = [
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ abcdefghijklmnopqrstuvwxyz 0123456789",
    "Il1O0 []{} <>() *!?#@ $%^&-+ Sil323 Sphinx 0123456789",
]
MAG = 3  # magnification factor for the zoom row (Image.NEAREST)


def regular_score(entry):
    """Lower = more regular. Excludes icon variants (returns None).

    Keep in sync with tools/build-merged.py.
    """
    name = entry["path"].lower()
    if "icons" in name:
        return None
    score = 0
    if entry.get("format") == "pcf":
        score += 5  # BDF preferred, PCF is lossy fallback
    xlfd = (entry.get("xlfd") or "").split("-")
    weight = xlfd[3].lower() if len(xlfd) > 4 else ""
    slant = xlfd[4].lower() if len(xlfd) > 5 else ""
    if weight in ("bold", "black", "demi", "demibold", "heavy"):
        score += 10
    if slant in ("i", "o") or "italic" in name or "oblique" in name:
        score += 10
    if "bold" in name or re.search(r"(^|[-_.])b\.", name):
        score += 10
    if re.search(r"(^|[-_.])(r|n|regular|normal|medium|roman)\.", name):
        score -= 1
    return score


def render_sample(font_path, px):
    """Render SAMPLE_LINES at native size. Returns (image, black, gray).

    Raises on unrenderable strikes (e.g. broken merged ProFont strikes).
    """
    from PIL import Image, ImageDraw, ImageFont
    font = ImageFont.truetype(font_path, px)
    probe = Image.new("L", (8, 8), 255)
    d = ImageDraw.Draw(probe)
    widths, heights = [], []
    for line in SAMPLE_LINES:
        box = d.textbbox((0, 0), line, font=font, anchor="lt")
        widths.append(box[2])
        heights.append(box[3])
    w = max(widths) + 10
    h = sum(heights) + 5 * (len(SAMPLE_LINES) + 1)
    img = Image.new("L", (w, h), 255)
    d = ImageDraw.Draw(img)
    y = 5
    for i, line in enumerate(SAMPLE_LINES):
        d.text((5, y), line, font=font, fill=0, anchor="lt")
        y += heights[i] + 5
    data = list(img.getdata())  # getdata: works on old and new Pillow
    black = sum(1 for v in data if v == 0)
    gray = sum(1 for v in data if v not in (0, 255))
    return img, black, gray


def preview_image(font_path, px):
    """Native block over a MAG x nearest-neighbor zoom row + separator."""
    from PIL import Image, ImageDraw
    native, black, gray = render_sample(font_path, px)
    zoom = native.resize((native.width * MAG, native.height * MAG),
                         Image.NEAREST)
    sheet = Image.new("L", (zoom.width, native.height + 1 + zoom.height), 255)
    sheet.paste(native, (0, 0))
    ImageDraw.Draw(sheet).line([(0, native.height), (zoom.width, native.height)],
                               fill=128)
    sheet.paste(zoom, (0, native.height + 1))
    return sheet, black, gray


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pkgmap", required=True)
    ap.add_argument("--sizes", required=True)
    ap.add_argument("--merged-otb", required=True)
    ap.add_argument("--merged-report", required=True)
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()

    pkgmap = {}
    with open(args.pkgmap, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                store_path, _, logical = line.rpartition(" ")
                pkgmap[logical] = store_path
    with open(args.sizes, encoding="utf-8") as f:
        files = json.load(f)["files"]
    with open(args.merged_report, encoding="utf-8") as f:
        merged_report = json.load(f)

    by_pkg_px = {}
    for e in files:
        if e.get("format") in ("bdf", "pcf") and isinstance(e.get("pixel_size"), int):
            by_pkg_px.setdefault((e["package"], e["pixel_size"]), []).append(e)

    jobs = []  # (package, px, font_path, source_label, asc, desc)
    for (pkg, px) in sorted(by_pkg_px, key=lambda t: (t[0], t[1])):
        cands = []
        for e in by_pkg_px[(pkg, px)]:
            s = regular_score(e)
            if s is not None:
                cands.append((s, e["path"], e))
        if not cands:
            continue
        cands.sort(key=lambda t: (t[0], t[1]))
        e = cands[0][2]
        full = os.path.join(pkgmap[pkg], "share", "fonts", e["path"])
        asc, desc = e.get("ascent"), e.get("descent")
        jobs.append((pkg, px, full,
                     f"{e['path']} ({e['format']})",
                     asc if isinstance(asc, int) else None,
                     desc if isinstance(desc, int) else None))

    from fontTools.ttLib import TTFont
    merged_px = []
    with TTFont(args.merged_otb) as font:
        tag = "EBLC" if "EBLC" in font else "CBLC"
        merged_px = sorted({s.bitmapSizeTable.ppemX for s in font[tag].strikes})
    rep_by_px = {s["px"]: s for s in merged_report["strikes"]}
    for px in merged_px:
        src = rep_by_px.get(px, {})
        jobs.append(("Muteshebbek", px, args.merged_otb,
                     f"merged strike from {src.get('package', '?')}"
                     f"/{src.get('file', '?')}",
                     src.get("ascent"), src.get("descent")))

    pngdir = os.path.join(args.outdir, "png")
    os.makedirs(pngdir, exist_ok=True)
    previews = []
    for pkg, px, font_path, source, asc, desc in jobs:
        img_name = f"{pkg}-{px}px.png"
        status, black, gray = "ok", 0, 0
        try:
            sheet, black, gray = preview_image(font_path, px)
            if not black:
                status = "empty"
            elif gray:
                status = "antialiased"
            else:
                sheet.save(os.path.join(pngdir, img_name))
        except Exception as e:  # noqa: BLE001 - record, don't kill the gallery
            status = f"error: {type(e).__name__}: {e}"
            print(f"WARN: {pkg} {px}px ({source}): {status}", file=sys.stderr)
        previews.append({"package": pkg, "px": px, "source": source,
                         "ascent": asc, "descent": desc, "image": img_name,
                         "status": status, "black": black, "gray": gray})

    with open(os.path.join(args.outdir, "previews.json"), "w",
              encoding="utf-8") as f:
        json.dump({"generated_by": "tools/render-previews.py",
                   "previews": previews}, f, indent=1, sort_keys=True)
        f.write("\n")

    groups = {}
    for p in previews:
        groups.setdefault(p["package"], []).append(p)
    parts = ["<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\">",
             "<title>Muteshebbek font previews</title><style>",
             "body{font-family:sans-serif;background:#f4f4f4;color:#111;"
             "margin:2em;max-width:1400px}",
             "img{image-rendering:pixelated;background:#fff;border:1px solid #ccc;"
             "max-width:100%}figure{background:#fff;border:1px solid #ddd;",
             "padding:1em;margin:0 0 1.5em}figcaption{margin-top:.5em}",
             ".badge{display:inline-block;padding:.1em .5em;border-radius:4px;",
             "font-size:.85em}.ok{background:#d7f0d7}.bad{background:#f5d0d0}",
             "</style></head><body><h1>Muteshebbek font previews</h1>"]
    ok = sum(1 for p in previews if p["status"] == "ok")
    parts.append(f"<p>{ok}/{len(previews)} previews rendered pixel-exact; "
                 "each shows the native bitmap row above a 3x zoom row.</p>")
    for pkg in sorted(groups):
        parts.append(f"<h2>{html.escape(pkg)}</h2>")
        for p in sorted(groups[pkg], key=lambda q: q["px"]):
            cls = "ok" if p["status"] == "ok" else "bad"
            meta = (f"{p['px']}px &mdash; {html.escape(p['source'])}"
                    + (f" &mdash; asc {p['ascent']}/desc {p['descent']}"
                       if p["ascent"] is not None else ""))
            if p["status"] == "ok":
                parts.append(
                    f"<figure><img src=\"png/{p['image']}\" "
                    f"alt=\"{html.escape(pkg)} {p['px']}px\">"
                    f"<figcaption>{meta} "
                    f"<span class=\"badge {cls}\">crisp</span></figcaption>"
                    "</figure>")
            else:
                parts.append(
                    f"<figure><figcaption>{meta} "
                    f"<span class=\"badge {cls}\">"
                    f"{html.escape(p['status'])}</span></figcaption></figure>")
    parts.append("</body></html>")
    with open(os.path.join(args.outdir, "index.html"), "w",
              encoding="utf-8") as f:
        f.write("\n".join(parts))

    failed = [p for p in previews if p["status"] != "ok"]
    print(f"previews: {len(previews) - len(failed)}/{len(previews)} crisp "
          f"-> {args.outdir}")
    for p in failed:
        print(f"  MISS {p['package']} {p['px']}px: {p['status']}")


if __name__ == "__main__":
    main()
