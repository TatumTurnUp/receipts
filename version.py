"""The one place the version number lives.

Everything else reads it from here: the window title, the About line, the
installer filenames, the release feed. Bump this, tag the commit, and the
build pipeline does the rest.

    0.9.0          an early public release  → tag v0.9.0
    1.2.0          a finished release       → tag v1.2.0
    0.9.0-beta.1   flagged as a pre-release → tag v0.9.0-beta.1

CHANNEL is what a build says about itself. Beta builds carry "beta" so the app
can show it in the title bar and, later, check the beta update feed.
"""

VERSION = "1.0.0"
CHANNEL = "stable"  # "stable" | "beta"

APP_NAME = "Receipts"
BUNDLE_ID = "com.tatumturnup.receipts"


def display_version() -> str:
    """What the title bar shows.

    A beta build should say so, but "0.9.0-beta.1 (beta)" says it twice — so
    the suffix is only added when the version number does not already carry it.
    """
    if CHANNEL == "stable" or CHANNEL in VERSION:
        return VERSION
    return f"{VERSION} ({CHANNEL})"
