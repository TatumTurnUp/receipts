"""Where the archive lives, and how it gets there.

The bug these exist to prevent: user data stored inside the application
folder. Installing an update replaces that folder, so an archive kept there is
destroyed on the first update — silently, and completely.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import legacy_schemas  # noqa: E402
from test_migrations import PROBE, run_app  # noqa: E402

APP_ROOT = Path(__file__).resolve().parent.parent
LEGACY = APP_ROOT / "receipts-data"


@pytest.fixture
def no_legacy_folder():
    """Guarantee the repo has no ./receipts-data before and after each test."""
    stash = None
    if LEGACY.exists():
        stash = APP_ROOT / "receipts-data.teststash"
        shutil.move(str(LEGACY), str(stash))
    yield
    shutil.rmtree(LEGACY, ignore_errors=True)
    if stash:
        shutil.move(str(stash), str(LEGACY))


def run_with_home(home: Path):
    """Import app.py with no RECEIPTS_DATA, so the default location is used."""
    proc = subprocess.run(
        [sys.executable, "-c", PROBE],
        cwd=APP_ROOT,
        env={"PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(home),
             "XDG_DATA_HOME": str(home / ".local" / "share"),
             "RECEIPTS_NO_BROWSER": "1"},
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return json.loads(proc.stdout.split("---PROBE---")[-1].strip()), proc


def test_default_location_is_outside_the_app_folder(tmp_path, no_legacy_folder):
    state, _ = run_with_home(tmp_path)
    data_dir = Path(state["data_dir"]).resolve()

    assert APP_ROOT.resolve() not in data_dir.parents and data_dir != APP_ROOT.resolve(), (
        f"archive at {data_dir} is inside the app folder — an update would destroy it"
    )
    assert str(tmp_path) in str(data_dir)


def test_legacy_archive_is_adopted_without_being_destroyed(tmp_path, no_legacy_folder):
    """A pre-1.0 ./receipts-data must be copied out, and the original kept."""
    legacy_schemas.build(LEGACY / "receipts.db", 7)
    (LEGACY / "files").mkdir(parents=True, exist_ok=True)
    (LEGACY / "files" / "screenshot.png").write_bytes(b"fake image bytes")
    (LEGACY / "config.json").write_text(json.dumps({"model": "claude-sonnet-5"}))
    original_db = (LEGACY / "receipts.db").read_bytes()

    state, _ = run_with_home(tmp_path)
    new_dir = Path(state["data_dir"])

    # Everything came across.
    assert (new_dir / "receipts.db").exists()
    assert (new_dir / "files" / "screenshot.png").read_bytes() == b"fake image bytes"
    assert json.loads((new_dir / "config.json").read_text())["model"] == "claude-sonnet-5"
    assert len(state["records"]) == len(legacy_schemas.RECORDS)

    # The original is a COPY left intact — the whole point of the safety net.
    assert (LEGACY / "receipts.db").exists(), "original archive was moved, not copied"
    assert (LEGACY / "receipts.db").read_bytes() == original_db
    assert (LEGACY / "files" / "screenshot.png").exists()
    assert (LEGACY / "MOVED-README.txt").exists(), "no note left explaining the move"


def test_adoption_never_overwrites_an_existing_archive(tmp_path, no_legacy_folder):
    """If the user already has a real archive, a stale ./receipts-data loses."""
    home = tmp_path
    existing = home / ".local" / "share" / "receipts"
    legacy_schemas.build(existing / "receipts.db", 7)
    marker = existing / "files" / "keepme.txt"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("the live archive")

    # A stale legacy folder with different contents.
    legacy_schemas.build(LEGACY / "receipts.db", 3)
    (LEGACY / "files").mkdir(parents=True, exist_ok=True)
    (LEGACY / "files" / "stale.txt").write_text("old")

    state, _ = run_with_home(home)

    assert marker.read_text() == "the live archive"
    assert not (existing / "files" / "stale.txt").exists(), "stale data leaked in"
    assert not (LEGACY / "MOVED-README.txt").exists(), "adoption ran when it should not have"


def test_env_override_wins_and_skips_adoption(tmp_path, no_legacy_folder):
    """RECEIPTS_DATA is the dev escape hatch: explicit, and never adopts."""
    legacy_schemas.build(LEGACY / "receipts.db", 7)
    scratch = tmp_path / "dev-archive"

    state, _ = run_app(scratch)

    assert Path(state["data_dir"]) == scratch
    assert state["records"] == [], "dev archive should start empty, not adopt real data"
    assert not (LEGACY / "MOVED-README.txt").exists()
