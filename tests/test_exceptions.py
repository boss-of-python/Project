"""Exception-handling regression tests: hostile inputs, dead pipes, model
malformations, read-only config dirs, and the Android layout-fallback path.

Every test proves that a previously-possible crash now degrades gracefully
(no traceback, actionable message, safe exit code).
"""
from __future__ import annotations

import importlib
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_android_ui  # noqa: E402  (Kivy harness)
import test_desktop_ui  # noqa: E402  (tkinter harness)

from thans import cli as thans_cli  # noqa: E402
from thans import config  # noqa: E402
from thans.engine import Engine, Result  # noqa: E402
from thans.tts import Speaker  # noqa: E402


def _mkroot(tmp: Path, n: int = 3) -> Path:
    for i in range(n):
        (tmp / f"f{i}.txt").write_text(f"content {i}", encoding="utf-8")
    return tmp


# --------------------------------------------------------------------------
class TestEngineRobustness(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="thans_exc_"))
        _mkroot(self.tmp)
        self.engine = Engine(self.tmp, {"root": str(self.tmp), "use_llm": False})

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_llm_missing_params_is_friendly(self):
        class _BadLLM:
            def available(self):
                return True

            def parse(self, text, items):
                return {"action": "mkdir", "params": {}}  # dropped 'path'

        self.engine.llm = _BadLLM()
        res = self.engine.run("make me a thing")
        self.assertIsInstance(res, Result)
        self.assertFalse(res.ok)
        self.assertIn("missing the file or folder name", res.message)

    def test_llm_extra_garbage_params_ignored(self):
        class _OddLLM:
            def available(self):
                return True

            def parse(self, text, items):
                return {"action": "help", "params": {"junk": object()}}

        self.engine.llm = _OddLLM()
        res = self.engine.run("anything")
        self.assertTrue(res.ok)

    def test_undo_with_incomplete_record_is_friendly(self):
        self.engine.last_record = {"action": "rename"}  # no src/dest
        res = self.engine.run("undo")
        self.assertFalse(res.ok)
        self.assertTrue(res.message.startswith("Undo failed"))
        self.assertIsNone(self.engine.last_record)

    def test_null_byte_root_degrades_to_home(self):
        self.assertEqual(config.resolve_root("a\0b"), Path.home().resolve())
        self.assertTrue(config.resolve_root("").is_dir())
        self.assertTrue(config.resolve_root("   ").is_dir())

    def test_search_with_empty_query_is_friendly(self):
        res = self.engine.run("find")
        self.assertFalse(res.ok)

    def test_open_on_missing_item_is_friendly(self):
        with mock.patch("platform.system", return_value="Linux"):
            res = self.engine.run("open nope.txt")
        self.assertFalse(res.ok)
        self.assertIn("not found", res.message)


# --------------------------------------------------------------------------
class TestBrokenPipe(unittest.TestCase):
    """`thans --run … | head -1` must exit 0 without a traceback."""

    def setUp(self):
        self._saved_flag = thans_cli._PIPE_CLOSED
        thans_cli._PIPE_CLOSED = False
        self.tmp = Path(tempfile.mkdtemp(prefix="thans_pipe_"))
        _mkroot(self.tmp)
        self.engine = Engine(self.tmp, {"root": str(self.tmp)})

    def tearDown(self):
        thans_cli._PIPE_CLOSED = self._saved_flag
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    @staticmethod
    def _closed_pipe_stream() -> "types.TextIO":
        r, w = os.pipe()
        os.close(r)  # reader is gone
        return os.fdopen(w, "w", encoding="utf-8")

    @staticmethod
    def _close_quiet(stream) -> None:
        try:
            stream.close()
        except (BrokenPipeError, OSError):
            pass  # unflushed bytes to a dead reader

    def test_emit_survives_closed_pipe(self):
        stream = self._closed_pipe_stream()
        result = Result(True, "x" * 300_000, "list", "rules")
        try:
            out_ok = thans_cli.emit(result, out=stream, err=stream)
        finally:
            self._close_quiet(stream)
        self.assertTrue(out_ok)
        self.assertTrue(thans_cli._PIPE_CLOSED)

    def test_run_lines_returns_zero_when_pipe_closes(self):
        # 3000 listings ≈ 250 KB — well past the 64 KB kernel pipe buffer,
        # so the EPIPE is guaranteed to fire.
        stream = self._closed_pipe_stream()
        try:
            code = thans_cli.run_lines(self.engine, ["list"] * 3000, out=stream, err=stream)
        finally:
            self._close_quiet(stream)
        self.assertEqual(code, 0)
        self.assertTrue(thans_cli._PIPE_CLOSED)

    def test_real_process_pipe_closed_exits_zero(self):
        # end-to-end: pipe the CLI into a reader that closes immediately
        import subprocess
        head = subprocess.Popen(["head", "-c", "1"], stdin=subprocess.PIPE,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        proc = subprocess.run(
            [sys.executable, "-m", "thans", "--cli", "--root", str(self.tmp)],
            stdout=head.stdin, stderr=subprocess.PIPE,
            input=b"list\n" * 3000 + b"exit\n", timeout=120,
        )
        head.stdin.close()
        head.wait(timeout=30)
        self.assertEqual(proc.returncode, 0)
        self.assertNotIn("Traceback", proc.stderr.decode("utf-8", "replace"))


# --------------------------------------------------------------------------
class TestTtsQueueCap(unittest.TestCase):
    def test_queue_stays_bounded_when_worker_is_dead(self):
        sp = Speaker(enabled=True)  # worker dies here (no TTS backend)
        for i in range(120):
            sp.say(f"msg {i}")
        self.assertLessEqual(sp._q.qsize(), 50)
        # newest messages must be the ones retained
        last = list(sp._q.queue)[-1]
        self.assertIn("msg 119", last)
        sp.stop()


# --------------------------------------------------------------------------
class TestConfigSaveGuard(unittest.TestCase):
    """A read-only ~/.thans must never crash the desktop UI."""

    @classmethod
    def setUpClass(cls):
        test_desktop_ui._install_fake_tk()
        if "thans.app" in sys.modules:
            importlib.reload(sys.modules["thans.app"])
        else:
            importlib.import_module("thans.app")
        cls.app_mod = sys.modules["thans.app"]

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="thans_cfg_"))
        self.cfg = {
            "root": str(self.tmp), "tts": False, "use_llm": False,
            "permanent_delete": False, "theme": "dark",
            "animations": False, "sidebar": True,
        }
        self.app = self.app_mod.ThansApp(cfg=self.cfg, text_only=True)

    def tearDown(self):
        self.app._on_close()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_safe_save_survives_read_only_config(self):
        with mock.patch.object(config, "save_config", side_effect=OSError("read-only")):
            self.app._safe_save()          # no raise
            self.app.toggle_theme()        # no raise
            self.app.toggle_sidebar()      # no raise
            self.app.toggle_theme()


# --------------------------------------------------------------------------
class TestAndroidLayoutFallback(unittest.TestCase):
    """If thans.kv fails to load, the app boots a fallback screen instead of
    crashing — and every status/add call stays safe against the bare root."""

    @classmethod
    def setUpClass(cls):
        kv = ROOT / "android" / "thans.kv"
        cls.kv_ids, _, _ = test_android_ui._extract_kv_metadata(kv)
        cls.App = test_android_ui._load_android_app_with_harness(cls.kv_ids)

    def _mkapp(self):
        tmp = Path(tempfile.mkdtemp(prefix="thans_and_fb_"))
        app = self.App(workdir=str(tmp))
        app.build()
        return tmp, app

    def test_set_status_and_add_safe_on_bare_root(self):
        import shutil
        tmp, app = self._mkapp()
        try:
            app._root = test_android_ui._FakeRoot([])  # fallback screen: no ids
            app._set_status("hello")   # must not raise
            app._add("You", "text")    # must not raise
            app._refresh_workspace()   # must not raise (all ids guarded)
            app._animate_tick(0.05)    # must not raise
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_build_recovers_when_kv_loading_raises(self):
        import shutil
        tmp, _ = self._mkapp()
        try:
            app = self.App(workdir=str(tmp))
            with mock.patch("thans_android.app.Builder") as b:
                b.load_file.side_effect = Exception("kv exploded")
                b.get_root.side_effect = Exception("kv exploded")
                root = app.build()
            self.assertIsNotNone(root)
            app._set_status("still safe")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
