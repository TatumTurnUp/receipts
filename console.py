"""Console output that cannot take the app down with it.

Receipts prints a handful of status lines at startup — which archive it found,
which format it migrated, why it could not open. On Linux and macOS that is
unremarkable. On Windows it was fatal.

A Windows console defaults to cp1252, which has no arrow and no em dash. A
plain print() containing either raises UnicodeEncodeError, and since these
lines are printed from inside startup, that exception propagated and Receipts
refused to open at all. An app that will not launch because of a character in
a status message is a bad trade, and it is exactly the kind of failure that
never shows up on the machine it was written on.

There is a second, quieter case: a packaged windowed build has no console, so
sys.stdout is None on Windows and inside a macOS .app.

say() handles both. Import it instead of using print().
"""

import sys


def _prefer_utf8() -> None:
    """Ask for UTF-8 where the console can take it, so nice characters survive."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass  # None, or a stream that does not support it


_prefer_utf8()


def say(message: str = "") -> None:
    """Print a line, degrading rather than raising, whatever the console is."""
    if sys.stdout is None:
        return
    try:
        print(message)
    except UnicodeEncodeError:
        # Last resort: strip it down to something every console can render.
        try:
            print(message.encode("ascii", "replace").decode("ascii"))
        except Exception:
            pass
    except Exception:
        pass
