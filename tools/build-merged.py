#!/usr/bin/env python3
"""Build the merged font: one strike per px size, winner per priority.

For every px in winners.json, takes the highest-priority font that has a
BDF (preferred) or PCF file at exactly that pixel size (regular weight,
no icon variants), then merges all selected files into a single OTB with
fonttosfnt (one strike per input) and brands it "Muteshebbek".

Usage:
  build-merged.py --pkgmap pkgmap.txt --sizes sizes.json --winners winners.json \\
      --out Muteshebbek.otb --report merged-report.json
"""

import argparse
import json
import os
import re
import subprocess
import sys

FAMILY = "Muteshebbek"


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pkgmap", required=True)
    ap.add_argument("--sizes", required=True)
    ap.add_argument("--winners", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--report", required=True)
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
        full = os.path.join(pkgmap[contender], "share", "fonts", e["path"])
        strikes.append({"px": px, "package": contender, "file": e["path"],
                        "format": e["format"], "sha256": e["sha256"],
                        "fullpath": full})

    if not strikes:
        print("ERROR: nothing selected", file=sys.stderr)
        sys.exit(1)

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
        font.save(args.out)
    finally:
        font.close()

    report = {"font": os.path.basename(args.out), "family": FAMILY,
              "generated_by": "tools/build-merged.py via winners.json",
              "strikes": [{k: s[k] for k in ("px", "package", "file", "format", "sha256")}
                          for s in strikes],
              "skipped": skipped}
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1, sort_keys=True)
        f.write("\n")
    print(f"merged {len(strikes)} strikes -> {args.out}")


if __name__ == "__main__":
    main()
