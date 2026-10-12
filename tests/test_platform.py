"""Cross-platform plumbing tests (Windows / Linux / macOS / Android).

Covers:
  * thans.platforms.find_downloader  — model-downloader script + interpreter
    discovery (incl. the PyInstaller-frozen EXE case)
  * thans.platforms.resolve_workdir  — writable working directory (Android)
  * thans.actions.opener             — per-OS "open" dispatch (startfile /
    open / xdg-open / explorer /select)
  * scripts/build_installer.build_args — PyInstaller argv assembly (flags must
    come AFTER the "PyInstaller" token or CPython aborts)
  * version consistency between thans/__init__ and thans/config
"""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from thans import __version__, config, platforms  # noqa: E402
from thans.actions import opener  # noqa: E402


def _load_build_installer():
    path = ROOT / "scripts" / "build_installer.py"
    spec = importlib.util.spec_from_file_location("thans_build_installer", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------------------
class TestVersionConsistency(unittest.TestCase):
    def test_config_version_matches_package(self):
        self.assertEqual(config.APP_VERSION, __version__)


# --------------------------------------------------------------------------
class TestFindDownloader(unittest.TestCase):
    def test_unfrozen_returns_current_interpreter(self):
        script, py = platforms.find_downloader()
        self.assertTrue(script.is_file())
        self.assertEqual(script.name, "download_models.py")
        self.assertEqual(py, sys.executable)

    def test_missing_script_raises_file_not_found(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(FileNotFoundError):
                platforms.find_downloader(root=Path(td))

    def test_env_override_wins(self):
        with tempfile.TemporaryDirectory() as td:
            s = Path(td) / "custom_downloader.py"
            s.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
            old = os.environ.get("THANS_DOWNLOAD_SCRIPT")
            os.environ["THANS_DOWNLOAD_SCRIPT"] = str(s)
            try:
                script, _ = platforms.find_downloader()
                self.assertEqual(script, s)
            finally:
                if old is None:
                    os.environ.pop("THANS_DOWNLOAD_SCRIPT", None)
                else:
                    os.environ["THANS_DOWNLOAD_SCRIPT"] = old

    def test_frozen_uses_python_from_path(self):
        # root= simulates "the scripts folder sits next to the installed exe"
        with mock.patch.object(sys, "frozen", True, create=True), \
             mock.patch("shutil.which",
                        side_effect=lambda n: "/fake/python3" if n == "python3" else None):
            script, py = platforms.find_downloader(root=ROOT)
            self.assertEqual(py, "/fake/python3")
            self.assertTrue(script.is_file())

    def test_frozen_without_any_python_raises(self):
        with mock.patch.object(sys, "frozen", True, create=True), \
             mock.patch("shutil.which", return_value=None):
            with self.assertRaises(RuntimeError) as ctx:
                platforms.find_downloader(root=ROOT)
            self.assertIn("Python", str(ctx.exception))


# --------------------------------------------------------------------------
class TestResolveWorkdir(unittest.TestCase):
    def test_preferred_writable_dir_is_used(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(platforms.resolve_workdir(td), td)

    def test_unwritable_preferred_falls_back_to_writable(self):
        with tempfile.TemporaryDirectory() as td:
            blocker = Path(td) / "a-file"
            blocker.write_text("x", encoding="utf-8")
            # a directory cannot be created *inside* a file → guaranteed failure
            bad = str(blocker / "impossible")
            result = Path(platforms.resolve_workdir(bad))
            self.assertTrue(result.is_dir())
            probe = result / ".thans_write_test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()

    def test_default_returns_something_writable(self):
        result = Path(platforms.resolve_workdir())
        self.assertTrue(result.is_dir())


# --------------------------------------------------------------------------
class TestOpenDispatch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "doc.txt").write_text("hi", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def _open(self, system: str, reveal: bool = False):
        with mock.patch.object(opener.platform, "system", return_value=system):
            return opener.open_item(self.root, self.root, "doc.txt", reveal=reveal)

    def test_linux_uses_xdg_open(self):
        with mock.patch.object(opener.subprocess, "Popen") as popen:
            ok, _, _ = self._open("Linux")
            self.assertTrue(ok)
            self.assertEqual(popen.call_args[0][0][0], "xdg-open")

    def test_linux_reveal_opens_parent(self):
        with mock.patch.object(opener.subprocess, "Popen") as popen:
            ok, _, _ = self._open("Linux", reveal=True)
            self.assertTrue(ok)
            self.assertEqual(Path(popen.call_args[0][0][1]), self.root)

    def test_darwin_uses_open(self):
        with mock.patch.object(opener.subprocess, "Popen") as popen:
            ok, _, _ = self._open("Darwin")
            self.assertTrue(ok)
            self.assertEqual(popen.call_args[0][0][0], "open")

    def test_windows_uses_startfile(self):
        with mock.patch.object(opener.os, "startfile", create=True) as sf:
            ok, _, _ = self._open("Windows")
            self.assertTrue(ok)
            sf.assert_called_once()

    def test_windows_reveal_uses_explorer_select(self):
        with mock.patch.object(opener.subprocess, "Popen") as popen:
            ok, _, _ = self._open("Windows", reveal=True)
            self.assertTrue(ok)
            cmd = popen.call_args[0][0]
            self.assertEqual(cmd[0], "explorer")
            self.assertIn("doc.txt", cmd[1])

    def test_missing_item_raises_not_found(self):
        with mock.patch.object(opener.platform, "system", return_value="Linux"):
            with self.assertRaises(ValueError):
                opener.open_item(self.root, self.root, "nope.txt")


# --------------------------------------------------------------------------
class TestBuildInstallerArgs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bi = _load_build_installer()

    def test_positional_prefix_is_untouched(self):
        # the first three tokens must stay `python -m PyInstaller` — inserting
        # --icon/--onedir before "-m" makes CPython abort ("unknown option")
        for onedir in (False, True):
            args = self.bi.build_args(onedir=onedir)
            self.assertEqual(args[1], "-m")
            self.assertEqual(args[2], "PyInstaller")

    def test_onedir_flag_lands_inside_pyinstaller_argv(self):
        args = self.bi.build_args(onedir=True)
        pi = args.index("PyInstaller")
        self.assertIn("--onedir", args[pi + 1:])
        self.assertNotIn("--onedir", args[:pi])

    def test_entry_point_present(self):
        args = self.bi.build_args()
        self.assertTrue(any(a.endswith(os.path.join("thans", "__main__.py")) for a in args))

    def test_lazy_native_packages_collected_only_when_present(self):
        joined = " ".join(self.bi.build_args())
        for pkg in ("vosk", "sounddevice"):
            self.assertEqual(
                f"--collect-all {pkg}" in joined,
                platforms.native_package_available(pkg),
                msg=f"--collect-all {pkg} should be present iff the package is importable",
            )

    def test_pyttsx3_drivers_collected_when_pyttsx3_present(self):
        joined = " ".join(self.bi.build_args())
        if platforms.native_package_available("pyttsx3"):
            self.assertIn("pyttsx3.drivers.sapi5", joined)
            self.assertIn("pyttsx3.drivers.espeak", joined)


if __name__ == "__main__":
    unittest.main()
