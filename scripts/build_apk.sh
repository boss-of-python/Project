#!/usr/bin/env bash
# Build the THANS Android debug APK locally (Linux).
# Requires: openjdk-17, buildozer, cython 0.29.x
# First run downloads the Android SDK/NDK (~1 GB).
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m thans --selftest
cd android
chmod +x stage_thans.sh
./stage_thans.sh
buildozer android debug
echo
echo "APK:"
ls -lh bin/*.apk
