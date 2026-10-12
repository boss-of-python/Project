#!/usr/bin/env bash
# Stages the shared core package into this buildozer project.
# Single source of truth: the thans/ package at the repo root.
set -euo pipefail
cd "$(dirname "$0")"
rm -rf thans
cp -r ../thans ./thans
find thans -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
echo "staged ../thans → android/thans"
