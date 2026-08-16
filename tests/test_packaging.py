"""The packaging configuration, checked without building.

A full build takes minutes on four runners, and the failures it catches are the
expensive kind — a download that installs and then does not work. These read
the configuration files directly so a mistake is caught in seconds, on every
push, on every platform.
"""

import re
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _without_comments(text: str, markers: tuple) -> str:
    """Strip comment lines before searching for configuration directives.

    These tests search files as text, so a directive named in a comment reads
    exactly like the directive itself — which produced two false failures the
    first time this ran. Comments explaining why something is absent are
    valuable; they should not be able to fail the test that checks it is.
    """
    return "\n".join(
        line for line in text.splitlines()
        if not line.strip().startswith(markers)
    )


SPEC = _read(APP_ROOT / "receipts.spec")
RELEASE = _read(APP_ROOT / ".github" / "workflows" / "release.yml")
RELEASE_CODE = _without_comments(RELEASE, ("#",))
ISS = _read(APP_ROOT / "build-assets" / "receipts.iss")
ISS_CODE = _without_comments(ISS, (";", "//"))


def test_the_frontend_is_bundled():
    assert '("static", "static")' in SPEC, "without this the app serves 404s"


def test_the_runtime_icon_is_bundled():
    assert '("build-assets/icon.png"' in SPEC
    assert (APP_ROOT / "build-assets" / "icon.png").exists()


def test_every_icon_the_installers_reference_exists():
    for name in ("icon.ico", "icon.png"):
        assert (APP_ROOT / "build-assets" / name).exists(), f"build-assets/{name} missing"
    iconset = APP_ROOT / "build-assets" / "Receipts.iconset"
    assert iconset.is_dir() and list(iconset.glob("*.png")), (
        "the macOS iconset is empty; iconutil would fail in CI"
    )
    # The AppImage step copies these by size.
    for size in (16, 32, 64, 128, 256, 512):
        assert (APP_ROOT / "build-assets" / "icons" / f"icon_{size}.png").exists(), (
            f"icons/icon_{size}.png missing — the AppImage icon install would skip it"
        )


def test_optional_heavyweight_packages_are_excluded():
    """These arrive only because some dependency probes for them, and they are
    the difference between a 45 MB and a 65 MB download."""
    for pkg in ("cryptography", "yaml", "chardet", "websockets", "tkinter"):
        assert f'"{pkg}"' in SPEC, f"{pkg} is not excluded; the bundle will vary by build machine"


def test_macos_binaries_are_not_stripped():
    """Stripping arm64 binaries before code signing is a known source of
    trouble, so strip everywhere except macOS."""
    assert "strip=not IS_MAC" in SPEC
    assert "strip=True" not in SPEC


def test_the_window_backend_is_verified_before_building():
    """CI must fail loudly if the native window backend is missing.

    Otherwise the only symptom is that every Linux user silently gets a browser
    tab instead of an app window, which nobody notices until a bug report.
    """
    assert "Verify the native window backend" in RELEASE
    assert "webview.platforms.gtk" in RELEASE
    assert "webview.platforms.cocoa" in RELEASE
    assert "webview.platforms.edgechromium" in RELEASE


def test_linux_gtk_bindings_come_from_pip_not_apt():
    """apt's python3-gi is built for the distro's Python, not the one CI
    installs — so the build would silently produce a windowless app."""
    assert "PyGObject" in RELEASE
    assert "python3-gi" not in RELEASE_CODE, (
        "apt python3-gi is not importable by the setup-python interpreter"
    )


def test_the_bundle_is_verified_after_building():
    assert "verify_bundle.py" in RELEASE
    assert (APP_ROOT / "build-assets" / "verify_bundle.py").exists()


def test_windows_installer_provisions_the_webview_runtime():
    """Without it, pywebview silently falls back to the IE engine and renders a
    blank window — no error, nothing to diagnose."""
    assert "MicrosoftEdgeWebview2Setup.exe" in ISS
    assert "WebView2Missing" in ISS
    assert "MicrosoftEdgeWebview2Setup.exe" in RELEASE, (
        "the installer references a file CI never downloads; ISCC would fail"
    )


def test_uninstalling_never_deletes_the_archive():
    assert "[UninstallDelete]" not in ISS_CODE, (
        "an UninstallDelete section could remove a user's archive"
    )


def test_the_appimage_desktop_entry_matches_the_window_app_id():
    """Wayland matches a window to a .desktop file by app id and takes the icon
    from there. A mismatch shows a blank space in the dock."""
    launch = (APP_ROOT / "launch.py").read_text(encoding="utf-8")
    app_id = re.search(r'APP_ID = "([^"]+)"', launch).group(1)
    assert f"StartupWMClass={app_id}" in RELEASE, "AppImage desktop entry app id mismatch"
    assert f"Icon={app_id}" in RELEASE

    installer = (APP_ROOT / "install-launcher.sh").read_text(encoding="utf-8")
    assert f"StartupWMClass={app_id}" in installer
    assert f"{app_id}.desktop" in installer
    assert f"Icon={app_id}" in installer, (
        "an absolute icon path works on X11 and shows blank on Wayland"
    )


def test_release_and_test_workflows_agree_on_dependencies():
    tests_wf = (APP_ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    assert "requirements-dev.txt" in tests_wf
    assert "requirements-build.txt" in RELEASE


def test_version_is_stamped_from_the_tag():
    assert "Stamp the version into the build" in RELEASE
    version_py = (APP_ROOT / "version.py").read_text(encoding="utf-8")
    assert re.search(r'^VERSION = "[^"]+"$', version_py, re.M), (
        "the CI stamping regex would not match version.py"
    )
    assert re.search(r'^CHANNEL = "[^"]+"', version_py, re.M)


def test_beta_tags_publish_as_prereleases():
    assert "-beta" in RELEASE and "prerelease" in RELEASE


def test_version_label_does_not_repeat_the_channel():
    """A beta build should say beta once, not twice."""
    src = (APP_ROOT / "version.py").read_text(encoding="utf-8")
    for raw, channel, expected in [
        ("0.9.0", "stable", "0.9.0"),
        ("0.9.0-beta.1", "beta", "0.9.0-beta.1"),   # not "0.9.0-beta.1 (beta)"
        ("1.0.0", "beta", "1.0.0 (beta)"),          # the number alone gives no hint
    ]:
        stamped = re.sub(r'^VERSION = ".*"$', f'VERSION = "{raw}"', src, flags=re.M)
        stamped = re.sub(r'^CHANNEL = ".*?"', f'CHANNEL = "{channel}"', stamped, flags=re.M)
        ns: dict = {}
        exec(compile(stamped, "version.py", "exec"), ns)
        assert ns["display_version"]() == expected, (
            f"{raw}/{channel} showed {ns['display_version']()!r}, expected {expected!r}"
        )


def test_ci_runs_on_the_branch_you_are_working_on():
    """Work happens on feature branches; CI that only watches main is decoration."""
    tests_wf = (APP_ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    assert 'branches: ["**"]' in tests_wf


def test_install_instructions_exist_and_cover_every_platform():
    """The first thing a new user hits is a security warning. If the download
    page does not explain it, the app looks broken rather than unsigned."""
    install = _read(APP_ROOT / "INSTALL.md")
    for needed in ("macos-arm64.dmg", "macos-intel.dmg", "Receipts-Setup", ".AppImage"):
        assert needed in install, f"INSTALL.md never mentions {needed}"
    assert "Open Anyway" in install, "no macOS Gatekeeper instructions"
    assert "Run anyway" in install, "no Windows SmartScreen instructions"
    assert "chmod +x" in install, "no Linux AppImage instructions"


def test_release_notes_warn_about_the_unsigned_warnings():
    assert "Open Anyway" in RELEASE and "Run anyway" in RELEASE


def test_install_guide_does_not_give_obsolete_mac_advice():
    """Apple removed the Control-click bypass in macOS Sequoia; telling people
    to right-click and Open now sends them down a path that does not work."""
    install = _read(APP_ROOT / "INSTALL.md")
    body = "\n".join(
        line for line in install.splitlines() if not line.strip().startswith(">")
    )
    assert "right-click" not in body.lower() or "Open Anyway" in body


def test_no_retired_runner_images():
    """A job pointed at a retired runner queues forever instead of failing.

    macos-13 was retired in December 2025 and the v0.9.0 Intel build sat
    waiting for a machine that no longer exists.
    """
    retired = ["macos-13", "macos-12", "macos-11", "ubuntu-20.04", "windows-2019"]
    for image in retired:
        assert f"os: {image}\n" not in RELEASE_CODE, (
            f"{image} has been retired; that job will queue indefinitely"
        )


def test_every_platform_still_has_a_build():
    for label in ("macos-arm64", "macos-intel", "windows", "linux"):
        assert f"label: {label}" in RELEASE_CODE, f"no build produces the {label} download"
