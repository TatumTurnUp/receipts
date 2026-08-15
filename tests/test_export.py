"""The export escape hatch, and search surviving a migration.

Export is what makes a user whole no matter what goes wrong, so it has to work
on a freshly migrated archive, contain everything, and never leak an API key.
"""

import io
import json
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import legacy_schemas  # noqa: E402

APP_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A TestClient bound to a freshly migrated v3 archive."""
    data = tmp_path / "archive"
    legacy_schemas.build(data / "receipts.db", 3)
    (data / "files").mkdir(parents=True, exist_ok=True)
    (data / "files" / "screenshot.png").write_bytes(b"fake png bytes")
    (data / "config.json").write_text(
        json.dumps({"anthropic_api_key": "sk-ant-SECRET-DO-NOT-LEAK", "model": "claude-sonnet-5"})
    )

    monkeypatch.setenv("RECEIPTS_DATA", str(data))
    monkeypatch.setenv("RECEIPTS_NO_BROWSER", "1")
    monkeypatch.syspath_prepend(str(APP_ROOT))
    for mod in ("app",):
        sys.modules.pop(mod, None)

    from fastapi.testclient import TestClient
    import app as app_module

    return TestClient(app_module.app), data


def test_export_contains_the_whole_archive(client):
    c, data = client
    r = c.get("/api/export")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"

    z = zipfile.ZipFile(io.BytesIO(r.content))
    names = set(z.namelist())
    assert "receipts.db" in names
    assert "README.txt" in names
    assert "config.json" in names
    assert "files/screenshot.png" in names
    assert z.read("files/screenshot.png") == b"fake png bytes"
    assert z.read("receipts.db")[:16] == b"SQLite format 3\x00"


def test_export_never_leaks_the_api_key(client):
    c, _ = client
    r = c.get("/api/export")
    z = zipfile.ZipFile(io.BytesIO(r.content))

    cfg = json.loads(z.read("config.json"))
    assert cfg["anthropic_api_key"] == ""
    assert cfg["model"] == "claude-sonnet-5", "other settings should survive"
    assert b"SECRET-DO-NOT-LEAK" not in r.content


def test_exported_database_is_readable_and_complete(client, tmp_path):
    import sqlite3

    c, _ = client
    z = zipfile.ZipFile(io.BytesIO(c.get("/api/export").content))
    out = tmp_path / "restored.db"
    out.write_bytes(z.read("receipts.db"))

    conn = sqlite3.connect(out)
    assert conn.execute("SELECT COUNT(*) FROM records").fetchone()[0] == len(
        legacy_schemas.RECORDS
    )
    assert conn.execute("SELECT name FROM modules").fetchone()[0] == "Laura"
    conn.close()


def test_search_works_after_migration(client):
    """The reindex must leave full-text search actually functional."""
    c, _ = client
    r = c.get("/api/search", params={"q": "Brewskys"})
    assert r.status_code == 200
    hits = r.json()
    titles = [h.get("title", "") for h in (hits if isinstance(hits, list) else hits.get("results", []))]
    assert any("Brewskys" in t for t in titles), f"search returned nothing useful: {hits}"


def test_stats_reports_the_data_directory(client):
    c, data = client
    body = c.get("/api/stats").json()
    assert Path(body["data_dir"]) == data
    assert body["records"] == len(legacy_schemas.RECORDS)
    assert body["schema_version"] >= 8
