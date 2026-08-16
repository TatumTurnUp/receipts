"""Check a freshly built bundle before it becomes a download.

PyInstaller is happy to produce an application that starts and then fails at
the first thing it needs from disk. Every check here corresponds to something
that would look fine on the build machine and break only once a user had
downloaded it — which is the most expensive place to find out.

Run from the repo root after `pyinstaller receipts.spec`:

    python build-assets/verify_bundle.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IS_MAC = sys.platform == "darwin"

BUNDLE = (
    ROOT / "dist" / "Receipts.app" / "Contents" / "Frameworks"
    if IS_MAC
    else ROOT / "dist" / "Receipts" / "_internal"
)
EXECUTABLE = (
    ROOT / "dist" / "Receipts.app" / "Contents" / "MacOS" / "Receipts"
    if IS_MAC
    else ROOT / "dist" / "Receipts" / ("Receipts.exe" if sys.platform == "win32" else "Receipts")
)

failures: list[str] = []
notes: list[str] = []


def require(condition: bool, message: str) -> None:
    (notes if condition else failures).append(message)


def find(*relative: str) -> Path | None:
    """Locate a bundled path, tolerating PyInstaller's per-platform layouts."""
    for root in (BUNDLE, BUNDLE.parent, BUNDLE.parent / "Resources"):
        candidate = root.joinpath(*relative)
        if candidate.exists():
            return candidate
    return None


require(EXECUTABLE.exists(), f"executable present: {EXECUTABLE.name}")

# The whole interface. Without it the app starts and serves a 404.
index = find("static", "index.html")
require(index is not None, "frontend bundled (static/index.html)")
if index is not None:
    require(index.stat().st_size > 10_000, f"frontend looks complete ({index.stat().st_size:,} bytes)")

# Linux and Qt read the window icon from disk at runtime; a missing file here
# is the difference between the app icon and a blank space in the dock.
require(find("build-assets", "icon.png") is not None, "runtime window icon bundled")

# Excluded on purpose. If one reappears the build machine leaked it in, and the
# download grew by megabytes nobody asked for.
for unwanted, why in [
    ("cryptography", "12 MB, only pypdf's optional encrypted-PDF backend"),
    ("yaml", "2.6 MB, only uvicorn's optional YAML log config"),
    ("chardet", "0.9 MB, only an optional requests extra"),
    ("websockets", "the app runs with ws='none'"),
    ("tkinter", "never imported"),
]:
    require(find(unwanted) is None, f"excluded: {unwanted} ({why})")

# Present-and-needed, as opposed to present-and-excluded.
require(find("PIL") is not None, "Pillow bundled (EXIF dates, image downscaling)")

print("\n".join(f"  ok    {n}" for n in notes))
if failures:
    print("\n".join(f"  FAIL  {f}" for f in failures), file=sys.stderr)
    print(f"\n{len(failures)} bundle check(s) failed.", file=sys.stderr)
    sys.exit(1)

size = sum(f.stat().st_size for f in (ROOT / "dist").rglob("*") if f.is_file())
print(f"\nAll {len(notes)} bundle checks passed. Total size: {size / 1e6:.1f} MB")
