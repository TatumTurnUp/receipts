"""Environment for test subprocesses.

Several tests launch app.py in a child process with HOME pointed at a temporary
directory, because HOME is what decides where the archive lands — that is the
whole thing being tested.

There is a trap in that. Python also derives the per-user site-packages
directory from HOME, so a fake HOME hides every dependency installed with
`pip install --user` — which is the default on most Linux distributions and on
macOS outside a virtualenv. The child then dies with ModuleNotFoundError on
`import fastapi`, long before it reaches anything the test is actually about,
and the failure looks like a bug in the app rather than in the harness.

It also hides itself: on a machine where the dependencies happen to be
installed system-wide, every one of these tests passes. That is why this needs
to be one shared helper rather than an env dict copy-pasted per call site.

The fix: inherit the real environment, pin the paths this process is genuinely
importing from onto PYTHONPATH while HOME is still correct, and only then apply
the overrides.
"""

import os
import site
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent


def _import_paths():
    """Every directory this process can import from, most specific first."""
    paths = [str(APP_ROOT)]

    try:
        if site.ENABLE_USER_SITE:
            paths.append(site.getusersitepackages())
    except Exception:
        pass

    try:
        paths.extend(site.getsitepackages())
    except AttributeError:  # some virtualenv layouts do not provide it
        pass

    # sys.path is the ground truth: whatever imports work here will work in the
    # child, whatever the installation layout turns out to be.
    paths.extend(sys.path)

    seen, unique = set(), []
    for p in paths:
        if p and p not in seen:
            seen.add(p)
            unique.append(p)
    return unique


def child_env(**overrides) -> dict:
    """A real environment for a child process, plus the given overrides."""
    env = os.environ.copy()

    inherited = env.get("PYTHONPATH")
    parts = _import_paths() + ([inherited] if inherited else [])
    env["PYTHONPATH"] = os.pathsep.join(parts)

    env["RECEIPTS_NO_BROWSER"] = "1"
    env.update({k: str(v) for k, v in overrides.items()})
    return env
