#!/usr/bin/env python3
"""PCF -> BDF converter.

Header fields (SIZE/PIXEL_SIZE/XLFD/resolution) come from our own PCF
PROPERTIES parser (tools/scan-sizes.py logic, incl. swapped-magic files);
glyph bitmaps come from FreeType rasterization at the native pixel size,
which handles all PCF quirks (byte orders, paddings) correctly.

Usage: pcf2bdf.py IN.pcf[.gz] OUT.bdf [--selftest SIBLING.bdf]
Requires: freetype-py
"""

import gzip
import struct
import sys
import tempfile


def _u32(b, o, lsb):
    return struct.unpack_from("<I" if lsb else ">I", b, o)[0]


def read_file(path):
    with open(path, "rb") as f:
        data = f.read()
    if path.endswith(".gz"):
        data = gzip.decompress(data)
    return data


def read_props(data):
    """PROPERTIES table -> dict. Tries LSB then MSB byte order."""
    if data[0:4] not in (b"\x01pcf", b"\x01fcp"):
        raise ValueError("bad PCF magic")
    ntables = _u32(data, 4, True)
    toff = None
    off = 8
    for _ in range(ntables):
        ttype, _, _, to = struct.unpack_from("<IIII", data, off)
        if ttype == 1:
            toff = to
        off += 16
    if toff is None:
        raise ValueError("no PROPERTIES table")
    for lsb in (True, False):
        try:
            return _props_body(data, toff, lsb)
        except (ValueError, struct.error, IndexError):
            pass
    raise ValueError("properties undecodable")


def _props_body(data, toff, lsb):
    nprops = _u32(data, toff + 4, lsb)
    if nprops > 10000:
        raise ValueError("nprops")
    pos = toff + 8
    entries = []
    for _ in range(nprops):
        entries.append((_u32(data, pos, lsb), data[pos + 4], _u32(data, pos + 5, lsb)))
        pos += 9
    pos += (4 - ((8 + 9 * nprops) % 4)) % 4
    ssize = _u32(data, pos, lsb)
    if ssize > 10_000_000:
        raise ValueError("strings")
    strings = data[pos + 4:pos + 4 + ssize]
    if len(strings) < ssize:
        raise ValueError("truncated")

    def gs(at):
        end = strings.index(b"\x00", at)
        return strings[at:end].decode("ascii", errors="replace")

    props = {}
    for name_off, is_str, val in entries:
        key = gs(name_off)
        props[key] = gs(val) if is_str else (val if val < 0x80000000 else val - 0x100000000)
    return props


def _pint(props, key):
    try:
        return int(str(props.get(key, "")).strip().strip('"'))
    except (ValueError, TypeError):
        return None


def convert(in_path, out_path):
    import freetype

    data = read_file(in_path)
    props = read_props(data)
    pixel = _pint(props, "PIXEL_SIZE")
    point_t = _pint(props, "POINT_SIZE")
    point = point_t / 10.0 if point_t is not None else (pixel or 10)
    resx = _pint(props, "RESOLUTION_X") or 75
    resy = _pint(props, "RESOLUTION_Y") or 75
    xlfd = str(props.get("FONT", "-misc-fixed-medium-r-normal--10-100-75-75-c-80-iso10646-1"))

    if pixel is None:
        parts = xlfd.split("-")  # XLFD field 7 = pixel size
        if len(parts) > 7:
            try:
                pixel = int(parts[7])
            except ValueError:
                pixel = None
    if pixel is None:
        raise ValueError("no PIXEL_SIZE in PCF PROPERTIES (nor XLFD)")

    with tempfile.NamedTemporaryFile(suffix=".pcf", delete=True) as tmp:
        tmp.write(data)
        tmp.flush()
        face = freetype.Face(tmp.name)
        try:
            face.select_charmap(freetype.FT_ENCODING_UNICODE)
        except freetype.ft_errors.FT_Exception:
            pass  # keep default charmap
        face.set_pixel_sizes(0, pixel)
        flags = freetype.FT_LOAD_RENDER | freetype.FT_LOAD_MONOCHROME
        glyphs = []
        seen = set()
        for code, _gindex in face.get_chars():
            if code in seen:
                continue
            seen.add(code)
            face.load_char(code, flags)
            slot = face.glyph
            bmp = slot.bitmap
            w, h = bmp.width, bmp.rows
            dw = slot.advance.x >> 6
            if w > 0 and h > 0:
                pitch = bmp.pitch
                buf = bytes(bmp.buffer)
                rowbytes = (w + 7) // 8
                rows = []
                for y in range(h):
                    row = buf[y * abs(pitch):y * abs(pitch) + rowbytes]
                    if len(row) < rowbytes:
                        row = row + b"\x00" * (rowbytes - len(row))
                    rows.append(row.hex().upper())
                if pitch < 0:
                    rows.reverse()
                xoff, yoff = slot.bitmap_left, slot.bitmap_top - h
            else:
                # e.g. space: advance but no ink
                rows, xoff, yoff = ["00"], 0, 0
                w, h = 1, 1
            glyphs.append((code, dw, w, h, xoff, yoff, rows))
    glyphs.sort()

    max_w = max(g[2] for g in glyphs)
    max_h = max(g[3] for g in glyphs)
    sw = lambda dw: int(round(dw * 72000 / (resx * point))) if point else dw * 10
    with open(out_path, "w", encoding="ascii") as f:
        f.write("STARTFONT 2.1\nFONT %s\nSIZE %d %d %d\n" % (xlfd, int(point), resx, resy))
        f.write("FONTBOUNDINGBOX %d %d 0 0\nSTARTPROPERTIES 3\n" % (max_w, max_h))
        f.write('FOUNDRY "%s"\nFAMILY_NAME "%s"\nPIXEL_SIZE %d\nENDPROPERTIES\n' % (
            xlfd.split("-")[1] if xlfd.startswith("-") else "UNKNOWN", "converted", pixel))
        f.write("CHARS %d\n" % len(glyphs))
        for enc, dw, bw, bh, xoff, yoff, rows in glyphs:
            f.write("STARTCHAR U+%04X\nENCODING %d\nSWIDTH %d 0\nDWIDTH %d 0\nBBX %d %d %d %d\nBITMAP\n"
                    % (enc, enc, sw(dw), dw, bw, bh, xoff, yoff))
            for row in rows:
                f.write("%s\n" % row)
            f.write("ENDCHAR\n")
        f.write("ENDFONT\n")
    return {"glyphs": len(glyphs), "pixel": pixel, "xlfd": xlfd}


def selftest_bdf(path):
    """Parse BDF into {enc: {dw, bbx, rows}} for comparison."""
    glyphs = {}
    cur = None
    rows = []
    with open(path, encoding="ascii", errors="replace") as f:
        for raw in f:
            line = raw.strip()
            if line.startswith("STARTCHAR"):
                cur = {}
                rows = []
            elif line.startswith("ENCODING "):
                cur["enc"] = int(line.split()[1])
            elif line.startswith("DWIDTH "):
                cur["dw"] = int(line.split()[1])
            elif line.startswith("BBX "):
                cur["bbx"] = tuple(int(x) for x in line.split()[1:5])
            elif line == "BITMAP":
                pass
            elif line == "ENDCHAR":
                cur["rows"] = rows
                glyphs[cur["enc"]] = cur
            elif cur is not None and line and all(c in "0123456789ABCDEFabcdef" for c in line):
                rows.append(line.upper())
    return glyphs


def main():
    out = convert(sys.argv[1], sys.argv[2])
    print(out)
    if len(sys.argv) > 3 and sys.argv[3] == "--selftest":
        ref = selftest_bdf(sys.argv[4])
        mine = selftest_bdf(sys.argv[2])
        common = sorted(set(ref) & set(mine))
        bad = [e for e in common
               if ref[e]["dw"] != mine[e]["dw"]
               or ref[e]["bbx"] != mine[e]["bbx"]
               or ref[e]["rows"] != mine[e]["rows"]]
        print(f"common={len(common)} ref_only={len(set(ref)-set(mine))} "
              f"mine_only={len(set(mine)-set(ref))} differ={len(bad)}")
        for e in bad[:10]:
            print(f"DIFF enc={e} dw ref={ref[e]['dw']} mine={mine[e]['dw']} "
                  f"bbx ref={ref[e]['bbx']} mine={mine[e]['bbx']} "
                  f"rowsdiff={ref[e]['rows'] != mine[e]['rows']}")
        if bad or len(common) < 10:
            sys.exit(1)
        print("SELFTEST OK")


if __name__ == "__main__":
    main()
