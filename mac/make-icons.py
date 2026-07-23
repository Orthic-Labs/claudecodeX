#!/usr/bin/env python3
"""Generate ClaudeCodeX second-instance icons for macOS and Windows.

The second instance must be instantly distinguishable from the primary in the
Dock, Cmd-Tab, and the taskbar, while still reading as the same application.
Both recipes keep the original glyph and only move colour:

  Claude    terracotta field + white glyph  ->  black field + terracotta glyph
  ChatGPT   white field + black glyph       ->  black field + white glyph

Inversion is done on a whiteness measure rather than a plain RGB invert, so
antialiased glyph edges blend between the two target colours instead of turning
muddy. Alpha is preserved, so the rounded-square silhouette is unchanged.

Outputs .icns (via native iconutil) and .ico (for the Windows launchers) from
one source, so both platforms stay in sync.

    python3 mac/make-icons.py <source.png> <out-basename> --recipe swap|invert
"""
import argparse
import colorsys
import pathlib
import shutil
import subprocess
import sys

from PIL import Image

ROUTE_BLACK = (11, 13, 16)
TERRACOTTA = (217, 119, 87)
WHITE = (245, 242, 234)

# macOS wants these; Windows .ico takes a subset.
ICNS_SIZES = [16, 32, 64, 128, 256, 512, 1024]
ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]


def whiteness(r, g, b):
    """1.0 for white, 0.0 for a fully saturated or fully dark pixel."""
    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    return (1.0 - s) * v


def lerp(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def field_whiteness(image):
    """Whiteness of the dominant opaque colour, i.e. the icon's background field.

    The ramp is anchored to this rather than to 0. Claude's terracotta field has
    a whiteness near 0.34, so an unanchored ramp would leave the background a
    muddy dark orange instead of black.
    """
    from collections import Counter
    counts = Counter(p for p in image.convert("RGBA").getdata() if p[3] > 200)
    if not counts:
        return 0.0
    r, g, b, _ = counts.most_common(1)[0][0]
    return whiteness(r, g, b)


def recolour(image, low, high, flip=False):
    """Map whiteness onto a two-colour ramp, preserving alpha.

    `low` is the colour for the background field, `high` for the glyph.

    `flip` is for icons whose field is the WHITEST element (ChatGPT: white field,
    dark glyph). There both ends already sit at the extremes, so the ramp is
    simply reversed and no anchoring is needed.
    """
    image = image.convert("RGBA")
    if flip:
        anchor, span = 0.0, 1.0
    else:
        anchor = field_whiteness(image)
        span = max(1e-6, 1.0 - anchor)
    out = Image.new("RGBA", image.size)
    src = image.load()
    dst = out.load()
    width, height = image.size
    for y in range(height):
        for x in range(width):
            r, g, b, a = src[x, y]
            if a == 0:
                dst[x, y] = (0, 0, 0, 0)
                continue
            w = whiteness(r, g, b)
            if flip:
                w = 1.0 - w
            t = min(1.0, max(0.0, (w - anchor) / span))
            dst[x, y] = (*lerp(low, high, t), a)
    return out


def write_icns(image, out_base):
    iconset = out_base.with_suffix(".iconset")
    if iconset.exists():
        shutil.rmtree(iconset)
    iconset.mkdir(parents=True)
    for size in ICNS_SIZES:
        image.resize((size, size), Image.LANCZOS).save(iconset / f"icon_{size}x{size}.png")
        if size <= 512:
            image.resize((size * 2, size * 2), Image.LANCZOS).save(
                iconset / f"icon_{size}x{size}@2x.png"
            )
    icns = out_base.with_suffix(".icns")
    subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(icns)], check=True)
    shutil.rmtree(iconset)
    return icns


def write_ico(image, out_base):
    ico = out_base.with_suffix(".ico")
    image.save(ico, sizes=[(s, s) for s in ICO_SIZES])
    return ico


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("out_base")
    ap.add_argument("--recipe", choices=("swap", "invert"), required=True)
    args = ap.parse_args()

    image = Image.open(args.source).convert("RGBA")
    if args.recipe == "swap":
        # Claude: the terracotta field goes black, the white glyph goes terracotta.
        result = recolour(image, ROUTE_BLACK, TERRACOTTA)
    else:
        # ChatGPT: the white field goes black, the dark glyph goes white.
        # The ramp already does this: whiteness 1 (the field) lands on the first
        # colour, whiteness 0 (the glyph) on the second.
        result = recolour(image, ROUTE_BLACK, WHITE, flip=True)

    out_base = pathlib.Path(args.out_base)
    out_base.parent.mkdir(parents=True, exist_ok=True)
    png = out_base.with_suffix(".png")
    result.save(png)
    icns = write_icns(result, out_base)
    ico = write_ico(result, out_base)
    print(f"{png}\n{icns}\n{ico}")


if __name__ == "__main__":
    sys.exit(main())
