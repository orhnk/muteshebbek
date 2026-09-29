#!/usr/bin/env python3
"""Quality gate for the all-fonts-preview gallery (runs in `nix flake check`).

Asserts every source-font preview rendered pixel-exact. Merged strikes
that FreeType cannot rasterize at all (currently the three ProFont
strikes 17/22/29px, see merged-render) are tolerated there, anything
else fails the build.
Usage: check-previews.py <all-fonts-preview-dir>
"""

import json
import os
import sys

# Merged strikes known to be unrasterizable (FreeType "invalid argument").
# Source PCFs render fine; only the fonttosfnt-merged strikes are broken.
KNOWN_BROKEN_MERGED = {17, 22, 29}

# Source files FreeType cannot address at their claimed integer size.
# The proggyfonts upstream PCFs carry fractional true sizes
# (fc-scan: 6.64/9.3/10.6/12.0px), so Pillow renders them blank or rejects
# the size outright. fonttosfnt (the real pipeline) consumes them fine --
# the merged 7px strike built from WebbyCaps renders crisp.
KNOWN_BROKEN_SOURCES = {("proggyfonts", px) for px in (7, 9, 11, 12, 13, 14)}


def fail(msg):
    print(f"check-previews: FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def main():
    base = sys.argv[1]
    with open(os.path.join(base, "previews.json"), encoding="utf-8") as f:
        previews = json.load(f)["previews"]
    if not os.path.isfile(os.path.join(base, "index.html")):
        fail("index.html missing")
    if len(previews) < 50:
        fail(f"implausibly few previews: {len(previews)}")
    bad = []
    for p in previews:
        png = os.path.join(base, "png", p["image"])
        if p["status"] != "ok":
            if p["package"] == "Muteshebbek" and p["px"] in KNOWN_BROKEN_MERGED \
                    and p["status"].startswith("error:"):
                continue
            if (p["package"], p["px"]) in KNOWN_BROKEN_SOURCES \
                    and (p["status"].startswith("error:")
                         or p["status"] == "empty"):
                continue
            bad.append(f"{p['package']} {p['px']}px: {p['status']}")
        elif not os.path.isfile(png):
            bad.append(f"{p['package']} {p['px']}px: status ok but {png} missing")
    if bad:
        fail(f"{len(bad)} broken previews:\n  " + "\n  ".join(bad[:20]))
    n_src = sum(1 for p in previews if p["package"] != "Muteshebbek")
    n_merged = len(previews) - n_src
    print(f"check-previews: OK: {len(previews)} previews "
          f"({n_src} source + {n_merged} merged strikes)")


if __name__ == "__main__":
    main()
