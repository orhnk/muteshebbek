#!/usr/bin/env python3
"""Scan LOCAL bitmap font packages, emit sizes.json database (one entry per file).

Reads real headers from local files (no network, no guessing):
  BDF      -> SIZE / FONTBOUNDINGBOX / FONT (XLFD) / PIXEL_SIZE+POINT_SIZE+
              RESOLUTION_*+FONT_ASCENT/DESCENT+AVERAGE_WIDTH / CHARS
  PCF      -> PROPERTIES table (same fields as BDF) + glyph count from
              METRICS/INK_METRICS table (.pcf.gz transparently decompressed)
  OTB/OTF  -> fontTools: EBLC/CBLC bitmap strikes (ppem), head/hhea/OS_2,
              name table, numGlyphs
  TTF/WOFF -> fontTools, marked scalable when no bitmap strikes exist
  PSF      -> PSFv1/v2 header (cell size, glyph count)
  other    -> recorded with format tag + parse_note (FON/DFONT/FNT/...)

Usage:
  scan-sizes.py --pkgmap pkgmap.json --manifest fonts.json \\
      --out sizes.json --summary summary.json --compare sizes-compare.txt
"""

import argparse
import gzip
import hashlib
import json
import os
import struct
import sys

SKIP_BASENAMES = {
    "fonts.dir", "fonts.scale", "fonts.alias", "fonts.cache-1",
    "fonts.list", "encodings.dir",
}
SKIP_SUFFIXES = (
    ".txt", ".md", ".gif", ".png", ".sh", ".mk", ".alias",
    ".cache-1", ".dir", ".scale", ".list",
)


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def open_bytes(path):
    if path.endswith(".gz"):
        return gzip.open(path, "rb")
    return open(path, "rb")


def _int_or_none(val):
    try:
        return int(str(val).strip().strip('"'))
    except (ValueError, TypeError):
        return None


def _xlfd_pixel_size(xlfd):
    """Field 7 of XLFD (0-based after leading empty split element)."""
    if not xlfd:
        return None
    parts = xlfd.split("-")
    if len(parts) > 7:
        return _int_or_none(parts[7])
    return None


# ---------------------------------------------------------------- BDF ---
def parse_bdf(path):
    info = {"pixel_size": None, "point_size": None, "point_size_tenths": None,
            "dpi": None, "bbox": None, "xlfd": None, "xlfd_pixel_size": None,
            "ascent": None, "descent": None, "avg_width_tenths": None,
            "spacing": None, "glyphs": None}
    res_x = res_y = None
    in_props = False
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt", encoding="ascii", errors="replace") as f:
        for raw in f:
            line = raw.rstrip("\n")
            if line.startswith("SIZE ") and info["point_size"] is None:
                parts = line.split()
                info["point_size"] = _int_or_none(parts[1]) if len(parts) > 1 else None
                if len(parts) >= 4:
                    res_x, res_y = _int_or_none(parts[2]), _int_or_none(parts[3])
            elif line.startswith("FONTBOUNDINGBOX "):
                parts = line.split()
                if len(parts) >= 5:
                    info["bbox"] = [_int_or_none(p) for p in parts[1:5]]
            elif line.startswith("FONT "):
                info["xlfd"] = line[5:].strip() or None
            elif line == "STARTPROPERTIES":
                in_props = True
            elif line == "ENDPROPERTIES":
                in_props = False
            elif in_props:
                key, _, val = line.partition(" ")
                val = val.strip()
                if key == "PIXEL_SIZE":
                    info["pixel_size"] = _int_or_none(val)
                elif key == "POINT_SIZE":
                    tenths = _int_or_none(val)
                    info["point_size_tenths"] = tenths / 10.0 if tenths is not None else None
                elif key == "RESOLUTION_X":
                    res_x = _int_or_none(val)
                elif key == "RESOLUTION_Y":
                    res_y = _int_or_none(val)
                elif key == "FONT_ASCENT":
                    info["ascent"] = _int_or_none(val)
                elif key == "FONT_DESCENT":
                    info["descent"] = _int_or_none(val)
                elif key == "AVERAGE_WIDTH":
                    info["avg_width_tenths"] = _int_or_none(val)
                elif key == "SPACING":
                    info["spacing"] = val.strip('"') or None
            elif line.startswith("CHARS "):
                info["glyphs"] = _int_or_none(line.split()[1])
                break
    if res_x is not None or res_y is not None:
        info["dpi"] = [res_x, res_y]
    info["xlfd_pixel_size"] = _xlfd_pixel_size(info["xlfd"])
    if info["pixel_size"] is None:
        info["pixel_size"] = info["xlfd_pixel_size"]
    return info


# ---------------------------------------------------------------- PCF ---
def _u32(buf, off, lsb):
    return struct.unpack_from("<I" if lsb else ">I", buf, off)[0]


def _u16(buf, off, lsb):
    return struct.unpack_from("<H" if lsb else ">H", buf, off)[0]


def parse_pcf(data):
    """Minimal PCF reader: PROPERTIES + glyph count from METRICS tables.

    Accepts standard magic (b"\\x01pcf") and the byte-swapped variant
    (b"\\x01fcp") found in some old stlarch/lode/dweep/ohsnap/termsyn files
    (rest of the file is a sane LSB PCF; fontconfig accepts them too).
    """
    magic = data[0:4]
    if magic == b"\x01pcf":
        swapped_magic = False
    elif magic == b"\x01fcp":
        swapped_magic = True
    else:
        raise ValueError("bad PCF magic")
    ntables = _u32(data, 4, True)
    tables = {}
    off = 8
    for _ in range(ntables):
        ttype, fmt, size, toff = struct.unpack_from("<IIII", data, off)
        tables[ttype] = (fmt, size, toff)
        off += 16

    def body_byte_order(fmt):
        return bool(fmt & 0x4)  # PCF_BYTE_MASK -> True == LSBFirst

    props = {}
    if 1 in tables:  # PROPERTIES
        fmt, _, toff = tables[1]
        for lsb in (body_byte_order(fmt), not body_byte_order(fmt)):
            try:
                props = _parse_pcf_properties(data, toff, lsb)
                break
            except (ValueError, struct.error, IndexError):
                props = {}
        if not props:
            raise ValueError("cannot decode PROPERTIES table")

    glyphs, glyphs_source = _parse_pcf_glyphs(data, tables)

    def prop_int(key):
        v = props.get(key)
        return _int_or_none(v) if v is not None else None

    def prop_str(key):
        v = props.get(key)
        return str(v) if v is not None else None

    xlfd = prop_str("FONT")
    pixel_size = prop_int("PIXEL_SIZE")
    if pixel_size is None:
        pixel_size = _xlfd_pixel_size(xlfd)
    tenths = prop_int("POINT_SIZE")
    res_x, res_y = prop_int("RESOLUTION_X"), prop_int("RESOLUTION_Y")
    return {
        "pcf_magic": "swapped" if swapped_magic else "standard",
        "pixel_size": pixel_size,
        "point_size_tenths": tenths / 10.0 if tenths is not None else None,
        "dpi": [res_x, res_y] if res_x is not None or res_y is not None else None,
        "xlfd": xlfd,
        "xlfd_pixel_size": _xlfd_pixel_size(xlfd),
        "ascent": prop_int("FONT_ASCENT"),
        "descent": prop_int("FONT_DESCENT"),
        "avg_width_tenths": prop_int("AVERAGE_WIDTH"),
        "spacing": prop_str("SPACING"),
        "glyphs": glyphs,
        "glyphs_source": glyphs_source,
        "pcf_properties": len(props),
    }


def _parse_pcf_glyphs(data, tables):
    """Glyph count with size-consistency check.

    Some old files (swapped-magic PCFs: stlarch/lode/dweep/...) store u16
    counts in the opposite byte order. Candidates are accepted only if the
    count fits the table size; declared byte order wins, flipped is fallback.
    Returns (count|None, source-description|None).
    """
    def body_byte_order(fmt):
        return bool(fmt & 0x4)

    cands = []
    for ttype in (4, 16):  # METRICS, INK_METRICS
        if ttype not in tables:
            continue
        fmt, size, toff = tables[ttype]
        for lsb in (body_byte_order(fmt), not body_byte_order(fmt)):
            try:
                n, stride = _parse_pcf_metrics_count(data, toff, lsb)
                cands.append((n, size >= 4 + n * stride,
                              f"metrics({'LSB' if lsb else 'MSB'})"))
            except (ValueError, struct.error, IndexError):
                pass
    if 8 in tables:  # BITMAPS: CARD32 format, CARD32 nbitmaps, offsets[n]
        _, size, toff = tables[8]
        for lsb in (True, False):
            try:
                n = _u32(data, toff + 4, lsb)
                cands.append((n, 0 < n <= 200000 and size >= 4 + 4 * n,
                              f"bitmaps({'LSB' if lsb else 'MSB'})"))
            except (ValueError, struct.error, IndexError):
                pass
    for n, sane, src in cands:
        if sane and 0 < n <= 200000:
            return n, src
    return None, None


def _parse_pcf_properties(data, toff, lsb):
    # format word itself is stored LSB-first; body follows its byte order
    nprops = _u32(data, toff + 4, lsb)
    if nprops > 10000:
        raise ValueError(f"implausible nprops={nprops}")
    pos = toff + 8
    entries = []
    for _ in range(nprops):
        name = _u32(data, pos, lsb)
        is_str = data[pos + 4]
        val = _u32(data, pos + 5, lsb)
        entries.append((name, is_str, val))
        pos += 9
    pos += (4 - ((8 + 9 * nprops) % 4)) % 4  # align to 4 rel. table start
    str_size = _u32(data, pos, lsb)
    if str_size > 10_000_000:
        raise ValueError(f"implausible string_size={str_size}")
    strings = data[pos + 4:pos + 4 + str_size]
    if len(strings) < str_size:
        raise ValueError("truncated string table")

    def get_str(at):
        end = strings.index(b"\x00", at)
        return strings[at:end].decode("ascii", errors="replace")

    props = {}
    for name_off, is_str, val in entries:
        key = get_str(name_off)
        if is_str:
            props[key] = get_str(val)
        else:
            props[key] = val if val < 0x80000000 else val - 0x100000000
    return props


def _parse_pcf_metrics_count(data, toff, lsb):
    fmt = _u32(data, toff, lsb)
    if fmt & 0x100:  # PCF_COMPRESSED_METRICS: CARD16 count, 5 bytes/glyph
        count = _u16(data, toff + 4, lsb)
        return count, 5
    count = _u32(data, toff + 4, lsb)  # 12 bytes/glyph
    return count, 12


# --------------------------------------------------------------- SFNT ---
def _strike_ppem(strike):
    # fontTools EblcStrike/CblcStrike: ppem lives in bitmapSizeTable
    bst = getattr(strike, "bitmapSizeTable", None)
    if bst is not None:
        x = getattr(bst, "ppemX", getattr(bst, "ppem_x", None))
        y = getattr(bst, "ppemY", getattr(bst, "ppem_y", None))
        if x is not None and y is not None:
            return [int(x), int(y)]
    v = getattr(strike, "ppems", None)
    if isinstance(v, (tuple, list)) and len(v) >= 2:
        return [int(v[0]), int(v[1])]
    x = getattr(strike, "ppemX", getattr(strike, "ppem_x", None))
    y = getattr(strike, "ppemY", getattr(strike, "ppem_y", None))
    if x is not None and y is not None:
        return [int(x), int(y)]
    return None


def parse_sfnt(path):
    from fontTools.ttLib import TTFont
    font = TTFont(path, lazy=True, recalcBBoxes=False, recalcTimestamp=False)
    try:
        tags = sorted(font.keys())
        head = font["head"]
        hhea = font["hhea"]
        maxp = font["maxp"]
        name = font["name"]
        os2 = font["OS/2"] if "OS/2" in font else None

        def nm(*ids):
            for i in ids:
                v = name.getDebugName(i)
                if v:
                    return v
            return None

        strikes = []
        for tag in ("EBLC", "CBLC"):
            if tag in font:
                for s in font[tag].strikes:
                    ppem = _strike_ppem(s)
                    entry = {"table": tag, "ppem": ppem}
                    if ppem is None:
                        entry["raw_attrs"] = sorted(vars(s).keys())
                    strikes.append(entry)
        return {
            "family": nm(16, 1),
            "style": nm(17, 2),
            "full_name": nm(4),
            "ps_name": nm(6),
            "upem": int(head.unitsPerEm),
            "ascent": int(hhea.ascent),
            "descent": int(hhea.descent),
            "win_ascent": int(os2.usWinAscent) if os2 else None,
            "win_descent": int(os2.usWinDescent) if os2 else None,
            "typo_ascent": int(os2.sTypoAscender) if os2 else None,
            "typo_descent": int(os2.sTypoDescender) if os2 else None,
            "glyphs": int(maxp.numGlyphs),
            "sfnt_tables": tags,
            "strikes": strikes,
            "scalable": not strikes,
        }
    finally:
        font.close()


# ---------------------------------------------------------------- PSF ---
def parse_psf(data):
    if struct.unpack_from("<H", data, 0)[0] == 0x0436:  # PSFv1
        mode, chsize = data[2], data[3]
        return {
            "psf_version": 1,
            "cell": [8, chsize],
            "glyphs": 512 if (mode & 0x01) else 256,
            "unicode_table": bool(mode & 0x02),
        }
    if struct.unpack_from("<I", data, 0)[0] == 0x864B4654:  # PSFv2
        _, _, _, flags, numglyph, _, height, width = struct.unpack_from("<8I", data, 0)
        return {
            "psf_version": 2,
            "cell": [width, height],
            "glyphs": numglyph,
            "unicode_table": bool(flags & 0x01),
        }
    raise ValueError("unknown PSF magic")


# -------------------------------------------------------------- driver ---
def scan_file(package, relpath, fullpath):
    entry = {"package": package, "path": relpath, "sha256": sha256_of(fullpath),
             "format": None, "parse_note": None}
    lower = relpath.lower()
    try:
        if lower.endswith(".bdf"):
            entry["format"] = "bdf"
            entry.update(parse_bdf(fullpath))
            if entry.get("pixel_size") is None:
                entry["parse_note"] = "no PIXEL_SIZE (nor XLFD px) in BDF header"
        elif lower.endswith(".pcf") or lower.endswith(".pcf.gz"):
            entry["format"] = "pcf"
            entry["compressed"] = lower.endswith(".gz")
            with open_bytes(fullpath) as f:
                entry.update(parse_pcf(f.read()))
            if entry.get("pixel_size") is None:
                entry["parse_note"] = "no PIXEL_SIZE (nor XLFD px) in PCF PROPERTIES"
        elif lower.endswith((".otb", ".otf", ".ttf", ".ttc", ".woff", ".woff2")):
            entry["format"] = lower.rsplit(".", 1)[-1]
            try:
                entry.update(parse_sfnt(fullpath))
            except Exception as e:  # noqa: BLE001 - record, don't crash the scan
                entry["parse_note"] = f"sfnt parse failed: {e}"
            if entry.get("strikes") is None and entry.get("parse_note") is None:
                entry["parse_note"] = "no bitmap strikes table decoded"
        elif lower.removesuffix(".gz").endswith((".psf", ".psfu")):
            entry["format"] = "psf"
            entry["compressed"] = lower.endswith(".gz")
            with open_bytes(fullpath) as f:
                entry.update(parse_psf(f.read()))
        else:
            entry["format"] = lower.rsplit(".", 1)[-1] if "." in lower else "unknown"
            entry["parse_note"] = "container/metadata format, sizes not extracted"
    except Exception as e:  # noqa: BLE001 - one bad file must not kill the DB
        entry["parse_note"] = f"parse failed: {e}"
    return entry


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pkgmap", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--priority", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--summary", required=True)
    ap.add_argument("--compare", required=True)
    ap.add_argument("--winners", required=True)
    args = ap.parse_args()

    with open(args.pkgmap, encoding="utf-8") as f:
        pkgmap = {}
        for line in f:
            line = line.strip()
            if not line:
                continue
            store_path, _, logical = line.rpartition(" ")
            pkgmap[store_path] = logical

    files = []
    skipped = 0
    for store_path in sorted(pkgmap):
        logical = pkgmap[store_path]
        fonts_root = os.path.join(store_path, "share", "fonts")
        if not os.path.isdir(fonts_root):
            print(f"WARN: no share/fonts in {logical} ({store_path})", file=sys.stderr)
            continue
        for dirpath, _, filenames in os.walk(fonts_root):
            for fn in sorted(filenames):
                low = fn.lower()
                if low in SKIP_BASENAMES or low.endswith(SKIP_SUFFIXES):
                    skipped += 1
                    continue
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, fonts_root)
                files.append(scan_file(logical, rel, full))

    files.sort(key=lambda e: (e["package"], e["path"]))
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"generated_by": "tools/scan-sizes.py", "files": files},
                  f, indent=1, sort_keys=True)
        f.write("\n")

    by_format, by_package = {}, {}
    px_set = set()
    noted = 0
    for e in files:
        by_format[e["format"]] = by_format.get(e["format"], 0) + 1
        by_package[e["package"]] = by_package.get(e["package"], 0) + 1
        if isinstance(e.get("pixel_size"), int):
            px_set.add(e["pixel_size"])
        for s in e.get("strikes") or []:
            if s.get("ppem"):
                px_set.add(int(s["ppem"][1]))
        if e.get("parse_note"):
            noted += 1
    summary = {"total_files": len(files), "skipped_nonfont": skipped,
               "by_format": by_format, "by_package": by_package,
               "distinct_pixel_sizes": sorted(px_set),
               "files_with_notes": noted}
    with open(args.summary, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=1, sort_keys=True)
        f.write("\n")

    with open(args.manifest, encoding="utf-8") as f:
        manifest = json.load(f)
    aliases = {"uushi-lemon": ["lemon", "uushi"]}
    scanned = {}
    scalable_only = set()
    for e in files:
        for name in aliases.get(e["package"], [e["package"]]):
            px = scanned.setdefault(name, set())
            if isinstance(e.get("pixel_size"), int):
                px.add(e["pixel_size"])
            for s in e.get("strikes") or []:
                if s.get("ppem"):
                    px.add(int(s["ppem"][1]))
            if e.get("scalable"):
                scalable_only.add(name)
    lines = []
    for m in manifest:
        name, claimed = m["name"], set(m.get("sizes_px", []))
        got = scanned.get(name, set())
        if not got:
            if name in scalable_only:
                lines.append(f"SCALABLE {name}: outline-only, no native px "
                             f"(claimed={sorted(claimed)})")
            else:
                lines.append(f"NO-SCANNED-DATA {name}: claimed={sorted(claimed)}")
        elif got == claimed:
            lines.append(f"OK {name}: {sorted(got)}")
        else:
            lines.append(f"MISMATCH {name}: claimed={sorted(claimed)} scanned={sorted(got)}")
    with open(args.compare, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    n_ok = sum(1 for l in lines if l.startswith("OK"))
    n_mm = sum(1 for l in lines if l.startswith("MISMATCH"))
    n_sc = sum(1 for l in lines if l.startswith("SCALABLE"))
    n_nd = sum(1 for l in lines if l.startswith("NO-SCANNED-DATA"))
    print(f"compare: {n_ok} OK, {n_mm} MISMATCH, {n_sc} SCALABLE, {n_nd} NO-DATA")

    # ---- winners: pro px-Groesse gewinnt hoechste Priority (priority.json)
    with open(args.priority, encoding="utf-8") as f:
        priority = json.load(f)["priority"]
    rank = {name: i for i, name in enumerate(priority)}
    px_owners = {}
    for e in files:
        sizes = set()
        if isinstance(e.get("pixel_size"), int):
            sizes.add(e["pixel_size"])
        for s in e.get("strikes") or []:
            if s.get("ppem"):
                sizes.add(int(s["ppem"][1]))
        for px in sizes:
            px_owners.setdefault(px, set()).add(e["package"])
    winners = {}
    for px in sorted(px_owners):
        contenders = sorted(px_owners[px], key=lambda n: rank.get(n, len(rank)))
        winners[str(px)] = {"winner": contenders[0], "contenders": contenders}
    with open(args.winners, "w", encoding="utf-8") as f:
        json.dump({"generated_by": "tools/scan-sizes.py via priority.json",
                   "winners": winners}, f, indent=1, sort_keys=True)
        f.write("\n")
    print(f"winners: {len(winners)} px-Groessen entschieden")


if __name__ == "__main__":
    main()
