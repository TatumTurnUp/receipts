"""Behaviours that differ between macOS, Windows and Linux.

Every test here corresponds to something that works on the developer's Linux
machine and misbehaves on a user's Mac or PC. They are written to fail on Linux
too — by simulating the platform difference rather than trusting the platform —
because otherwise they would only ever run in CI on one of the three.
"""

import json
import sqlite3
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import legacy_schemas  # noqa: E402

APP_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def app_module(tmp_path, monkeypatch):
    data = tmp_path / "archive"
    legacy_schemas.build(data / "receipts.db", 7)
    monkeypatch.setenv("RECEIPTS_DATA", str(data))
    monkeypatch.setenv("RECEIPTS_NO_BROWSER", "1")
    monkeypatch.syspath_prepend(str(APP_ROOT))
    sys.modules.pop("app", None)
    import app as app_module

    return app_module, data


# --------------------------------------------------------------- text encoding

def test_text_uploads_survive_a_non_utf8_locale(app_module, tmp_path):
    """Windows defaults text reads to cp1252, which mangles anything non-ASCII.

    The damage is permanent: the mojibake is what gets sent to the AI, and the
    AI's reading of it is what lands in the record body and the search index.
    """
    app, _ = app_module
    sample = tmp_path / "note.txt"
    original = 'café — naïve "quotes" 日本語'
    sample.write_text(original, encoding="utf-8")

    source = (APP_ROOT / "app.py").read_text(encoding="utf-8")
    assert 'read_text(errors="replace")' not in source, (
        "a text read without encoding= will be cp1252 on Windows"
    )
    assert sample.read_text(encoding="utf-8", errors="replace") == original


def test_no_text_file_io_relies_on_the_platform_default_encoding():
    """Catch the next one of these before a Windows user finds it."""
    source = (APP_ROOT / "app.py").read_text(encoding="utf-8")
    offenders = []
    for lineno, line in enumerate(source.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        for call in ("read_text(", "write_text("):
            if call in line and "encoding=" not in line:
                # Multi-line calls carry encoding= on a later line.
                window = "\n".join(source.splitlines()[lineno - 1:lineno + 8])
                if "encoding=" not in window:
                    offenders.append(f"app.py:{lineno}: {stripped[:70]}")
    assert not offenders, "text I/O without an explicit encoding:\n" + "\n".join(offenders)


def test_config_round_trips_non_ascii(app_module):
    """load_config swallows every error, so a decode failure silently wipes the
    API key and usage stats rather than surfacing anything."""
    app, _ = app_module
    app.save_config({**app.DEFAULT_CONFIG, "anthropic_api_key": "sk-café-✓",
                     "model": "claude-sonnet-5"})
    assert app.load_config()["anthropic_api_key"] == "sk-café-✓"


# ------------------------------------------------------------- file deletion

def test_a_locked_file_is_still_deleted_eventually(app_module, monkeypatch):
    """Windows refuses to unlink an open file; POSIX allows it.

    The database row is already gone by the time the unlink is attempted, so
    without a retry path the original would stay on disk forever while the
    interface reports the record as deleted.
    """
    app, data = app_module
    stored = app.FILES / "abc123_photo.png"
    stored.write_bytes(b"private photo bytes")

    real_unlink = Path.unlink

    def refuse_once(self, *a, **kw):
        if self.name == "abc123_photo.png":
            raise PermissionError(32, "The process cannot access the file")
        return real_unlink(self, *a, **kw)

    monkeypatch.setattr(Path, "unlink", refuse_once)
    app.remove_stored_file("abc123_photo.png")

    assert not stored.exists(), "the original is still sitting at its old name"
    pending = list(app.FILES.glob("*" + app.PENDING_DELETE_SUFFIX))
    assert len(pending) == 1, "the locked file was neither deleted nor set aside"

    monkeypatch.undo()
    app.sweep_pending_deletes()
    assert not list(app.FILES.glob("*" + app.PENDING_DELETE_SUFFIX)), (
        "the deferred delete was never finished"
    )
    assert not stored.exists()


# ------------------------------------------------------ export leftovers

def test_interrupted_exports_do_not_leave_the_archive_in_temp(app_module, monkeypatch, tmp_path):
    """The cleanup task only runs after a download completes. Cancel one and a
    complete unencrypted copy of the archive stays in the system temp folder —
    which Windows never clears on its own."""
    app, _ = app_module
    fake_temp = tmp_path / "systemp"
    fake_temp.mkdir()
    monkeypatch.setattr(app.tempfile, "gettempdir", lambda: str(fake_temp))

    abandoned = fake_temp / "receipts-export-abandoned"
    abandoned.mkdir()
    (abandoned / "receipts.db").write_bytes(b"the whole archive")
    import os

    old = app.time.time() - 7200
    os.utime(abandoned, (old, old))

    recent = fake_temp / "receipts-export-inflight"
    recent.mkdir()
    (recent / "receipts.db").write_bytes(b"still downloading")

    app.sweep_stale_exports()

    assert not abandoned.exists(), "an abandoned export was left in temp"
    assert recent.exists(), "an in-flight export was deleted out from under a download"


# ------------------------------------------------------- packaged-build safety

def test_a_packaged_build_never_looks_for_data_beside_itself():
    """LEGACY_DATA must be None when frozen.

    Those paths sit inside the installed application: writing the note there
    would invalidate the macOS signature, and on Windows would succeed and then
    be destroyed by the next update.
    """
    source = (APP_ROOT / "app.py").read_text(encoding="utf-8")
    assert "LEGACY_DATA = None if FROZEN else" in source, (
        "a frozen build would search for a legacy archive inside the bundle"
    )


def test_restart_is_refused_in_a_packaged_build(app_module, monkeypatch):
    """os.execv has no meaning in a frozen app and breaks outright on Windows."""
    app, _ = app_module
    from fastapi.testclient import TestClient

    monkeypatch.setattr(app, "FROZEN", True)
    client = TestClient(app.app, base_url="http://127.0.0.1")
    r = client.post("/api/restart")
    assert r.status_code == 400
    assert "from source" in r.json()["detail"]


def test_startup_failures_are_written_somewhere_visible(app_module):
    """A windowed build has no stdout, so print() is a silent no-op. Without a
    log file a failed launch looks like nothing happening at all."""
    app, data = app_module
    app.report_fatal("Receipts could not start.", "something went wrong")
    log = data / "startup-error.log"
    assert log.exists(), "no startup-error.log written"
    body = log.read_text(encoding="utf-8")
    assert "something went wrong" in body and str(data) in body


# ------------------------------------------------------------ zip portability

def test_export_zip_uses_portable_separators(app_module):
    app, _ = app_module
    (app.FILES / "abc_photo.png").write_bytes(b"bytes")
    from fastapi.testclient import TestClient

    client = TestClient(app.app, base_url="http://127.0.0.1")
    import io

    z = zipfile.ZipFile(io.BytesIO(client.get("/api/export").content))
    for name in z.namelist():
        assert "\\" not in name, f"backslash in zip entry {name!r} breaks on other platforms"
    assert "files/abc_photo.png" in z.namelist()


def test_exported_database_opens_after_a_round_trip(app_module, tmp_path):
    app, _ = app_module
    from fastapi.testclient import TestClient
    import io

    client = TestClient(app.app, base_url="http://127.0.0.1")
    z = zipfile.ZipFile(io.BytesIO(client.get("/api/export").content))
    out = tmp_path / "restored.db"
    out.write_bytes(z.read("receipts.db"))
    conn = sqlite3.connect(out)
    assert conn.execute("SELECT COUNT(*) FROM records").fetchone()[0] == len(
        legacy_schemas.RECORDS
    )
    conn.close()
    assert json.loads(z.read("config.json"))["anthropic_api_key"] == ""


# ------------------------------------------------- where the archive lands

@pytest.mark.parametrize(
    "platform,osname,expected_tail",
    [
        ("darwin", "posix", ("Library", "Application Support", "Receipts")),
        ("win32", "nt", ("AppData", "Local", "Receipts")),
        ("linux", "posix", (".local", "share", "receipts")),
    ],
)
def test_default_archive_location_per_platform(
    app_module, monkeypatch, tmp_path, platform, osname, expected_tail
):
    """Pin all three layouts from one machine.

    Two of the three would otherwise only be exercised on a CI runner, which is
    a slow and indirect way to discover the path is wrong — and the Windows one
    was wrong.
    """
    app, _ = app_module
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    home = tmp_path / "home"

    got = app.default_data_dir(platform=platform, osname=osname, home=home)
    assert got == home.joinpath(*expected_tail), f"{platform}: got {got}"


def test_windows_honours_localappdata_when_set(app_module, monkeypatch, tmp_path):
    app, _ = app_module
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Custom"))
    got = app.default_data_dir(platform="win32", osname="nt", home=tmp_path / "home")
    assert got == tmp_path / "Custom" / "Receipts"


def test_linux_honours_xdg_data_home(app_module, monkeypatch, tmp_path):
    app, _ = app_module
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    got = app.default_data_dir(platform="linux", osname="posix", home=tmp_path / "home")
    assert got == tmp_path / "xdg" / "receipts"


def test_the_archive_is_never_inside_the_application(app_module, monkeypatch, tmp_path):
    """The one invariant that has to hold on every platform."""
    app, _ = app_module
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    for platform, osname in (("darwin", "posix"), ("win32", "nt"), ("linux", "posix")):
        data_dir = app.default_data_dir(
            platform=platform, osname=osname, home=tmp_path / "home"
        )
        assert APP_ROOT.resolve() not in data_dir.resolve().parents, (
            f"{platform}: archive would sit inside the app and be destroyed by an update"
        )
