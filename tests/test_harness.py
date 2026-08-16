"""Tests for the test harness itself.

These exist because of a real failure. Several tests run app.py in a child
process with HOME redirected to a temp directory. Python derives the per-user
site-packages path from HOME, so those children could not import fastapi on any
machine where dependencies were installed with `pip install --user` — the
default on most Linux distributions and on macOS outside a virtualenv.

The nasty part is that it passed on machines with system-wide installs, so the
suite looked green while being incapable of testing anything on a normal
developer setup. These tests pin the fix so it cannot regress quietly.
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from subprocess_env import child_env  # noqa: E402

APP_ROOT = Path(__file__).resolve().parent.parent


def test_child_can_import_the_app_with_a_redirected_home(tmp_path):
    """The exact failure: fake HOME must not hide installed dependencies."""
    proc = subprocess.run(
        [sys.executable, "-c", "import fastapi, uvicorn; print('IMPORTS OK')"],
        cwd=APP_ROOT,
        env=child_env(HOME=tmp_path, XDG_DATA_HOME=tmp_path / ".local" / "share"),
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, (
        "a child with a redirected HOME could not import the app's "
        f"dependencies:\n{proc.stdout}\n{proc.stderr}"
    )
    assert "IMPORTS OK" in proc.stdout


def test_child_env_pins_the_real_import_paths(tmp_path):
    """Guard the mechanism, not just the symptom.

    The import test above passes for the wrong reason on machines with
    system-wide installs, so assert the paths are actually being carried over.
    """
    env = child_env(HOME=tmp_path)
    assert "PYTHONPATH" in env, "child_env must pin an explicit import path"

    pinned = env["PYTHONPATH"].split(":" if sys.platform != "win32" else ";")
    assert str(APP_ROOT) in pinned, "the app itself must be importable"

    import fastapi

    fastapi_dir = str(Path(fastapi.__file__).parent.parent)
    assert any(Path(p) == Path(fastapi_dir) for p in pinned if p), (
        f"the directory fastapi actually lives in ({fastapi_dir}) is not pinned; "
        "a child with a redirected HOME would fail to import it"
    )


def test_child_env_does_not_leak_a_stale_archive_path(tmp_path):
    """A RECEIPTS_DATA set in the developer's own shell must not hijack tests."""
    env = child_env(HOME=tmp_path, RECEIPTS_DATA=tmp_path / "explicit")
    assert env["RECEIPTS_DATA"] == str(tmp_path / "explicit")
    assert env["RECEIPTS_NO_BROWSER"] == "1"
