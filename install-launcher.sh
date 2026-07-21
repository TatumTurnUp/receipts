#!/bin/bash
# Installs "Receipts" as an app in your Linux app menu/panel.
# Run this ONCE from wherever the receipts folder permanently lives.
# If you ever move the folder, just run it again.
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
chmod +x "$DIR/start.sh"

mkdir -p "$HOME/.local/share/applications"
cat > "$HOME/.local/share/applications/receipts.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Receipts
Comment=Your personal receipts archive
Exec="$DIR/start.sh"
Icon=$DIR/icon.svg
Terminal=false
Categories=Utility;Office;
StartupNotify=true
EOF

update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true

echo ""
echo "✓ Installed. Look for 🧾 Receipts in your app menu (log out/in if it doesn't appear)."
echo "  Clicking it starts the app AND opens your browser. If it's already running,"
echo "  it just opens the browser. Pin it to your panel/dock like any other app."
