"""The app window must carry the Receipts icon, not a generic placeholder.

GTK and Qt only take an icon at runtime, via webview.start(icon=...). macOS and
Windows read theirs from the application bundle, so launch.py must not pass a
path on those platforms — and the packaging spec must actually ship the file
that the Linux path points at.
"""

import sys
from pathlib import Path

import pytest

APP_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_ROOT))

import launch  # noqa: E402


def test_the_icon_file_exists_where_launch_looks_for_it():
    icon = APP_ROOT / "build-assets" / "icon.png"
    assert icon.exists(), (
        "build-assets/icon.png is missing — regenerate it with "
        "`python build-assets/make_icons.py`"
    )
    assert icon.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n", "not a real PNG"


@pytest.mark.skipif(
    sys.platform == "darwin" or sys.platform == "win32",
    reason="runtime icons are a GTK/Qt thing",
)
def test_linux_gets_a_runtime_icon_path():
    icon = launch.window_icon()
    assert icon is not None, "Linux window would fall back to a generic icon"
    assert Path(icon).exists()


def test_packaging_ships_the_icon():
    """The runtime path is inside the bundle, so the bundle must contain it."""
    spec = (APP_ROOT / "receipts.spec").read_text()
    assert "build-assets/icon.png" in spec, (
        "receipts.spec does not bundle build-assets/icon.png, so window_icon() "
        "would find nothing in a packaged build"
    )


def test_mac_and_windows_do_not_get_a_runtime_path(monkeypatch):
    """Passing one there is a no-op at best; the bundle is the source of truth."""
    monkeypatch.setattr(sys, "platform", "darwin")
    assert launch.window_icon() is None

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(launch.os, "name", "nt")
    assert launch.window_icon() is None
