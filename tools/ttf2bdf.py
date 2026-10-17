#!/usr/bin/env python3
"""Rasterize a TTF/OTF into a BDF bitmap strike at a given pixel size.

This is the merge *filler*: px sizes that no bitmap font reaches (e.g. 19px
or 77px) would otherwise leave a hole in the OTB. CozetteVector is an outline
font drawn on a pixel grid, so rendering it 1-bit at the target ppem yields a
crisp TTF-derived bitmap strike that fonttosfnt can merge like any other BDF.

Usage: ttf2bdf.py IN.ttf PX OUT.bdf [FAMILY]
Requires: freetype-py
"""

import sys

RES = 75  # dpi used for the emitted BDF header


def rasterize(ttf_path, px, family="CozetteVector"):
    """Return (bdf_text, ascent, descent) for one ppem of ttf_path.

    ascent/descent are BDF-style (descent positive) and let the merged OTB
    keep a per-strike line height instead of fonttosfnt's global max.
    """
    import freetype

    face = freetype.Face(ttf_path)
    try:
        face.select_charmap(freetype.FT_ENCODING_UNICODE)
    except freetype.ft_errors.FT_Exception:
        pass  # keep default charmap
    face.set_pixel_sizes(0, px)
    flags = freetype.FT_LOAD_RENDER | freetype.FT_LOAD_TARGET_MONO

    ascent = face.size.ascender >> 6
    descent = -(face.size.descender >> 6)
    if ascent <= 0 or ascent + descent <= 0:
        ascent = max(1, int(round(px * 0.8)))
        descent = px - ascent

    glyphs = []
    seen = set()
    for code, _gindex in face.get_chars():
        if code in seen or code < 0:
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
                start = y * abs(pitch)
                row = buf[start:start + rowbytes]
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
    min_x = min(g[4] for g in glyphs)
    min_y = min(g[5] for g in glyphs)
    cell_w = max(g[1] for g in glyphs) or max_w
    point = px * 72.0 / RES

    def swidth(dw):
        return int(round(dw * 72000 / (RES * point))) if point else dw * 10

    xlfd = ("-muteshebbek-%s-Medium-R-Normal--%d-%d-%d-%d-M-%d-ISO10646-1"
            % (family, px, int(round(point * 10)), RES, RES, cell_w * 10))
    out = [
        "STARTFONT 2.1",
        "FONT " + xlfd,
        "SIZE %d %d %d" % (px, RES, RES),
        "FONTBOUNDINGBOX %d %d %d %d" % (max_w, max_h, min_x, min_y),
        "STARTPROPERTIES 5",
        'FOUNDRY "muteshebbek"',
        'FAMILY_NAME "%s"' % family,
        "PIXEL_SIZE %d" % px,
        "FONT_ASCENT %d" % ascent,
        "FONT_DESCENT %d" % descent,
        "ENDPROPERTIES",
        "CHARS %d" % len(glyphs),
    ]
    for enc, dw, bw, bh, xoff, yoff, rows in glyphs:
        out.append("STARTCHAR U+%04X" % enc)
        out.append("ENCODING %d" % enc)
        out.append("SWIDTH %d 0" % swidth(dw))
        out.append("DWIDTH %d 0" % dw)
        out.append("BBX %d %d %d %d" % (bw, bh, xoff, yoff))
        out.append("BITMAP")
        out.extend(rows)
        out.append("ENDCHAR")
    out.append("ENDFONT")
    return "\n".join(out) + "\n", ascent, descent


def main():
    text, ascent, descent = rasterize(sys.argv[1], int(sys.argv[2]),
                                      *(sys.argv[4:5] or ["CozetteVector"]))
    with open(sys.argv[3], "w", encoding="ascii") as f:
        f.write(text)
    print("ttf2bdf: %s @ %spx -> %s (ascent=%d descent=%d)"
          % (sys.argv[1], sys.argv[2], sys.argv[3], ascent, descent))


if __name__ == "__main__":
    main()
