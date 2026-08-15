"""The one place the version number lives.

Everything else reads it from here: the window title, the About line, the
installer filenames, the release feed. Bump this, tag the commit, and the
build pipeline does the rest.

    1.2.0          a normal release       → tag v1.2.0
    1.3.0-beta.1   a beta for testers     → tag v1.3.0-beta.1

CHANNEL is what a build says about itself. Beta builds carry "beta" so the app
can show it in the title bar and, later, check the beta update feed.
"""

VERSION = "1.0.0"
CHANNEL = "stable"  # "stable" | "beta"

APP_NAME = "Receipts"
BUNDLE_ID = "com.tatumturnup.receipts"


def display_version() -> str:
    return VERSION if CHANNEL == "stable" else f"{VERSION} ({CHANNEL})"
