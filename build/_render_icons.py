"""One-shot helper to render build/icon.svg into all icon formats.

Outputs:
  build/appicon.png                — 1024x1024 (Wails picks up)
  build/darwin/icon.icns           — macOS app icon
  build/windows/icon.ico           — Windows app icon (multi-resolution)
  build/icon-<size>.png            — PNG previews at common sizes
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import cairosvg
from PIL import Image

BUILD_DIR = Path(__file__).resolve().parent
SVG = BUILD_DIR / "icon.svg"
APPICON_PNG = BUILD_DIR / "appicon.png"
DARWIN_DIR = BUILD_DIR / "darwin"
WINDOWS_DIR = BUILD_DIR / "windows"
ICONSET = BUILD_DIR / "icon.iconset"

ICONSET_SIZES = [
    (16, "icon_16x16.png"),
    (32, "icon_16x16@2x.png"),
    (32, "icon_32x32.png"),
    (64, "icon_32x32@2x.png"),
    (128, "icon_128x128.png"),
    (256, "icon_128x128@2x.png"),
    (256, "icon_256x256.png"),
    (512, "icon_256x256@2x.png"),
    (512, "icon_512x512.png"),
    (1024, "icon_512x512@2x.png"),
]

ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]


def render_png(size: int) -> bytes:
    return cairosvg.svg2png(
        url=str(SVG),
        output_width=size,
        output_height=size,
    )


def main() -> int:
    if not SVG.exists():
        print(f"missing {SVG}", file=sys.stderr)
        return 1

    DARWIN_DIR.mkdir(exist_ok=True)
    WINDOWS_DIR.mkdir(exist_ok=True)

    # 1024 master → appicon.png
    APPICON_PNG.write_bytes(render_png(1024))
    print(f"wrote {APPICON_PNG}")

    # macOS iconset
    if ICONSET.exists():
        for f in ICONSET.iterdir():
            f.unlink()
        ICONSET.rmdir()
    ICONSET.mkdir()
    for size, name in ICONSET_SIZES:
        (ICONSET / name).write_bytes(render_png(size))
    icns = DARWIN_DIR / "icon.icns"
    subprocess.run(
        ["iconutil", "-c", "icns", str(ICONSET), "-o", str(icns)],
        check=True,
    )
    print(f"wrote {icns}")

    # Windows .ico (multi-resolution). Pillow embeds at each requested size
    # by downscaling from the source. Render a single 256x256 master.
    ico_path = WINDOWS_DIR / "icon.ico"
    tmp = BUILD_DIR / "_ico_master.png"
    tmp.write_bytes(render_png(256))
    master = Image.open(tmp).convert("RGBA")
    master.save(ico_path, format="ICO", sizes=[(s, s) for s in ICO_SIZES])
    tmp.unlink(missing_ok=True)
    print(f"wrote {ico_path}")

    # Cleanup iconset directory (icns is built; raw iconset not needed in repo)
    for f in ICONSET.iterdir():
        f.unlink()
    ICONSET.rmdir()

    return 0


if __name__ == "__main__":
    sys.exit(main())
