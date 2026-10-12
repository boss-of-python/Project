#!/usr/bin/env bash
# ============================================================
#  THANS - Linux installer
#  Usage:
#     installer/linux/install.sh [staged-folder]   (default: dist/linux/THANS)
#  Installs to /opt/thans (needs sudo) or ~/.local/thans (no sudo).
#  Creates a launcher: thans  + a .desktop entry.
# ============================================================
set -euo pipefail
cd "$(dirname "$0")/../.."

SRC="${1:-dist/linux/THANS}"
[ -d "$SRC" ] || { echo "[!] staged folder not found: $SRC (run installer/linux/build_exe.sh first)"; exit 1; }
[ -f "$SRC/thans" ] || { echo "[!] $SRC/thans not found"; exit 1; }

# ship the launcher icon next to the binary (used by the .desktop entry)
ICON_SRC="$(cd "$(dirname "$0")" && pwd)/thans.png"
if [ -f "$ICON_SRC" ]; then cp "$ICON_SRC" "$SRC/thans.png"; fi

if [ "$(id -u)" = "0" ] || sudo -n true 2>/dev/null; then
  DEST=/opt/thans
  sudo mkdir -p "$DEST"
  sudo cp -r "$SRC"/. "$DEST"/
  sudo chmod +x "$DEST/thans"
  # launcher
  sudo ln -sf "$DEST/thans" /usr/local/bin/thans
  echo "Installed to $DEST  (launcher: thans)"
else
  DEST="$HOME/.local/thans"
  mkdir -p "$DEST"
  cp -r "$SRC"/. "$DEST"/
  chmod +x "$DEST/thans"
  mkdir -p "$HOME/.local/bin"
  ln -sf "$DEST/thans" "$HOME/.local/bin/thans"
  echo "Installed to $DEST (launcher: thans — ensure ~/.local/bin is on PATH)"
fi

# desktop entry
DESK="$(dirname "$DEST")/thans.desktop"
cat > /tmp/thans.desktop <<EOF
[Desktop Entry]
Type=Application
Name=THANS
Comment=Offline voice & text file assistant
Exec=$DEST/thans
Path=$DEST
Icon=$DEST/thans.png
Terminal=false
Categories=Utility;FileTools;
StartupWMClass=THANS
EOF
if [ "$(id -u)" = "0" ]; then
  sudo cp /tmp/thans.desktop /usr/share/applications/thans.desktop
else
  mkdir -p "$HOME/.local/share/applications"
  cp /tmp/thans.desktop "$HOME/.local/share/applications/thans.desktop"
fi
rm -f /tmp/thans.desktop
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true

echo
echo "✓ THANS installed. Launch with:  thans   (or from your app menu)"
echo "  First run: click the ↓ button inside the app to download the offline models,"
echo "  or run:  python scripts/download_models.py --only stt   (~40 MB, then offline)."
echo "  Headless machines:  thans --run \"list\"   (no window needed)"
