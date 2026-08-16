# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build recipe for Receipts.

Bundles Python, the dependencies and the frontend into one application per
platform, so nobody has to install Python or open a terminal.

    pyinstaller receipts.spec --noconfirm

Output lands in dist/. The release workflow wraps that into a .dmg, an
installer .exe and an .AppImage.

Nothing here writes to the user's archive. The bundle is read-only at runtime;
app.py keeps all user data in a per-user folder outside it, which is what makes
replacing this bundle on update a safe operation.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(SPECPATH)))
from version import APP_NAME, BUNDLE_ID  # noqa: E402

IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform == "win32"

# uvicorn and pywebview resolve these at runtime, so static analysis misses
# them and the packaged app dies on launch without them spelled out.
HIDDEN = [
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    # No websockets entries on purpose: the app runs uvicorn with ws="none",
    # so bundling a WebSocket backend would only add weight and a version
    # conflict to trip over.
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
]
try:
    import webview  # noqa: F401

    if IS_MAC:
        HIDDEN += ["webview.platforms.cocoa"]
    elif IS_WIN:
        HIDDEN += ["webview.platforms.edgechromium", "webview.platforms.winforms"]
    else:
        HIDDEN += ["webview.platforms.gtk"]
except ImportError:
    # Building without a native web view: the result still runs, it just opens
    # in the default browser (see launch.py). Release builds always have it.
    print("receipts.spec: pywebview not installed — building the browser fallback")

# Everything below is either unused, or an optional extra some dependency
# probes for and falls back from cleanly. Listing them explicitly also makes
# the build deterministic: without this, whatever happens to be installed on
# the build machine leaks into the bundle. `cryptography` alone is 12 MB, and
# arrives only because pypdf probes for it to read encrypted PDFs.
EXCLUDES = [
    # Never imported by anything here.
    "tkinter", "matplotlib", "numpy", "pytest",
    "PIL.ImageQt", "PIL.ImageTk", "PIL.ImageMath",
    # Optional PDF encryption backends — pypdf guards all three imports.
    "cryptography", "Crypto", "Cryptodome",
    # Optional uvicorn log-config format; we pass log_level, never a YAML file.
    "yaml",
    # Optional requests charset detector.
    "chardet",
    # Optional uvicorn extras. The app runs with ws="none" and the plain
    # asyncio loop, and uvicorn falls back cleanly when these are absent.
    "websockets", "wsproto", "watchfiles", "uvloop", "httptools",
]

a = Analysis(
    ["launch.py"],
    pathex=[SPECPATH],
    binaries=[],
    datas=[
        ("static", "static"),      # the entire frontend
        # GTK and Qt need a real icon file at runtime; macOS and Windows take
        # theirs from the bundle metadata instead.
        ("build-assets/icon.png", "build-assets"),
    ],
    hiddenimports=HIDDEN,
    hookspath=[],
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                     # UPX trips code signing and antivirus
    console=False,                 # no terminal window, ever
    disable_windowed_traceback=False,
    argv_emulation=IS_MAC,         # lets the .app receive dropped files
    # Native arch only. A universal2 build needs every dependency wheel to be
    # universal too, which is a fragile thing to depend on; the release
    # workflow builds Apple Silicon and Intel on separate runners instead.
    target_arch=None,
    codesign_identity=None,        # signing happens in CI, after the build
    entitlements_file=None,
    icon=str(Path(SPECPATH) / "build-assets" / ("icon.ico" if IS_WIN else "icon.png")),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=not IS_MAC,
    upx=False,
    name=APP_NAME,
)

if IS_MAC:
    app = BUNDLE(
        coll,
        name=f"{APP_NAME}.app",
        icon=str(Path(SPECPATH) / "build-assets" / "icon.icns"),
        bundle_identifier=BUNDLE_ID,
        info_plist={
            "CFBundleName": APP_NAME,
            "CFBundleDisplayName": APP_NAME,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
            # Receipts talks only to its own loopback server, but the hardened
            # runtime still needs this to allow the connection.
            "NSAppTransportSecurity": {"NSAllowsLocalNetworking": True},
        },
    )
