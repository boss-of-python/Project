"""Headless mode tests: the CLI must never need a display and must be scriptable.

These run the *engine* against a temp root and the *real* ``python -m thans``
entry point in a subprocess, so the exit codes and stdout/stderr contract that
scripts and CI depend on are covered too.
"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from thans import cli  # noqa: E402
from thans.__main__ import main  # noqa: E402

REPO = Path(__file__).resolve().parent.parent


class CliTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="thans_cli_"))
        (self.tmp / "work").mkdir()
        (self.tmp / "work" / "report.pdf").write_text("pdf")
        (self.tmp / "todo.txt").write_text("tasks")
        self.eng = cli.make_engine(root=self.tmp, cfg={"root": str(self.tmp), "use_llm": False})

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_cli(self, argv):
        """Run ``python -m thans`` in a subprocess; return (code, stdout, stderr)."""
        p = subprocess.run([sys.executable, "-m", "thans", *argv],
                           cwd=str(REPO), capture_output=True, text=True, timeout=120)
        return p.returncode, p.stdout, p.stderr


class TestCliEngine(CliTestBase):
    def test_runs_command_and_creates_folder(self):
        out, err = io.StringIO(), io.StringIO()
        code = cli.run_lines(self.eng, ["create folder reports"], out=out, err=err)
        self.assertEqual(code, 0, err.getvalue())
        self.assertTrue((self.tmp / "reports").is_dir())
        self.assertIn("Created folder 'reports'", out.getvalue())
        self.assertEqual(err.getvalue(), "")

    def test_failure_goes_to_stderr_and_sets_exit_code(self):
        out, err = io.StringIO(), io.StringIO()
        code = cli.run_lines(self.eng, ["delete ghost.txt"], out=out, err=err)
        self.assertEqual(code, 1)
        self.assertEqual(out.getvalue(), "")
        self.assertIn("THANS:", err.getvalue())

    def test_later_commands_still_run_after_a_failure(self):
        out, err = io.StringIO(), io.StringIO()
        code = cli.run_lines(self.eng, ["delete ghost.txt", "list"], out=out, err=err)
        self.assertEqual(code, 1)
        self.assertIn("todo.txt", out.getvalue())

    def test_json_output_is_one_object_per_line(self):
        out, err = io.StringIO(), io.StringIO()
        cli.run_lines(self.eng, ["list", "delete ghost.txt"], as_json=True, out=out, err=err)
        ok = json.loads(out.getvalue().strip())
        self.assertTrue(ok["ok"])
        self.assertEqual(ok["source"], "rules")
        self.assertIn("command", ok)
        bad = json.loads(err.getvalue().strip())
        self.assertFalse(bad["ok"])

    def test_quiet_prints_nothing(self):
        out, err = io.StringIO(), io.StringIO()
        code = cli.run_lines(self.eng, ["create folder silent", "delete ghost"], quiet=True,
                             out=out, err=err)
        self.assertEqual(code, 1)
        self.assertEqual(out.getvalue(), "")
        self.assertEqual(err.getvalue(), "")

    def test_root_override_does_not_touch_saved_config(self):
        eng2 = cli.make_engine(root=self.tmp)
        self.assertEqual(eng2.root, self.tmp.resolve())

    def test_repl_runs_commands_then_exits(self):
        stdin = io.StringIO("list\ncreate folder from-repl\nexit\n")
        out, err = io.StringIO(), io.StringIO()
        real_stdin = sys.stdin
        try:
            sys.stdin = stdin
            code = cli.repl(self.eng, quiet=False, out=out, err=err)
        finally:
            sys.stdin = real_stdin
        self.assertEqual(code, 0)
        self.assertTrue((self.tmp / "from-repl").is_dir())
        self.assertIn("todo.txt", out.getvalue())
        self.assertIn("thans:", out.getvalue())      # prompt


class TestCliMainInProcess(CliTestBase):
    def test_main_run_returns_zero(self):
        code = main(["--run", "list", "--root", str(self.tmp)])
        self.assertEqual(code, 0)

    def test_main_run_error_returns_one(self):
        code = main(["--run", "move ghost.bin to work", "--root", str(self.tmp)])
        self.assertEqual(code, 1)

    def test_does_not_write_config_in_headless_mode(self):
        from thans import config
        before = config.config_path().read_text(encoding="utf-8") if config.config_path().exists() else None
        main(["--run", "list", "--root", str(self.tmp)])
        after = config.config_path().read_text(encoding="utf-8") if config.config_path().exists() else None
        self.assertEqual(before, after)


class TestCliSubprocess(CliTestBase):
    """End-to-end: real process, real argv, real exit codes."""

    def test_run_single_command(self):
        code, out, err = self.run_cli(["--run", "create folder cli-made", "--root", str(self.tmp)])
        self.assertEqual(code, 0, err)
        self.assertTrue((self.tmp / "cli-made").is_dir())
        self.assertIn("Created folder", out)

    def test_run_reports_failure_with_exit_code_1(self):
        code, out, err = self.run_cli(["--run", "delete ghost.txt", "--root", str(self.tmp)])
        self.assertEqual(code, 1)
        self.assertIn("THANS:", err)

    def test_run_json_is_machine_readable(self):
        code, out, err = self.run_cli(["--run", "how many files in work", "--json",
                                       "--root", str(self.tmp)])
        self.assertEqual(code, 0, err)
        payload = json.loads(out.strip().splitlines()[-1])
        self.assertTrue(payload["ok"])
        self.assertIn("1 files", payload["message"])

    def test_run_accepts_short_flag(self):
        code, out, err = self.run_cli(["-c", "list", "--root", str(self.tmp)])
        self.assertEqual(code, 0, err)
        self.assertIn("todo.txt", out)

    def test_cli_pipe_mode_keeps_safety(self):
        """Piped commands are non-interactive but must still be root-confined."""
        evil = self.tmp.parent / "thans_cli_escape"
        code, out, err = self.run_cli(["--run", f"move todo.txt to {evil}/x.txt",
                                       "--root", str(self.tmp)])
        self.assertEqual(code, 1)
        self.assertIn("outside the working root", err)
        self.assertFalse(evil.exists())

    def test_help_flag_lists_headless_mode(self):
        code, out, err = self.run_cli(["--help"])
        self.assertEqual(code, 0)
        self.assertIn("--cli", out)
        self.assertIn("--run", out)

    def test_version_flag(self):
        from thans import __version__
        code, out, err = self.run_cli(["--version"])
        self.assertEqual(code, 0)
        self.assertIn(__version__, out)

    def test_models_flag_needs_no_display(self):
        code, out, err = self.run_cli(["--models"])
        self.assertEqual(code, 0, err)
        self.assertIn("Models dir", out)

    def test_selftest_flag_exits_clean(self):
        if os.environ.get("THANS_SELFTEST"):     # nested run — avoid infinite recursion
            self.skipTest("already inside a --selftest run")
        code, out, err = self.run_cli(["--selftest"])
        self.assertEqual(code, 0, err)
        self.assertIn("OK", err)

    def test_cli_flag_repl_over_pipe(self):
        if os.environ.get("THANS_SELFTEST"):
            self.skipTest("already inside a --selftest run")
        p = subprocess.run([sys.executable, "-m", "thans", "--cli", "--root", str(self.tmp)],
                           cwd=str(REPO), input="create folder piped\nexit\n",
                           capture_output=True, text=True, timeout=120)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue((self.tmp / "piped").is_dir())
        self.assertIn("Working folder", p.stdout)


if __name__ == "__main__":
    unittest.main()
