#!/bin/bash
# Adds "Receipts" to your Linux app menu, with a proper icon.
# Run this ONCE from wherever the receipts folder permanently lives.
# If you ever move the folder, run it again.
#
# Most people should install the packaged AppImage instead — see the Releases
# page. This is for running from source.
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
chmod +x "$DIR/start.sh"

APPS="$HOME/.local/share/applications"
ICONS="$HOME/.local/share/icons/hicolor"
mkdir -p "$APPS"

# Install the icon into the icon theme rather than pointing at a file in the
# repo. Wayland does not let a window hand over a picture directly: it matches
# the window's app id to a .desktop file and takes the icon named there from
# the theme. An absolute path here works on X11 and leaves a blank space on
# Wayland — which is exactly the bug this replaces.
for size in 16 32 64 128 256 512; do
  src="$DIR/build-assets/icons/icon_${size}.png"
  if [ -f "$src" ]; then
    mkdir -p "$ICONS/${size}x${size}/apps"
    cp "$src" "$ICONS/${size}x${size}/apps/receipts.png"
  fi
done
if [ -f "$DIR/icon.svg" ]; then
  mkdir -p "$ICONS/scalable/apps"
  cp "$DIR/icon.svg" "$ICONS/scalable/apps/receipts.svg"
fi

# The filename must stay receipts.desktop: launch.py pins the window's app id
# to "receipts", and that is what the desktop matches against.
cat > "$APPS/receipts.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Receipts
Comment=Your private archive
Exec="$DIR/start.sh"
Icon=receipts
Terminal=false
Categories=Utility;Office;
StartupNotify=true
StartupWMClass=receipts
EOF

update-desktop-database "$APPS" 2>/dev/null || true
gtk-update-icon-cache -f -t "$ICONS" 2>/dev/null || true

echo ""
echo "✓ Installed. Look for Receipts in your app menu."
echo "  If the icon still looks blank, log out and back in — icon caches are stubborn."
