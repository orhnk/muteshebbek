#!/usr/bin/env python3
"""Build the merged font: one strike per px size, winner per priority.

For every px in winners.json, takes the highest-priority font that has a
BDF (preferred) or PCF file at exactly that pixel size (regular weight,
no icon variants), then merges all selected files into a single OTB with
fonttosfnt (one strike per input) and brands it "Muteshebbek".

upscale.json declares extra integer scales per package, either as a
factor list (all native sizes) or as {source_px: [factors]} for selected
sizes, e.g. cherry-bitmap 11px * 2 = 22px strike:
the native winning file is pixel-doubled into a synthetic BDF strike at
px*factor. A declared scaled strike WINS its target over natives;
package priority only orders multiple scaled contenders for one target
(all visible via --dry-run). This gives small-only fonts a pixel-perfect
big size instead of losing to interpolated scaling.

Usage:
  build-merged.py --pkgmap pkgmap.txt --sizes sizes.json --winners winners.json \\
      --priority priority.json --upscale upscale.json \\
      --out Muteshebbek.otb --report merged-report.json
  build-merged.py --dry-run --sizes sizes.json --winners winners.json \\
      --priority priority.json --upscale upscale.json
      (prints which source font each px size would use, builds nothing)
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import pcf2bdf
except ImportError:  # only needed when scaling a PCF source
    pcf2bdf = None

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


def strike_metrics(entry, px):
    """(ascent, descent) for one strike, descent positive.

    fonttosfnt stamps every strike with the global max (e.g. 52/-12 from
    a 64px strike), which makes small sizes space lines far too wide.
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


def scale_hex_row(hexstr, orig_width, factor):
    """Scale one BDF bitmap row x factor, kept byte-aligned hex.

    orig_width is the UNscaled glyph width: complete rows already span
    the full byte width, so padding must use this basis (padding to the
    scaled width would prepend a zero byte and shift all ink right).
    """
    # Defensive: rows may omit leading zero nibbles; pad those back.
    hexstr = hexstr.strip().zfill(2 * ((orig_width + 7) // 8))
    val = int(hexstr or "0", 16)
    total = len(hexstr) * 4
    out = []
    for i in range(orig_width):
        out.extend([(val >> (total - 1 - i)) & 1] * factor)
    while len(out) % 8:
        out.append(0)
    num = 0
    for b in out:
        num = (num << 1) | b
    return format(num, "X").zfill(len(out) // 4)


def scale_xlfd(line, factor):
    """Scale pixel/point/avgwidth fields of an XLFD font name line."""
    parts = line.split("-")
    if len(parts) == 15:
        try:
            parts[7] = str(int(parts[7]) * factor)
            parts[8] = str(int(parts[8]) * factor)
            parts[12] = str(int(parts[12]) * factor)
            return "-".join(parts)
        except ValueError:
            pass
    return line


def scale_bdf_text(text, factor):
    """Pixel-double BDF source text by an integer factor (metrics + ink)."""
    out = []
    in_bitmap = False
    cur_w = None
    for raw in text.splitlines():
        line = raw
        if in_bitmap:
            if line == "ENDCHAR":
                in_bitmap = False
                out.append("ENDCHAR")
                continue
            out.extend([scale_hex_row(line, cur_w // factor, factor)] * factor
                       if cur_w else [line])
            continue
        if line.startswith("SIZE ") and len(line.split()) >= 4:
            p = line.split()
            out.append(f"SIZE {int(p[1]) * factor} {p[2]} {p[3]}")
        elif line.startswith("FONTBOUNDINGBOX ") and len(line.split()) >= 5:
            v = [int(x) * factor for x in line.split()[1:5]]
            out.append("FONTBOUNDINGBOX " + " ".join(map(str, v)))
        elif line.startswith("FONT_ASCENT ") and len(line.split()) >= 2:
            out.append(f"FONT_ASCENT {int(line.split()[1]) * factor}")
        elif line.startswith("FONT_DESCENT ") and len(line.split()) >= 2:
            out.append(f"FONT_DESCENT {int(line.split()[1]) * factor}")
        elif line.startswith("PIXEL_SIZE ") and len(line.split()) >= 2:
            out.append(f"PIXEL_SIZE {int(line.split()[1]) * factor}")
        elif line.startswith("POINT_SIZE ") and len(line.split()) >= 2:
            out.append(f"POINT_SIZE {int(line.split()[1]) * factor}")
        elif line.startswith("AVERAGE_WIDTH ") and len(line.split()) >= 2:
            out.append(f"AVERAGE_WIDTH {int(line.split()[1]) * factor}")
        elif line.startswith("FONT "):
            out.append(scale_xlfd(line, factor))
        elif line.startswith("SWIDTH ") and len(line.split()) >= 3:
            p = line.split()
            out.append(f"SWIDTH {int(p[1]) * factor} {int(p[2]) * factor}")
        elif line.startswith("DWIDTH ") and len(line.split()) >= 3:
            p = line.split()
            out.append(f"DWIDTH {int(p[1]) * factor} {int(p[2]) * factor}")
        elif line.startswith("BBX ") and len(line.split()) >= 5:
            v = [int(x) * factor for x in line.split()[1:5]]
            cur_w = v[0]
            out.append("BBX " + " ".join(map(str, v)))
        elif line == "BITMAP":
            in_bitmap = True
            out.append("BITMAP")
        else:
            out.append(raw)
    return "\n".join(out) + "\n"


def bdf_source_text(entry, pkgmap):
    """Raw BDF text for a sizes.json entry (PCF converted via freetype)."""
    full = os.path.join(pkgmap[entry["_pkg"]], "share", "fonts", entry["path"])
    if entry.get("format") == "bdf":
        with open(full, encoding="ascii", errors="replace") as f:
            return f.read()
    if pcf2bdf is None:
        raise RuntimeError("pcf2bdf unavailable (freetype-py missing?)")
    with tempfile.NamedTemporaryFile(suffix=".bdf", delete=False) as tmp:
        tmppath = tmp.name
    try:
        pcf2bdf.convert(full, tmppath)
        with open(tmppath, encoding="ascii", errors="replace") as f:
            return f.read()
    finally:
        try:
            os.unlink(tmppath)
        except OSError:
            pass


def print_dry_run(strikes, skipped):
    """Human-readable strike table for --dry-run (no files written)."""
    print(f"{'px':>4}  {'package':<14}  {'asc':>3} {'desc':>4}  scale   "
          f"format  file")
    for s in strikes:
        if s["scale"] == 1:
            scale = "native"
        else:
            scale = f"{s['scale']}x-of-{s['source_px']}px"
        print(f"{s['px']:4d}  {s['package']:<14}  {s['ascent']:3d} "
              f"{s['descent']:4d}  {scale:<7} {s['format']:<6}  {s['file']}")
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
    ap.add_argument("--priority", required=True)
    ap.add_argument("--upscale", required=True)
    ap.add_argument("--out", required=False, default=None)
    ap.add_argument("--report", required=False, default=None)
    ap.add_argument("--dry-run", action="store_true",
                    help="print the strike table without running fonttosfnt")
    args = ap.parse_args()

    if args.dry_run:
        if args.out or args.report or args.pkgmap:
            print("dry-run: ignoring --out/--report/--pkgmap "
                  "(nothing is written)", file=sys.stderr)
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
    with open(args.priority, encoding="utf-8") as f:
        priority = json.load(f)["priority"]
    with open(args.upscale, encoding="utf-8") as f:
        upscale = json.load(f).get("upscale", {})
    rank = {name: i for i, name in enumerate(priority)}
    if not isinstance(upscale, dict):
        print("ERROR: upscale.json must hold an 'upscale' object",
              file=sys.stderr)
        sys.exit(1)
    # Normalize to {pkg: {src_px: [factors]}}; a bare factor list means
    # "all native sizes of that package".
    norm_upscale = {}
    for pkg, spec in upscale.items():
        if isinstance(spec, list):
            norm_upscale[pkg] = ("all", spec)
        elif isinstance(spec, dict) and spec:
            try:
                norm_upscale[pkg] = ("sizes",
                                     {int(k): v for k, v in spec.items()})
            except (TypeError, ValueError):
                print(f"ERROR: upscale[{pkg}] source sizes must be ints",
                      file=sys.stderr)
                sys.exit(1)
        else:
            print(f"ERROR: upscale[{pkg}] must be a factor list or "
                  f"{{source_px: [factors]}}", file=sys.stderr)
            sys.exit(1)
        for factors in (norm_upscale[pkg][1].values()
                        if norm_upscale[pkg][0] == "sizes"
                        else [norm_upscale[pkg][1]]):
            if (not isinstance(factors, list) or not factors
                    or any(not isinstance(x, int) or x < 2
                           for x in factors)):
                print(f"ERROR: upscale[{pkg}] factors must be ints >= 2",
                      file=sys.stderr)
                sys.exit(1)

    for e in files:
        e["_pkg"] = e["package"]
    by_pkg_px = {}
    for e in files:
        if e.get("format") in ("bdf", "pcf") and isinstance(e.get("pixel_size"), int):
            by_pkg_px.setdefault((e["package"], e["pixel_size"]), []).append(e)

    def best_native(pkg, px):
        cands = []
        for e in by_pkg_px.get((pkg, px), []):
            s = regular_score(e)
            if s is not None:
                cands.append((s, e["path"], e))
        if not cands:
            return None
        cands.sort(key=lambda t: (t[0], t[1]))
        return cands[0][2]

    # 1) native picks: first viable contender per px (existing behavior).
    native_pick = {}
    skipped = []
    for px_str in sorted(winners, key=int):
        px = int(px_str)
        picked = None
        for contender in winners[px_str]["contenders"]:
            e = best_native(contender, px)
            if e is not None:
                picked = (contender, e)
                break
        if picked is None:
            reason = "only OTB strikes / outline sources, fonttosfnt needs BDF/PCF"
            skipped.append({"px": px, "reason": reason,
                            "contenders": winners[px_str]["contenders"]})
            print(f"WARN: no BDF/PCF for {px}px, skipped ({reason})",
                  file=sys.stderr)
        else:
            native_pick[px] = picked

    # 2) scaled candidates from upscale declarations. A declared scaled
    # strike wins its target over natives; package priority only orders
    # multiple scaled contenders for one target.
    scaled_cands = {}  # target px -> [(pkg, src_px, entry, factor)]
    for pkg in sorted(norm_upscale):
        kind, spec = norm_upscale[pkg]
        if kind == "all":
            jobs = [(px, f)
                    for px in sorted({p for (p, px) in by_pkg_px if p == pkg})
                    for f in spec]
        else:
            jobs = [(src_px, f)
                    for src_px in sorted(spec)
                    for f in spec[src_px]]
        for src_px, factor in jobs:
            e = best_native(pkg, src_px)
            if e is None:
                print(f"WARN: upscale {pkg} {src_px}px has no usable "
                      f"BDF/PCF, skipped", file=sys.stderr)
                continue
            scaled_cands.setdefault(src_px * factor, []).append(
                (pkg, src_px, e, factor))

    # 3) final selection: declared scaled strikes win their target over
    # natives (priority only orders scaled-vs-scaled); scaled files are
    # materialized lazily, failures fall through to the next contender.
    strikes = []
    tmpdir = None
    scaled_cache = {}

    def materialize(pkg, src_px, entry, factor):
        key = (pkg, src_px, factor)
        if key in scaled_cache:
            return scaled_cache[key]
        nonlocal tmpdir
        if tmpdir is None:
            tmpdir = tempfile.mkdtemp(prefix="muteshebbek-scale-")
        text = bdf_source_text(entry, pkgmap)
        scaled = scale_bdf_text(text, factor)
        path = os.path.join(tmpdir,
                            f"{pkg}-{src_px}px-x{factor}.bdf")
        with open(path, "w", encoding="ascii") as f:
            f.write(scaled)
        scaled_cache[key] = path
        return path

    for px in sorted(set(native_pick) | set(scaled_cands)):
        ordered = []  # (scaled_first, rank, payload)
        for (pkg, src_px, e, factor) in scaled_cands.get(px, []):
            ordered.append((0, rank.get(pkg, len(rank)),
                            ("scaled", pkg, src_px, e, factor)))
        if str(px) in winners:
            for contender in winners[str(px)]["contenders"]:
                e = best_native(contender, px)
                if e is not None:
                    ordered.append((1, rank.get(contender, len(rank)),
                                    ("native", contender, e)))
        ordered.sort(key=lambda t: (t[0], t[1]))
        picked = None
        for _, _, payload in ordered:
            if payload[0] == "native":
                _, contender, e = payload
                asc, desc = strike_metrics(e, px)
                full = os.path.join(pkgmap[contender], "share", "fonts",
                                    e["path"]) if pkgmap else ""
                picked = {"px": px, "package": contender, "file": e["path"],
                          "format": e["format"], "sha256": e["sha256"],
                          "ascent": asc, "descent": desc,
                          "scale": 1, "source_px": px, "fullpath": full}
                break
            _, pkg, src_px, e, factor = payload
            if args.dry_run:
                asc, desc = strike_metrics(e, src_px)
                picked = {"px": px, "package": pkg, "file": e["path"],
                          "format": e["format"], "sha256": e["sha256"],
                          "ascent": asc * factor, "descent": desc * factor,
                          "scale": factor, "source_px": src_px, "fullpath": ""}
                break
            try:
                path = materialize(pkg, src_px, e, factor)
            except Exception as exc:  # noqa: BLE001 - fall through
                print(f"WARN: cannot scale {pkg} {src_px}px x{factor} "
                      f"for {px}px ({exc}), trying next contender",
                      file=sys.stderr)
                continue
            asc, desc = strike_metrics(e, src_px)
            picked = {"px": px, "package": pkg, "file": e["path"],
                      "format": e["format"], "sha256": e["sha256"],
                      "ascent": asc * factor, "descent": desc * factor,
                      "scale": factor, "source_px": src_px, "fullpath": path}
            break
        if picked is None:
            print(f"WARN: no BDF/PCF (native or scaled) for {px}px, skipped",
                  file=sys.stderr)
            continue
        strikes.append(picked)

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
        # global max ascender/descender, so small sizes inherit a huge line
        # height. Restore each strike's own values instead.
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
                                            "sha256", "ascent", "descent",
                                            "scale", "source_px")}
                          for s in strikes],
              "skipped": skipped}
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1, sort_keys=True)
        f.write("\n")
    print(f"merged {len(strikes)} strikes -> {args.out}")


if __name__ == "__main__":
    main()
