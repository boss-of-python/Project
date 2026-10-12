"""Action & engine tests: run against a temp working root (no display needed)."""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from thans import actions  # noqa: E402
from thans.engine import Engine  # noqa: E402


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


class TestParserFallback(EngineTestBase):
    def test_unknown_phrase(self):
        r = self.say("tell me a joke")
        self.assertFalse(r.ok)
        self.assertIn("didn't catch", r.message)

    def test_command_description(self):
        r = self.say("create folder work/reports")
        self.assertTrue(r.command.startswith("mkdir"))
        self.assertEqual(r.source, "rules")


if __name__ == "__main__":
    unittest.main()
