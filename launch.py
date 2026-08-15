"""Receipts as a desktop app.

Starts the server on a private local port and opens it in a native window, so
Receipts looks and behaves like an installed application: its own icon in the
Dock or taskbar, no browser chrome, no localhost address on screen.

The window is the OS's own web view — WKWebView on macOS, WebView2 on Windows,
WebKitGTK on Linux — so the interface renders exactly as it does in a browser
without shipping a second browser to do it.

Run directly (`python launch.py`) or as the entry point of a packaged build.
`python app.py` still works and still opens a browser tab, which stays the
quicker loop while developing.
"""

import os
import socket
import sys
import threading
import time
from contextlib import closing

os.environ.setdefault("RECEIPTS_NO_BROWSER", "1")  # the window is the browser

HOST = "127.0.0.1"
PREFERRED_PORT = 8765


def free_port() -> int:
    """Prefer the familiar port; take any free one rather than fail.

    A fixed port collides when a second copy is running or another app got
    there first, and it is also the easiest thing for a malicious web page to
    guess. Falling back to an ephemeral port fixes both.
    """
    with closing(socket.socket()) as s:
        try:
            s.bind((HOST, PREFERRED_PORT))
            return PREFERRED_PORT
        except OSError:
            pass
    with closing(socket.socket()) as s:
        s.bind((HOST, 0))
        return s.getsockname()[1]


def wait_until_up(port: int, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with closing(socket.socket()) as s:
            s.settimeout(0.4)
            if s.connect_ex((HOST, port)) == 0:
                return True
        time.sleep(0.15)
    return False


def main() -> int:
    try:
        import uvicorn
    except ImportError:
        print("Missing dependencies. Install with:\n    pip install -r requirements.txt")
        return 1

    # Imported after the env var is set, and inside main(), so that a failure
    # to open the archive prints its own message and exits cleanly.
    import app as receipts
    from version import APP_NAME, display_version

    port = free_port()
    title = f"{APP_NAME} {display_version()}"
    url = f"http://{HOST}:{port}"

    server = uvicorn.Server(
        uvicorn.Config(receipts.app, host=HOST, port=port, log_level="warning")
    )
    threading.Thread(target=server.run, daemon=True).start()

    if not wait_until_up(port):
        print("Receipts could not start its local server.")
        return 1

    try:
        import webview
    except ImportError:
        # No native web view available — a Linux box without WebKitGTK, say.
        # Falling back to the default browser keeps Receipts usable instead of
        # failing to open at all; everything but the window frame is identical.
        import webbrowser

        print(f"\n  {title}\n  Opening in your browser → {url}\n  Close this window to quit.\n")
        webbrowser.open(url)
        try:
            while not server.should_exit:
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        return 0

    window = webview.create_window(
        title, url, width=1280, height=860, min_size=(900, 600), text_select=True
    )
    window.events.closed += lambda: setattr(server, "should_exit", True)

    webview.start()  # blocks until the window closes
    server.should_exit = True
    return 0


if __name__ == "__main__":
    sys.exit(main())
