"""Turn icon.svg into the icon formats each platform installer wants.

Run from the repo root after changing icon.svg:

    pip install cairosvg pillow
    python build-assets/make_icons.py

Produces (all committed, so the build pipeline needs no image tooling):
    build-assets/icons/icon_<size>.png   source sizes
    build-assets/icon.ico                Windows
    build-assets/icon.png                Linux (512px)
    build-assets/Receipts.iconset/       macOS; CI runs iconutil over this

macOS .icns is assembled on the macOS runner because iconutil ships with
Xcode and has no cross-platform equivalent worth trusting.
"""

from pathlib import Path

import cairosvg
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SVG = ROOT / "icon.svg"
OUT = ROOT / "build-assets"
PNGS = OUT / "icons"
ICONSET = OUT / "Receipts.iconset"

SIZES = [16, 32, 64, 128, 256, 512, 1024]

# macOS wants each size at 1x and 2x, under exactly these names.
ICONSET_FILES = [
    ("icon_16x16.png", 16), ("icon_16x16@2x.png", 32),
    ("icon_32x32.png", 32), ("icon_32x32@2x.png", 64),
    ("icon_128x128.png", 128), ("icon_128x128@2x.png", 256),
    ("icon_256x256.png", 256), ("icon_256x256@2x.png", 512),
    ("icon_512x512.png", 512), ("icon_512x512@2x.png", 1024),
]


def render(size: int) -> Path:
    dest = PNGS / f"icon_{size}.png"
    cairosvg.svg2png(
        url=str(SVG), write_to=str(dest), output_width=size, output_height=size
    )
    return dest


def main() -> None:
    for d in (PNGS, ICONSET):
        d.mkdir(parents=True, exist_ok=True)

    rendered = {s: render(s) for s in SIZES}
    print(f"rendered {len(rendered)} PNG sizes")

    for name, size in ICONSET_FILES:
        Image.open(rendered[size]).save(ICONSET / name)
    print(f"wrote {ICONSET.relative_to(ROOT)}/ ({len(ICONSET_FILES)} files)")

    # Windows .ico carries every size in one file.
    Image.open(rendered[256]).save(
        OUT / "icon.ico",
        sizes=[(s, s) for s in (16, 32, 48, 64, 128, 256)],
    )
    print("wrote build-assets/icon.ico")

    Image.open(rendered[512]).save(OUT / "icon.png")
    print("wrote build-assets/icon.png")


if __name__ == "__main__":
    main()
