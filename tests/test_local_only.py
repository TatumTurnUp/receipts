"""Receipts must only answer to itself.

The server listens on 127.0.0.1, which is not the same as being private: any
web page open in the user's browser can fire requests at a local port, and this
server will hand back a person's entire archive to whoever asks. These tests
pin the two checks that stop that.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import legacy_schemas  # noqa: E402

APP_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def client(tmp_path, monkeypatch):
    data = tmp_path / "archive"
    legacy_schemas.build(data / "receipts.db", 7)
    monkeypatch.setenv("RECEIPTS_DATA", str(data))
    monkeypatch.setenv("RECEIPTS_NO_BROWSER", "1")
    monkeypatch.syspath_prepend(str(APP_ROOT))
    sys.modules.pop("app", None)

    from fastapi.testclient import TestClient
    import app as app_module

    return TestClient(app_module.app, base_url="http://127.0.0.1")


@pytest.mark.parametrize("origin", [
    "https://evil.example",
    "http://evil.example",
    "http://127.0.0.1.evil.example",
    "null",
])
def test_requests_from_other_websites_are_refused(client, origin):
    r = client.get("/api/stats", headers={"Origin": origin})
    assert r.status_code == 403, f"{origin} was allowed to read the archive"


def test_our_own_origin_is_allowed(client):
    r = client.get("/api/stats", headers={"Origin": "http://127.0.0.1"})
    assert r.status_code == 200


def test_requests_with_no_origin_still_work(client):
    """Image tags and the export download are same-origin and send no Origin."""
    assert client.get("/api/stats").status_code == 200


@pytest.mark.parametrize("host", ["evil.example", "receipts.attacker.net"])
def test_dns_rebinding_is_refused(client, host):
    """A remote domain re-pointed at 127.0.0.1 must not get in."""
    r = client.get("/api/stats", headers={"Host": host})
    assert r.status_code == 400, f"host {host} was accepted"


def test_loopback_hosts_are_accepted(client):
    for host in ("127.0.0.1", "localhost", "127.0.0.1:8765"):
        assert client.get("/api/stats", headers={"Host": host}).status_code == 200, host


def test_health_reports_version_and_channel(client):
    body = client.get("/api/health").json()
    assert "version" in body and "channel" in body
    assert body["schema_version"] >= 8


def test_writes_are_blocked_cross_origin(client):
    """Not just reads — a hostile page must not be able to change anything."""
    r = client.post(
        "/api/modules",
        headers={"Origin": "https://evil.example"},
        json={"name": "injected", "type": "person"},
    )
    assert r.status_code == 403
    names = [m["name"] for m in client.get("/api/modules").json()]
    assert "injected" not in names
