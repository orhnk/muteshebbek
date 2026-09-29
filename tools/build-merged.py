#!/usr/bin/env python3
"""Build the merged font: one strike per px size, winner per priority.

For every px in winners.json, takes the highest-priority font that has a
BDF (preferred) or PCF file at exactly that pixel size (regular weight,
no icon variants), then merges all selected files into a single OTB with
fonttosfnt (one strike per input) and brands it "Muteshebbek".

Usage:
  build-merged.py --pkgmap pkgmap.txt --sizes sizes.json --winners winners.json \\
      --out Muteshebbek.otb --report merged-report.json
  build-merged.py --dry-run --sizes sizes.json --winners winners.json
      (prints which source font each px size would use, builds nothing)
"""

import argparse
import json
import os
import re
import subprocess
import sys

FAMILY = "Muteshebbek"


def strike_metrics(entry, px):
    """(ascent, descent) for one strike, descent positive.

    fonttosfnt stamps every strike with the global max (currently 52/-12
    from the 64px strike), which makes small sizes space lines ~64px apart.
    Prefer the source header values (sizes.json: BDF FONT_ASCENT/DESCENT,
    PCF accelerators), then the BDF bounding box, then a px-proportional
    split as last resort.
    """
    asc, desc = entry.get("ascent"), entry.get("descent")
    if (isinstance(asc, int) and isinstance(desc, int)
            and asc > 0 and desc >= 0 and asc + desc <= 2 * px + 4):
        return asc, desc
    bb = entry.get("bbox")
    if (isinstance(bb, list) and len(bb) == 4
            and all(isinstance(v, int) for v in bb)):
        a, d = bb[1] + bb[3], -bb[3]
        if a > 0 and d >= 0 and a + d <= 2 * px + 4:
            return a, d
    a = max(1, round(px * 0.8))
    return a, px - a


def regular_score(entry):
    """Lower = more regular. Excludes icon variants (returns None)."""
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


def print_dry_run(strikes, skipped):
    """Human-readable strike table for --dry-run (no files written)."""
    print(f"{'px':>4}  {'package':<14}  {'asc':>3} {'desc':>4}  format  file")
    for s in strikes:
        print(f"{s['px']:4d}  {s['package']:<14}  {s['ascent']:3d} "
              f"{s['descent']:4d}  {s['format']:<6}  {s['file']}")
    for sk in skipped:
        print(f"{sk['px']:4d}  SKIPPED (contenders="
              f"{','.join(sk['contenders'])}): {sk['reason']}")
    print(f"dry-run: {len(strikes)} strikes, {len(skipped)} skipped "
          f"(nothing written)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pkgmap", required=False, default=None)
    ap.add_argument("--sizes", required=True)
    ap.add_argument("--winners", required=True)
    ap.add_argument("--out", required=False, default=None)
    ap.add_argument("--report", required=False, default=None)
    ap.add_argument("--dry-run", action="store_true",
                    help="print the strike table without running fonttosfnt")
    args = ap.parse_args()

    if args.dry_run:
        if args.out or args.report:
            print("dry-run: ignoring --out/--report (nothing is written)",
                  file=sys.stderr)
    elif not args.pkgmap or not args.out or not args.report:
        ap.error("--pkgmap/--out/--report are required without --dry-run")

    pkgmap = {}
    if args.pkgmap:
        with open(args.pkgmap, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    store_path, _, logical = line.rpartition(" ")
                    pkgmap[logical] = store_path
    with open(args.sizes, encoding="utf-8") as f:
        files = json.load(f)["files"]
    with open(args.winners, encoding="utf-8") as f:
        winners = json.load(f)["winners"]

    by_pkg_px = {}
    for e in files:
        if e.get("format") in ("bdf", "pcf") and isinstance(e.get("pixel_size"), int):
            by_pkg_px.setdefault((e["package"], e["pixel_size"]), []).append(e)

    strikes = []
    skipped = []
    for px_str in sorted(winners, key=int):
        px = int(px_str)
        picked = None
        for contender in winners[px_str]["contenders"]:
            cands = []
            for e in by_pkg_px.get((contender, px), []):
                s = regular_score(e)
                if s is not None:
                    cands.append((s, e["path"], e))
            if cands:
                cands.sort(key=lambda t: (t[0], t[1]))
                picked = (contender, cands[0][2])
                break
        if picked is None:
            reason = "only OTB strikes / outline sources, fonttosfnt needs BDF/PCF"
            skipped.append({"px": px, "reason": reason,
                            "contenders": winners[px_str]["contenders"]})
            print(f"WARN: no BDF/PCF for {px}px, skipped ({reason})", file=sys.stderr)
            continue
        contender, e = picked
        base = pkgmap.get(contender, "")
        full = os.path.join(base, "share", "fonts", e["path"]) if base else ""
        asc, desc = strike_metrics(e, px)
        strikes.append({"px": px, "package": contender, "file": e["path"],
                        "format": e["format"], "sha256": e["sha256"],
                        "ascent": asc, "descent": desc,
                        "fullpath": full})

    if not strikes:
        print("ERROR: nothing selected", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        print_dry_run(strikes, skipped)
        return 0

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    inputs = [s["fullpath"] for s in strikes]
    r = subprocess.run(["fonttosfnt", "-o", args.out] + inputs,
                       capture_output=True, text=True)
    print(r.stdout[-2000:] if r.stdout else "")
    if r.returncode != 0:
        print(r.stderr[-2000:], file=sys.stderr)
        sys.exit(1)

    from fontTools.ttLib import TTFont
    font = TTFont(args.out)
    try:
        name = font["name"]
        for plat in ((3, 1, 0x409), (1, 0, 0)):
            name.setName(FAMILY, 1, *plat)
            name.setName(f"{FAMILY} Regular", 4, *plat)
            name.setName(f"{FAMILY}-Regular", 6, *plat)
            name.setName(FAMILY, 16, *plat)
        # Per-strike line metrics: fonttosfnt stamps every strike with the
        # global max ascender/descender, so small sizes inherit the 64px
        # strike's line height. Restore each strike's own values instead.
        want = {s["px"]: (s["ascent"], s["descent"]) for s in strikes}
        for tag in ("EBLC", "CBLC"):
            if tag not in font:
                continue
            for st in font[tag].strikes:
                px = st.bitmapSizeTable.ppemX
                if px not in want:
                    print(f"WARN: no metrics for {px}px strike, kept as-is",
                          file=sys.stderr)
                    continue
                asc, desc = want[px]
                st.bitmapSizeTable.hori.ascender = asc
                st.bitmapSizeTable.hori.descender = -desc
                st.bitmapSizeTable.vert.ascender = asc
                st.bitmapSizeTable.vert.descender = -desc
        # Global Win metrics must agree with hhea/typo (≈1em line) instead
        # of the head-bbox union (≈1.36em), or Win-metric apps add leading.
        os2 = font["OS/2"]
        os2.usWinAscent = max(0, font["hhea"].ascent)
        os2.usWinDescent = max(0, -font["hhea"].descent)
        font.save(args.out)
    finally:
        font.close()

    report = {"font": os.path.basename(args.out), "family": FAMILY,
              "generated_by": "tools/build-merged.py via winners.json",
              "strikes": [{k: s[k] for k in ("px", "package", "file", "format",
                                            "sha256", "ascent", "descent")}
                          for s in strikes],
              "skipped": skipped}
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1, sort_keys=True)
        f.write("\n")
    print(f"merged {len(strikes)} strikes -> {args.out}")


if __name__ == "__main__":
    main()
