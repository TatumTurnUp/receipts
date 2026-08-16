"""The server must start on a real machine, not just a clean one.

Reproduces a failure hit on a normal Linux desktop: the distro ships an older
`websockets` package in /usr/lib/python3/dist-packages, uvicorn came from
pip and is newer, and uvicorn's startup import of a WebSocket backend blew up
with `cannot import name 'ServerProtocol'`. The whole app failed to launch over
a feature it does not have — Receipts serves no WebSocket endpoints at all.

The fix is ws="none". These tests pin it, and prove it matters by breaking
`websockets` on purpose and checking the server still comes up.
"""

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from subprocess_env import child_env  # noqa: E402

APP_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def broken_websockets(tmp_path):
    """A `websockets` package too old for modern uvicorn, first on the path."""
    shim = tmp_path / "shim"
    pkg = shim / "websockets"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text('__version__ = "9.0"\n')
    # Present, importable, but missing the name uvicorn wants — exactly the
    # shape of the real failure.
    (pkg / "server.py").write_text("class WebSocketServerProtocol:\n    pass\n")
    (pkg / "legacy").mkdir()
    (pkg / "legacy" / "__init__.py").write_text("")
    return shim


def run_child(code: str, data_dir: Path, extra_path: Path | None = None):
    env = child_env(RECEIPTS_DATA=data_dir, HOME=data_dir.parent)
    if extra_path:
        env["PYTHONPATH"] = f"{extra_path}:{env['PYTHONPATH']}"
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        cwd=APP_ROOT, env=env, capture_output=True, text=True,
    )


LOAD_CONFIG = """
    import uvicorn, app
    cfg = uvicorn.Config(app.app, host="127.0.0.1", port=0, log_level="warning", ws={ws!r})
    cfg.load()
    print("CONFIG LOADED")
"""


def test_server_starts_with_an_outdated_websockets_package(tmp_path, broken_websockets):
    """The actual bug: this must succeed despite the broken package."""
    proc = run_child(LOAD_CONFIG.format(ws="none"), tmp_path / "archive", broken_websockets)
    assert "CONFIG LOADED" in proc.stdout, (
        "the server failed to start with an outdated websockets package "
        f"installed:\n{proc.stdout}\n{proc.stderr}"
    )


def test_the_shim_really_does_break_the_default(tmp_path, broken_websockets):
    """Guard against the test above passing for the wrong reason.

    If this ever stops failing, the shim no longer reproduces the problem and
    the test above has quietly stopped proving anything.
    """
    proc = run_child(LOAD_CONFIG.format(ws="auto"), tmp_path / "archive2", broken_websockets)
    if proc.returncode == 0:
        pytest.skip("this uvicorn build does not import websockets on 'auto'")
    assert "websockets" in (proc.stdout + proc.stderr).lower()


def test_launch_configures_the_server_without_websockets():
    """Pin the setting itself, so nobody restores the default by tidying up."""
    source = (APP_ROOT / "launch.py").read_text()
    assert 'ws="none"' in source, "launch.py must start uvicorn with ws='none'"

    app_source = (APP_ROOT / "app.py").read_text()
    assert 'ws="none"' in app_source, "app.py's own entrypoint needs it too"


def test_app_declares_no_websocket_routes():
    """The reasoning above only holds while this stays true."""
    sys.path.insert(0, str(APP_ROOT))
    import app as receipts

    ws_routes = [
        r for r in receipts.app.routes if type(r).__name__ == "WebSocketRoute"
    ]
    assert not ws_routes, (
        f"Receipts now has WebSocket routes ({ws_routes}) — ws='none' must be "
        "revisited, and a compatible websockets version pinned in requirements"
    )
