"""Migration safety tests.

The contract these enforce: opening an older archive with today's code brings
the schema forward and does not lose, alter or reorder a single row of the
user's data. This is the test suite that lets updates ship without holding
your breath — if it passes, an update cannot silently eat someone's history.

Each case runs in a subprocess because app.py opens and migrates the archive
at import time, so one Python process can only ever exercise one archive.
"""

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import legacy_schemas  # noqa: E402
from subprocess_env import child_env  # noqa: E402

APP_ROOT = Path(__file__).resolve().parent.parent

# Runs inside the app's process: import triggers migration, then report back.
PROBE = """
import json, sys
import app
conn = app.db()
out = {
    "user_version": conn.execute("PRAGMA user_version").fetchone()[0],
    "schema_version": app.SCHEMA_VERSION,
    "records": [dict(r) for r in conn.execute("SELECT * FROM records ORDER BY id")],
    "modules": [dict(r) for r in conn.execute("SELECT * FROM modules ORDER BY id")],
    "change_log": [dict(r) for r in conn.execute("SELECT * FROM change_log ORDER BY id")],
    "amendments": [dict(r) for r in conn.execute("SELECT * FROM amendments ORDER BY id")],
    "tags": [dict(r) for r in conn.execute("SELECT * FROM tags ORDER BY name")],
    "data_dir": str(app.DATA),
}
conn.close()
print("---PROBE---" + json.dumps(out))
"""


def run_app(data_dir: Path, code: str = PROBE, expect_ok: bool = True):
    """Import app.py against `data_dir` and return its reported state."""
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=APP_ROOT,
        env=child_env(RECEIPTS_DATA=data_dir, HOME=data_dir.parent),
        capture_output=True,
        text=True,
    )
    if not expect_ok:
        return proc
    assert proc.returncode == 0, f"app failed to start:\n{proc.stdout}\n{proc.stderr}"
    marker = proc.stdout.split("---PROBE---")[-1].strip()
    return json.loads(marker), proc


@pytest.mark.parametrize("from_version", [3, 7])
def test_migration_preserves_all_data(tmp_path, from_version):
    data = tmp_path / "archive"
    legacy_schemas.build(data / "receipts.db", from_version)

    state, _ = run_app(data)

    # Schema moved forward to current.
    assert state["user_version"] == state["schema_version"]

    # Nothing was lost.
    assert len(state["records"]) == len(legacy_schemas.RECORDS)
    assert len(state["modules"]) == 1
    assert len(state["change_log"]) == 2
    assert len(state["amendments"]) == 1

    # Original values survived untouched.
    by_id = {r["id"]: r for r in state["records"]}
    for rid, kind, title, ts_source, _, _ in legacy_schemas.RECORDS:
        assert by_id[rid]["title"] == title
        assert by_id[rid]["kind"] == kind
        assert by_id[rid]["ts_source"] == ts_source
        assert by_id[rid]["body"] == "body text"
        assert by_id[rid]["description"] == "a description"
        assert by_id[rid]["module_id"] == "mod_laura"
    assert state["modules"][0]["name"] == "Laura"
    assert state["amendments"][0]["added_text"] == "more detail"


@pytest.mark.parametrize("from_version", [3, 7])
def test_new_columns_exist_after_migration(tmp_path, from_version):
    data = tmp_path / "archive"
    legacy_schemas.build(data / "receipts.db", from_version)
    state, _ = run_app(data)

    rec = state["records"][0]
    for col in ("ts_score", "link_meta"):
        assert col in rec, f"records.{col} missing after migration"
    assert "tags_json" in state["modules"][0]
    for col in ("module_id", "entity_label"):
        assert col in state["change_log"][0], f"change_log.{col} missing"


def test_v5_backfill_maps_confidence_to_score(tmp_path):
    """The ts_score backfill must derive real values, not leave everything 0."""
    data = tmp_path / "archive"
    legacy_schemas.build(data / "receipts.db", 3)
    state, _ = run_app(data)

    by_id = {r["id"]: r for r in state["records"]}
    for rid, _, _, _, _, expected_score in legacy_schemas.RECORDS:
        assert by_id[rid]["ts_score"] == expected_score, (
            f"{rid}: expected ts_score {expected_score}, got {by_id[rid]['ts_score']}"
        )


def test_v4_backfill_populates_change_log_module_id(tmp_path):
    data = tmp_path / "archive"
    legacy_schemas.build(data / "receipts.db", 3)
    state, _ = run_app(data)

    by_id = {c["id"]: c for c in state["change_log"]}
    assert by_id["cl_1"]["module_id"] == "mod_laura"  # from the record it points at
    assert by_id["cl_2"]["module_id"] == "mod_laura"  # module rows use their own id


def test_v8_backfills_tag_registry_from_modules(tmp_path):
    data = tmp_path / "archive"
    legacy_schemas.build(data / "receipts.db", 7)
    state, _ = run_app(data)

    names = {t["name"] for t in state["tags"]}
    assert {"friend", "austin"} <= names


def test_pre_migration_snapshot_is_created_and_never_pruned(tmp_path):
    data = tmp_path / "archive"
    legacy_schemas.build(data / "receipts.db", 3)
    run_app(data)

    snaps = list((data / "backups").glob("snapshot-pre-v3-to-v*.db"))
    assert len(snaps) == 1, f"expected one pre-migration snapshot, found {snaps}"

    # The snapshot must be the archive as it was BEFORE the change.
    conn = sqlite3.connect(snaps[0])
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 3
    assert conn.execute("SELECT COUNT(*) FROM records").fetchone()[0] == len(
        legacy_schemas.RECORDS
    )
    conn.close()

    # Daily-backup pruning must not touch snapshots, however many days pass.
    bdir = data / "backups"
    for day in range(1, 40):
        (bdir / f"receipts-2026{day:04d}.db").write_bytes(b"")
    run_app(data)
    assert (data / "backups" / snaps[0].name).exists(), "snapshot was pruned"


def test_second_launch_is_a_no_op(tmp_path):
    """Re-running an already-current archive must not re-migrate or re-snapshot."""
    data = tmp_path / "archive"
    legacy_schemas.build(data / "receipts.db", 7)
    run_app(data)
    first = {p.name for p in (data / "backups").glob("snapshot-*.db")}
    run_app(data)
    second = {p.name for p in (data / "backups").glob("snapshot-*.db")}
    assert first == second, "a second launch created a redundant snapshot"


def test_archive_from_the_future_is_refused(tmp_path):
    """An older build must refuse a newer archive instead of corrupting it."""
    data = tmp_path / "archive"
    db = data / "receipts.db"
    legacy_schemas.build(db, 7)
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA user_version=99")
    conn.commit()
    conn.close()
    before = db.read_bytes()

    proc = run_app(data, expect_ok=False)
    assert proc.returncode != 0, "app started against an archive it cannot understand"
    assert "newer version" in (proc.stdout + proc.stderr).lower()
    assert db.read_bytes() == before, "refused archive was modified anyway"


def test_failed_migration_rolls_back(tmp_path):
    """A migration that throws must leave the archive exactly as it was.

    Drives migrate() directly with a deliberately broken step: the version
    must not advance, and the user's rows must all still be there.
    """
    data = tmp_path / "archive"
    legacy_schemas.build(data / "receipts.db", 3)

    inject = """
import sqlite3, importlib.util
spec = importlib.util.spec_from_file_location("app_mod", "app.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)          # normal startup: archive is now current

conn = mod.db()
conn.execute("PRAGMA user_version=3") # pretend we are back at v3
conn.commit()
mod.MIGRATIONS[mod.SCHEMA_VERSION] = ["UPDATE nonexistent_table SET x=1"]
try:
    mod.migrate(conn)
    print("NO-FAILURE")
except Exception:
    print("EXPECTED-FAILURE")
conn.close()
"""
    proc = subprocess.run(
        [sys.executable, "-c", inject],
        cwd=APP_ROOT,
        env=child_env(RECEIPTS_DATA=data, HOME=tmp_path),
        capture_output=True, text=True,
    )
    assert "EXPECTED-FAILURE" in proc.stdout, proc.stdout + proc.stderr

    conn = sqlite3.connect(data / "receipts.db")
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 3, (
        "schema version advanced even though the migration failed"
    )
    assert conn.execute("SELECT COUNT(*) FROM records").fetchone()[0] == len(
        legacy_schemas.RECORDS
    )
    conn.close()
