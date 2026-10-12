"""Rule parser tests: phrase → expected action/params."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from thans.parser_rules import parse  # noqa: E402


def expect(phrase, action, **params):
    cmd = parse(phrase)
    assert cmd is not None, f"no match for: {phrase!r}"
    assert cmd["action"] == action, f"{phrase!r} → {cmd['action']} (wanted {action})"
    for k, v in params.items():
        got = cmd["params"].get(k)
        assert got == v, f"{phrase!r} params[{k}] = {got!r} (wanted {v!r})"
    return cmd


class TestNaturalPhrasing(unittest.TestCase):
    """Phrasings people actually type — "here", ".", "count …", "find … in …"."""

    def test_here_words_mean_the_current_folder(self):
        for phrase in ("how many files in .", "how many files in here",
                       "number of folders here", "list this folder",
                       "what's in here", "list files in ."):
            cmd = parse(phrase)
            self.assertIsNotNone(cmd, phrase)
            self.assertEqual(cmd["action"], "list", phrase)
            self.assertFalse(cmd["params"].get("path"), phrase)

    def test_count_phrasings(self):
        for phrase in ("how many files", "count files", "number of items",
                       "count of files", "how many folders in docs"):
            cmd = parse(phrase)
            self.assertIsNotNone(cmd, phrase)
            self.assertEqual(cmd["action"], "list")
            self.assertTrue(cmd["params"].get("count"), phrase)
        self.assertEqual(parse("count files in docs")["params"]["path"], "docs")
        self.assertEqual(parse("how many items are in work")["params"]["path"], "work")

    def test_search_in_a_folder(self):
        cmd = parse("find invoice in docs")
        self.assertEqual(cmd, {"action": "search", "params": {"query": "invoice", "path": "docs"}})
        cmd = parse("search for pdf files in downloads")
        self.assertEqual(cmd["params"], {"query": "pdf files", "path": "downloads"})
        cmd = parse("find *.log in .")
        self.assertEqual(cmd["params"], {"query": "*.log", "path": ""})
        # a plain search still works
        self.assertEqual(parse("find invoice")["params"], {"query": "invoice"})

    def test_dots_in_file_names_survive_normalization(self):
        self.assertEqual(parse("delete report.pdf")["params"]["path"], "report.pdf")
        self.assertEqual(parse("open notes (1).txt")["params"]["path"], "notes (1).txt")


class TestParser(unittest.TestCase):
    def test_help(self):
        expect("help", "help")
        expect("Hey THANS, what can you do", "help")
        expect("show help", "help")
        expect("list commands", "help")

    def test_list(self):
        expect("list", "list", path=None)
        expect("ls", "list", path=None)
        expect("show files", "list", path=None)
        expect("show me the files", "list", path=None)
        expect("list reports", "list", path="reports")
        expect("show files in downloads", "list", path="downloads")
        expect("list in work", "list", path="work")
        expect("what's in work", "list", path="work")
        expect("how many files are in docs", "list", path="docs", count=True)
        expect("list all folders in work", "list", path="work")

    def test_mkdir(self):
        expect("create folder work/reports", "mkdir", path="work/reports")
        expect("make a folder called ideas in notes", "mkdir", path="ideas", in_dir="notes")
        expect("new directory project x", "mkdir", path="project x")
        expect("create a folder named archive", "mkdir", path="archive")
        expect("please create folder temp", "mkdir", path="temp")

    def test_touch(self):
        expect("create file todo.txt", "touch", path="todo.txt", content=None)
        expect("create a file called notes.txt in work", "touch", path="notes.txt", in_dir="work")
        expect("create file memo.txt with meeting at 3pm", "touch", path="memo.txt", content="meeting at 3pm")
        expect("create file memo.txt with meeting at 3pm in notes",
               "touch", path="memo.txt", in_dir="notes", content="meeting at 3pm")
        expect("make a file named readme.md", "touch", path="readme.md")

    def test_rename(self):
        expect("rename old.txt to new.txt", "rename", src="old.txt", dest="new.txt")
        expect("rename file notes.txt to journal.txt", "rename", src="notes.txt", dest="journal.txt")
        expect("change the name of report to final report", "rename", src="report", dest="final report")

    def test_move(self):
        expect("move report.pdf to work", "move", src="report.pdf", dest="work")
        expect("move a.txt into docs", "move", src="a.txt", dest="docs")
        expect("put budget.xlsx in finance", "move", src="budget.xlsx", dest="finance")
        expect("shift the old logs to archive", "move", src="old logs", dest="archive")

    def test_copy(self):
        expect("copy report.pdf to backups", "copy", src="report.pdf", dest="backups")
        expect("duplicate data.csv to temp", "copy", src="data.csv", dest="temp")

    def test_delete(self):
        expect("delete old.txt", "delete", path="old.txt", permanent=False)
        expect("remove the file report.txt", "delete", path="report.txt", permanent=False)
        expect("get rid of temp folder permanently", "delete", path="temp", permanent=True)
        expect("trash junk for good", "delete", path="junk", permanent=True)

    def test_search(self):
        expect("find invoice", "search", query="invoice")
        expect("search for pdf files", "search", query="pdf files")
        expect("find *.log", "search", query="*.log")

    def test_open_reveal(self):
        expect("open notes", "open", path="notes")
        expect("open folder work", "open", path="work")
        expect("open the file report.pdf", "open", path="report.pdf")
        expect("show in folder report.pdf", "open", path="report.pdf", reveal=True)
        expect("reveal memo.txt", "open", path="memo.txt", reveal=True)

    def test_organize(self):
        expect("organize downloads", "organize", path="downloads", mode="extension")
        expect("organize downloads by date", "organize", path="downloads", mode="date")
        expect("organize files by date", "organize", path=None, mode="date")
        expect("organize files in downloads by type", "organize", path="downloads", mode="extension")
        expect("organize", "organize", path=None, mode="extension")
        # "by <mode>" alone must NOT be swallowed as a folder name
        expect("organize by type", "organize", path=None, mode="extension")
        expect("organize by date", "organize", path=None, mode="date")
        expect("organize by extension", "organize", path=None, mode="extension")
        expect("organize using mtime", "organize", path=None, mode="date")
        expect("organize the downloads by date", "organize", path="downloads", mode="date")

    def test_cd(self):
        expect("go to work", "cd", path="work")
        expect("cd work/reports", "cd", path="work/reports")
        expect("cd", "cd", path="~")
        expect("go home", "cd", path="~")
        expect("change folder to work", "cd", path="work")

    def test_undo(self):
        expect("undo", "undo")
        expect("undo last action", "undo")

    def test_fillers(self):
        expect("Hey THANS, please create folder archive in work", "mkdir", path="archive", in_dir="work")
        expect("THANS, can you move a.txt to b", "move", src="a.txt", dest="b")

    def test_unmatched_returns_none(self):
        self.assertIsNone(parse(""))
        self.assertIsNone(parse("   "))
        self.assertIsNone(parse("tell me a joke"))
        self.assertIsNone(parse("what is the weather"))


if __name__ == "__main__":
    unittest.main()
