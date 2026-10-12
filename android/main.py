"""THANS (Android) — buildozer entry point.

The UI is Kivy (Android-friendly); the file-management engine is the EXACT
same pure-Python ``thans`` package the desktop app uses (staged into this
folder by stage_thans.sh).
"""
import os
import sys
import traceback

# make the staged core package + this app importable regardless of cwd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    try:
        from thans_android.app import ThansAndroidApp
        ThansAndroidApp().run()
    except Exception:
        # print into logcat for field debugging, then let the crash surface
        print("THANS fatal error:", file=sys.stderr)
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()
