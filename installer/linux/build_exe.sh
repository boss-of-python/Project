#!/usr/bin/env bash
# ============================================================
#  THANS - Linux build: PyInstaller onefile + staged folder
# ============================================================
set -euo pipefail
cd "$(dirname "$0")/../.."

PY=python3
command -v "$PY" >/dev/null || { echo "[!] python3 not found"; exit 1; }

echo "=== [1/3] Installing dependencies ==="
"$PY" -m pip install --upgrade pip
"$PY" -m pip install -r requirements.txt
"$PY" -m pip install -r requirements-llm.txt || echo "[!] LLM dependency failed (optional)"
"$PY" -m pip install -r requirements-build.txt

echo "=== [2/3] Self-test ==="
"$PY" -m thans --selftest || echo "[!] tests failed - continuing anyway"

echo "=== [3/3] Building ==="
"$PY" scripts/build_installer.py

# Stage a folder the installer can copy: THANS + models/
STAGE=dist/linux/THANS
rm -rf "$STAGE"
mkdir -p "$STAGE"
cp dist/THANS "$STAGE/thans"
chmod +x "$STAGE/thans"
# one-time model downloader (the app's "⬇ Models" button needs it at runtime)
cp -r scripts "$STAGE/scripts"
if [ -d models ] && [ -n "$(ls -A models 2>/dev/null)" ]; then
  cp -r models "$STAGE/models"
fi
echo
echo "Done. Staged app: $STAGE"
echo "Install with:  installer/linux/install.sh $STAGE"
