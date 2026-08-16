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

import inspect
import os
import socket
import sys
import threading
import time
from contextlib import closing
from pathlib import Path

from console import say

os.environ.setdefault("RECEIPTS_NO_BROWSER", "1")  # the window is the browser

HOST = "127.0.0.1"
PREFERRED_PORT = 8765

# Bundled read-only assets. PyInstaller unpacks them somewhere temporary, which
# is not where this file lives, so resolve both cases the same way app.py does.
ASSETS = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


APP_ID = "receipts"  # must match receipts.desktop and the installed icon name


def window_icon():
    """Path to the window icon, or None if the platform sets it another way.

    Only GTK and Qt take an icon at runtime. macOS and Windows read it from the
    application bundle instead, which receipts.spec already handles — passing a
    path there would do nothing.
    """
    if sys.platform == "darwin" or os.name == "nt":
        return None
    icon = ASSETS / "build-assets" / "icon.png"
    return str(icon) if icon.exists() else None


def set_app_identity() -> None:
    """Tell the desktop which application this window belongs to.

    Under X11 a window can hand the window manager a picture directly, which is
    what window_icon() is for. Wayland does not work that way: it ignores the
    picture entirely and instead matches the window's app id against an
    installed .desktop file, taking the icon from there. If nothing matches,
    you get a blank space in the dock — which is exactly what was reported.

    GTK derives that app id from argv[0] unless told otherwise, so it would be
    "launch.py" from source and "Receipts" from the packaged build, while the
    desktop file is receipts.desktop. Pinning it here makes all three agree.
    """
    if sys.platform == "darwin" or os.name == "nt":
        return
    try:
        import gi

        gi.require_version("Gtk", "3.0")
        from gi.repository import GLib

        GLib.set_prgname(APP_ID)
        GLib.set_application_name("Receipts")
    except Exception:
        # No GTK bindings, or a Qt backend — the icon path still covers X11.
        pass


def windows_webview_missing() -> bool:
    """True when Windows lacks the Edge WebView2 runtime.

    This has to be checked up front. Without the runtime, pywebview does not
    raise — it quietly falls back to the ancient IE engine, which cannot parse
    the app's JavaScript. The user gets a blank white window, and because
    nothing failed, the browser fallback never runs. A blank window is a much
    worse outcome than a browser tab, so detect it and choose the tab.
    """
    if os.name != "nt":
        return False
    import winreg

    key = (
        r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients"
        r"\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
    )
    for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(root, key):
                return False
        except OSError:
            continue
    return True


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
        say("Missing dependencies. Install with:\n    pip install -r requirements.txt")
        return 1

    # Imported after the env var is set, and inside main(), so that a failure
    # to open the archive prints its own message and exits cleanly.
    import app as receipts
    from version import APP_NAME, display_version

    port = free_port()
    title = f"{APP_NAME} {display_version()}"
    url = f"http://{HOST}:{port}"

    server = uvicorn.Server(
        uvicorn.Config(
            receipts.app,
            host=HOST,
            port=port,
            log_level="warning",
            # Receipts has no WebSocket endpoints. Left on "auto", uvicorn
            # imports a WebSocket backend at startup anyway, and on a machine
            # whose system `websockets` package is older than uvicorn expects
            # that import raises and takes the whole server down — for a
            # feature the app never uses. Turning it off removes the failure
            # and a dependency we have no need of.
            ws="none",
        )
    )

    # Without this, a server that dies on startup surfaces only as a bare
    # "could not start", with the real reason buried in a thread traceback.
    startup_error: list[BaseException] = []

    def run_server():
        try:
            server.run()
        except BaseException as exc:  # noqa: BLE001 — reported below, then re-raised nowhere
            startup_error.append(exc)

    threading.Thread(target=run_server, daemon=True).start()

    if not wait_until_up(port):
        say("\n  Receipts could not start its local server.")
        if startup_error:
            err = startup_error[0]
            say(f"  {type(err).__name__}: {err}")
            if isinstance(err, ImportError):
                say(
                    "\n  This usually means one of Receipts' dependencies is out of date.\n"
                    "  Try:  pip3 install --upgrade -r requirements.txt\n"
                )
        else:
            say(f"  Nothing was listening on port {port} after 30 seconds.\n")
        return 1

    def open_in_browser(reason: str = "") -> int:
        """Last resort: hand the running server to the default browser.

        Everything except the window frame is identical, so this keeps Receipts
        fully usable on a machine that cannot give it a native window.
        """
        import webbrowser

        say(f"\n  {title}")
        if reason:
            say(f"  (no app window available - {reason})")
        say(f"  Opening in your browser -> {url}")
        say("  Press Ctrl-C here when you're done.\n")
        webbrowser.open(url)
        try:
            while not server.should_exit:
                time.sleep(0.5)
        except KeyboardInterrupt:
            say("\n  Closing Receipts.")
        return 0

    try:
        import webview
    except ImportError:
        return open_in_browser("pywebview is not installed")

    if windows_webview_missing():
        return open_in_browser("the Microsoft Edge WebView2 runtime is not installed")

    set_app_identity()

    try:
        window = webview.create_window(
            title, url, width=1280, height=860, min_size=(900, 600), text_select=True
        )
        window.events.closed += lambda: setattr(server, "should_exit", True)

        # Check the signature rather than catching TypeError: this call is
        # inside the browser-fallback handler below, so a bad keyword would
        # silently demote a working window to a browser tab.
        start_kwargs = {}
        icon = window_icon()
        if icon and "icon" in inspect.signature(webview.start).parameters:
            start_kwargs["icon"] = icon

        webview.start(**start_kwargs)  # blocks until the window closes
    except Exception as exc:
        # pywebview imports fine but still cannot draw: no WebKitGTK on Linux,
        # no WebView2 runtime on Windows, or no display at all. An installed
        # library is not the same as a usable one, so the fallback has to cover
        # a failure here too, not just a missing import.
        return open_in_browser(f"{type(exc).__name__}: {exc}")

    server.should_exit = True
    return 0


if __name__ == "__main__":
    sys.exit(main())
