"""Action & engine tests: run against a temp working root (no display needed)."""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from thans import actions  # noqa: E402
from thans.engine import Engine  # noqa: E402


class TestFolderQualifiedCommands(unittest.TestCase):
    """`find x in y`, `how many files in .` and the count aliases end to end."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "docs").mkdir()
        (self.root / "docs" / "invoice-2026.pdf").write_text("x")
        (self.root / "other").mkdir()
        (self.root / "other" / "invoice-old.pdf").write_text("x")
        (self.root / "note.txt").write_text("hi")
        self.engine = Engine(self.root, {})

    def tearDown(self):
        self.tmp.cleanup()

    def test_search_inside_a_named_folder(self):
        res = self.engine.run("find invoice in docs")
        self.assertTrue(res.ok, res.message)
        self.assertIn("invoice-2026.pdf", res.message)
        self.assertNotIn("invoice-old.pdf", res.message)

    def test_search_here_stays_in_the_current_folder(self):
        self.engine.run("go to other")
        res = self.engine.run("find invoice in .")
        self.assertTrue(res.ok, res.message)
        self.assertIn("invoice-old.pdf", res.message)

    def test_count_aliases(self):
        for phrase in ("how many files in .", "count files in docs",
                       "number of items in docs", "how many files"):
            res = self.engine.run(phrase)
            self.assertTrue(res.ok, f"{phrase} → {res.message}")
            self.assertIn("files", res.message)

    def test_count_of_an_empty_folder_says_zero(self):
        (self.root / "empty").mkdir()
        res = self.engine.run("how many files in empty")
        self.assertTrue(res.ok)
        self.assertTrue("0 files" in res.message or "0 folders" in res.message, res.message)


class EngineTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="thans_test_"))
        self.cfg = {"root": str(self.tmp), "tts": False, "use_llm": False, "permanent_delete": False}
        self.eng = Engine(self.tmp, self.cfg)
        # seed: work/ folder with a few files
        (self.tmp / "work").mkdir()
        (self.tmp / "work" / "report.pdf").write_text("pdf")
        (self.tmp / "work" / "notes.txt").write_text("n")
        (self.tmp / "todo.txt").write_text("tasks")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def say(self, text):
        return self.eng.run(text)


class TestEngineFiles(EngineTestBase):
    def test_create_folder(self):
        r = self.say("create folder work/reports")
        self.assertTrue(r.ok, r.message)
        self.assertTrue((self.tmp / "work" / "reports").is_dir())

    def test_create_folder_in(self):
        r = self.say("make a folder called ideas in work")
        self.assertTrue(r.ok, r.message)
        self.assertTrue((self.tmp / "work" / "ideas").is_dir())

    def test_create_file_with_content(self):
        r = self.say("create file memo.txt with meeting at 3pm in work")
        self.assertTrue(r.ok, r.message)
        self.assertEqual((self.tmp / "work" / "memo.txt").read_text(), "meeting at 3pm\n")

    def test_list(self):
        r = self.say("list work")
        self.assertTrue(r.ok, r.message)
        self.assertIn("report.pdf", r.message)
        self.assertIn("2 files", r.message)

    def test_count(self):
        r = self.say("how many files are in work")
        self.assertTrue(r.ok, r.message)
        self.assertIn("2 files", r.message)

    def test_rename(self):
        # notes.txt lives in work/ — deep unique match should still find it
        r = self.say("rename notes.txt to journal.txt")
        self.assertTrue(r.ok, r.message)
        self.assertTrue((self.tmp / "work" / "journal.txt").is_file())
        self.assertFalse((self.tmp / "work" / "notes.txt").exists())

    def test_rename_in_subdir_via_cd(self):
        self.say("go to work")
        r = self.say("rename notes to journal.txt")  # fuzzy prefix match
        self.assertTrue(r.ok, r.message)
        self.assertTrue((self.tmp / "work" / "journal.txt").is_file())

    def test_move_into_folder(self):
        r = self.say("move todo.txt to work")
        self.assertTrue(r.ok, r.message)
        self.assertTrue((self.tmp / "work" / "todo.txt").is_file())
        self.assertFalse((self.tmp / "todo.txt").exists())

    def test_move_creates_dir_with_slash(self):
        r = self.say("move todo.txt to archive/")
        self.assertTrue(r.ok, r.message)
        self.assertTrue((self.tmp / "archive" / "todo.txt").is_file())

    def test_copy(self):
        r = self.say("copy report.pdf to work")  # already there → dest exists error
        self.assertFalse(r.ok)
        r = self.say("copy todo.txt to work")
        self.assertTrue(r.ok, r.message)
        self.assertTrue((self.tmp / "todo.txt").is_file())
        self.assertTrue((self.tmp / "work" / "todo.txt").is_file())

    def test_delete_to_trash_and_undo(self):
        r = self.say("delete todo.txt")
        self.assertTrue(r.ok, r.message)
        self.assertFalse((self.tmp / "todo.txt").exists())
        trash = list((self.tmp / ".thans_trash").iterdir())
        self.assertEqual(len(trash), 1)
        r = self.say("undo")
        self.assertTrue(r.ok, r.message)
        self.assertTrue((self.tmp / "todo.txt").is_file())

    def test_delete_permanent(self):
        r = self.say("delete todo.txt permanently")
        self.assertTrue(r.ok, r.message)
        self.assertFalse((self.tmp / "todo.txt").exists())
        self.assertFalse((self.tmp / ".thans_trash").exists())

    def test_delete_folder(self):
        r = self.say("delete work")
        self.assertTrue(r.ok, r.message)
        self.assertFalse((self.tmp / "work").exists())
        self.assertTrue((self.tmp / ".thans_trash").exists())

    def test_undo_move(self):
        r = self.say("move todo.txt to work")
        self.assertTrue(r.ok)
        r = self.say("undo")
        self.assertTrue(r.ok, r.message)
        self.assertTrue((self.tmp / "todo.txt").is_file())
        self.assertFalse((self.tmp / "work" / "todo.txt").exists())

    def test_undo_create_folder(self):
        self.say("create folder scratch")
        r = self.say("undo")
        self.assertTrue(r.ok, r.message)
        self.assertFalse((self.tmp / "scratch").exists())


class TestEngineSearchOrganize(EngineTestBase):
    def test_search_name(self):
        r = self.say("find report")
        self.assertTrue(r.ok, r.message)
        self.assertIn("report.pdf", r.message)

    def test_search_ext(self):
        r = self.say("search for txt files")
        self.assertTrue(r.ok, r.message)
        self.assertIn("notes.txt", r.message)
        self.assertNotIn("report.pdf", r.message)

    def test_search_star(self):
        (self.tmp / "debug.log").write_text("x")
        r = self.say("find *.log")
        self.assertTrue(r.ok, r.message)
        self.assertIn("debug.log", r.message)

    def test_organize_by_ext(self):
        w = self.tmp / "work"
        (w / "a.txt").write_text("a")
        (w / "b.txt").write_text("b")
        (w / "c.md").write_text("c")
        (w / "noext").write_text("n")
        r = self.say("organize work")
        self.assertTrue(r.ok, r.message)
        self.assertTrue((w / "txt" / "a.txt").is_file())
        self.assertTrue((w / "md" / "c.md").is_file())
        self.assertTrue((w / "other" / "noext").is_file())
        # Undo organize should restore files and remove empty category dirs
        u = self.say("undo")
        self.assertTrue(u.ok, u.message)
        self.assertTrue((w / "a.txt").is_file())
        self.assertTrue((w / "c.md").is_file())
        self.assertFalse((w / "txt").exists())

    def test_cd_up(self):
        (self.tmp / "work" / "sub").mkdir()
        self.say("go to work/sub")
        self.assertEqual(self.eng.current, (self.tmp / "work" / "sub").resolve())
        r = self.say("go back")
        self.assertTrue(r.ok, r.message)
        self.assertEqual(self.eng.current, (self.tmp / "work").resolve())
        r2 = self.say("up")
        self.assertTrue(r2.ok, r2.message)
        self.assertEqual(self.eng.current, self.eng.root)
        # Going up at root stays safely at root
        r3 = self.say("go up")
        self.assertTrue(r3.ok, r3.message)
        self.assertEqual(self.eng.current, self.eng.root)

    def test_organize_by_date(self):
        w = self.tmp / "work"
        r = self.say("organize work by date")
        self.assertTrue(r.ok, r.message)
        subs = [p for p in w.iterdir() if p.is_dir()]
        self.assertTrue(subs)

    def test_cd_and_list(self):
        r = self.say("go to work")
        self.assertTrue(r.ok, r.message)
        r = self.say("list")
        self.assertTrue(r.ok, r.message)
        self.assertIn("report.pdf", r.message)

    def test_cd_home(self):
        self.say("go to work")
        r = self.say("cd")
        self.assertTrue(r.ok, r.message)
        self.assertEqual(self.eng.current, self.eng.root)

    def test_not_found_lists_neighbours(self):
        r = self.say("delete nonexistent.txt")
        self.assertFalse(r.ok)
        self.assertIn("not found", r.message.lower())

    def test_ambiguous_or_helpful_error(self):
        r = self.say("move ghost.bin to work")
        self.assertFalse(r.ok)


class TestSafety(EngineTestBase):
    def test_escape_blocked(self):
        r = self.say(f"move todo.txt to {self.tmp.parent}/evil.txt")
        self.assertFalse(r.ok)
        self.assertIn("outside the working root", r.message)

    def test_dotdot_blocked(self):
        r = self.say("move todo.txt to ../../etc/passwd")
        self.assertFalse(r.ok)
        self.assertIn("outside the working root", r.message)

    def test_absolute_outside_blocked(self):
        r = self.say("create folder /tmp/thans_evil_dir")
        self.assertFalse(r.ok)
        self.assertFalse(Path("/tmp/thans_evil_dir").exists())

    def test_trash_hidden_from_search(self):
        self.say("delete todo.txt")
        r = self.say("find todo")
        self.assertTrue(r.ok, r.message)
        self.assertIn("Nothing", r.message)

    def test_parent_path_cannot_delete_outside_root(self):
        secret = self.tmp.parent / "thans_secret_outside.txt"
        secret.write_text("do-not-touch")
        try:
            r = self.say("delete ../thans_secret_outside.txt")
            self.assertFalse(r.ok, r.message)
            self.assertIn("outside the working root", r.message)
            self.assertTrue(secret.exists())
            self.assertEqual(secret.read_text(), "do-not-touch")
        finally:
            secret.unlink(missing_ok=True)

    def test_absolute_delete_outside_is_blocked(self):
        r = self.say("delete /etc/passwd")
        self.assertFalse(r.ok)
        self.assertIn("outside the working root", r.message)

    def test_open_absolute_outside_is_blocked(self):
        r = self.say("open /etc/passwd")
        self.assertFalse(r.ok)
        self.assertIn("outside the working root", r.message)

    def test_symlink_pointing_outside_is_blocked(self):
        outside = self.tmp.parent / "thans_symlink_target.txt"
        outside.write_text("OUT")
        link = self.tmp / "escape.txt"
        try:
            link.symlink_to(outside)
        except OSError:
            self.skipTest("symlinks not supported here")
        try:
            r = self.say("delete escape.txt")
            self.assertFalse(r.ok, r.message)
            self.assertIn("outside the working root", r.message)
            self.assertTrue(outside.exists())
            self.assertEqual(outside.read_text(), "OUT")
        finally:
            outside.unlink(missing_ok=True)

    def test_relative_inside_root_still_works(self):
        r = self.say("delete work/notes.txt")
        self.assertTrue(r.ok, r.message)
        self.assertFalse((self.tmp / "work" / "notes.txt").exists())


class TestParserFallback(EngineTestBase):
    def test_unknown_phrase(self):
        r = self.say("tell me a joke")
        self.assertFalse(r.ok)
        self.assertIn("didn't catch", r.message)

    def test_command_description(self):
        r = self.say("create folder work/reports")
        self.assertTrue(r.command.startswith("mkdir"))
        self.assertEqual(r.source, "rules")


class TestUniqueDestAndModels(unittest.TestCase):
    def test_unique_dest_keeps_extension_and_starts_at_one(self):
        tmp = Path(tempfile.mkdtemp(prefix="thans_unique_"))
        try:
            (tmp / "report.pdf").write_text("1")
            d1 = actions.unique_dest(tmp, "report.pdf")
            self.assertEqual(d1.name, "report (1).pdf")
            d1.write_text("2")
            d2 = actions.unique_dest(tmp, "report.pdf")
            self.assertEqual(d2.name, "report (2).pdf")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_vosk_ready_accepts_official_layout_not_just_model_bin(self):
        from thans.model_manager import vosk_model_ready
        tmp = Path(tempfile.mkdtemp(prefix="thans_vosk_"))
        try:
            fake = tmp / "vosk-model-small-en-us-0.15"
            fake.mkdir()
            self.assertFalse(vosk_model_ready(fake))
            (fake / "am").mkdir()
            (fake / "am" / "final.mdl").write_bytes(b"x")
            self.assertTrue(vosk_model_ready(fake))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
