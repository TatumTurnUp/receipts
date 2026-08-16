"""Status messages must never be able to stop the app from starting.

This is here because they did. On the Windows CI runners, ten tests failed with

    UnicodeEncodeError: 'charmap' codec can't encode character '\\u2192'

Receipts printed "Updating archive format v3 → v8" during startup, the Windows
console is cp1252, cp1252 has no arrow, and the exception propagated straight
out of init_db(). The app refused to open — because of a character in a
progress message.

It never appeared on Linux or macOS, whose consoles are UTF-8. That is the
whole reason these tests force the encoding rather than trusting the platform.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import legacy_schemas  # noqa: E402
from subprocess_env import child_env  # noqa: E402

APP_ROOT = Path(__file__).resolve().parent.parent


def run_on_console(code: str, data_dir: Path, encoding: str):
    env = child_env(RECEIPTS_DATA=data_dir, HOME=data_dir.parent)
    env["PYTHONIOENCODING"] = encoding
    return subprocess.run(
        [sys.executable, "-c", code], cwd=APP_ROOT, env=env,
        capture_output=True, text=True, errors="replace",
    )


@pytest.mark.parametrize("encoding", ["cp1252", "ascii", "utf-8"])
def test_the_app_starts_on_any_console_encoding(tmp_path, encoding):
    """A v3 archive migrating to v8 prints the message that used to be fatal."""
    data = tmp_path / "archive"
    legacy_schemas.build(data / "receipts.db", 3)

    proc = run_on_console(
        "import app; c = app.db();"
        "print('RECORDS', c.execute('SELECT COUNT(*) FROM records').fetchone()[0]);"
        "c.close()",
        data, encoding,
    )
    assert proc.returncode == 0, (
        f"Receipts failed to start on a {encoding} console:\n{proc.stdout}\n{proc.stderr}"
    )
    assert "RECORDS 5" in proc.stdout, proc.stdout


@pytest.mark.parametrize("encoding", ["cp1252", "ascii"])
def test_say_survives_characters_the_console_cannot_render(tmp_path, encoding):
    """The helper degrades the message; it never raises."""
    proc = subprocess.run(
        [sys.executable, "-c",
         "from console import say; say('arrow \\u2192 dash \\u2014 done'); print('SURVIVED')"],
        cwd=APP_ROOT, env={**child_env(), "PYTHONIOENCODING": encoding},
        capture_output=True, text=True, errors="replace",
    )
    assert proc.returncode == 0, proc.stderr
    assert "SURVIVED" in proc.stdout


def test_plain_print_really_does_fail_there(tmp_path):
    """Guard against the tests above passing for the wrong reason.

    If this ever stops failing, the environment no longer reproduces the
    Windows console and the tests above have quietly stopped proving anything.
    """
    proc = subprocess.run(
        [sys.executable, "-c", "print('v3 \\u2192 v8')"],
        env={**os.environ, "PYTHONIOENCODING": "cp1252"},
        capture_output=True, text=True, errors="replace",
    )
    assert proc.returncode != 0, "a cp1252 console accepted an arrow; the guard is broken"
    assert "UnicodeEncodeError" in proc.stderr


def test_no_console_at_all_is_survivable():
    """A packaged windowed build has sys.stdout set to None."""
    proc = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.stdout = None; from console import say; say('anything');"
         "sys.stderr.write('SURVIVED')"],
        cwd=APP_ROOT, env=child_env(), capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "SURVIVED" in proc.stderr


def test_startup_messages_stay_within_ascii_where_it_is_cheap():
    """say() is the safety net, not an excuse.

    Decorative characters in console output buy nothing and cost a fallback to
    a mangled line on the platform least able to render them.
    """
    offenders = []
    for name in ("app.py", "launch.py"):
        for lineno, line in enumerate((APP_ROOT / name).read_text(encoding="utf-8").splitlines(), 1):
            if "say(" not in line or line.strip().startswith("#"):
                continue
            exotic = [c for c in line if ord(c) > 127]
            if exotic:
                offenders.append(f"{name}:{lineno} {exotic} in {line.strip()[:60]}")
    assert not offenders, "non-ASCII in console output:\n" + "\n".join(offenders)
