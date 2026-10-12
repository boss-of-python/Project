"""Unit tests for shared UX intelligence (ui_helpers) & animation engine (animations)."""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from thans import animations, ui_helpers  # noqa: E402


class TestAnimations(unittest.TestCase):
    def test_hex_rgb_roundtrip(self):
        self.assertEqual(animations.hex_to_rgb("#5b8af5"), (91, 138, 245))
        self.assertEqual(animations.rgb_to_hex(91, 138, 245), "#5b8af5")
        self.assertEqual(animations.hex_to_rgb("#fff"), (255, 255, 255))

    def test_hex_to_rgba(self):
        rgba = animations.hex_to_rgba("#10b981", 0.75)
        self.assertEqual(len(rgba), 4)
        self.assertAlmostEqual(rgba[3], 0.75)
        self.assertTrue(0.0 <= rgba[0] <= 1.0)

    def test_lerp_color_and_rgba(self):
        c0 = animations.lerp_color("#000000", "#ffffff", 0.0)
        cm = animations.lerp_color("#000000", "#ffffff", 0.5)
        c1 = animations.lerp_color("#000000", "#ffffff", 1.0)
        self.assertEqual(c0, "#000000")
        self.assertEqual(cm, "#7f7f7f")
        self.assertEqual(c1, "#ffffff")

        r_mid = animations.lerp_rgba((0, 0, 0, 1), (1, 1, 1, 1), 0.5)
        self.assertAlmostEqual(r_mid[0], 0.5)

    def test_easing_and_pulse(self):
        self.assertAlmostEqual(animations.ease_out_cubic(0.0), 0.0)
        self.assertAlmostEqual(animations.ease_out_cubic(1.0), 1.0)
        self.assertGreater(animations.ease_out_cubic(0.5), 0.5)

        self.assertAlmostEqual(animations.ease_in_out_sine(0.0), 0.0)
        self.assertAlmostEqual(animations.ease_in_out_sine(1.0), 1.0)

        p_peak = animations.pulse_intensity(3, 20)
        p_end = animations.pulse_intensity(20, 20)
        self.assertGreater(p_peak, 0.8)
        self.assertEqual(p_end, 0.0)

    def test_sonic_waves_and_bars(self):
        for state in ("idle", "listening", "thinking", "speaking", "success", "error"):
            res = animations.compute_sonic_waves(220, 36, phase=1.2, state=state, level=0.6)
            self.assertEqual(len(res["ribbons"]), 3)
            self.assertEqual(len(res["ribbons"][0]["coords"]), 88)
            self.assertIn("orb", res)
            bars = animations.compute_equalizer_bars(10, phase=1.2, state=state, level=0.6)
            self.assertEqual(len(bars), 10)
            self.assertTrue(all(0.1 <= b <= 1.0 for b in bars))

    def test_stream_chunks(self):
        short = animations.stream_chunks("Hello")
        self.assertEqual(short, ["Hello"])
        long_txt = "Created folder 'work/reports' and moved 12 files into organized subfolders."
        chunks = animations.stream_chunks(long_txt, max_steps=6)
        self.assertGreater(len(chunks), 1)
        self.assertEqual("".join(chunks), long_txt)


class TestUIHelpers(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="thans_ui_test_"))
        (self.tmp / "work").mkdir()
        (self.tmp / "work" / "report.pdf").write_text("pdf content")
        (self.tmp / "notes.txt").write_text("hello world")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_icons_and_sizes(self):
        self.assertEqual(ui_helpers.file_icon(self.tmp / "work"), "📁")
        self.assertEqual(ui_helpers.file_icon(Path("doc.pdf"), is_dir=False), "📕")
        self.assertEqual(ui_helpers.file_icon(Path("code.py"), is_dir=False), "🐍")
        self.assertEqual(ui_helpers.format_size(512), "512 B")
        self.assertEqual(ui_helpers.format_size(2048), "2.0 KB")

    def test_dir_snapshot_and_diff(self):
        s1 = ui_helpers.dir_snapshot(self.tmp, self.tmp)
        self.assertEqual(s1.folder_count, 1)
        self.assertEqual(s1.file_count, 1)
        self.assertFalse(s1.can_go_up)
        self.assertEqual(len(s1.changed_names), 0)

        # Create a new file and verify diff detection highlights it
        (self.tmp / "fresh.md").write_text("new markdown")
        s2 = ui_helpers.dir_snapshot(self.tmp, self.tmp, prev=s1)
        self.assertIn("fresh.md", s2.changed_names)
        fresh_entry = next(e for e in s2.entries if e.name == "fresh.md")
        self.assertTrue(fresh_entry.is_changed)

        # Filter query
        s_filt = ui_helpers.dir_snapshot(self.tmp, self.tmp, filter_query="fresh")
        self.assertEqual(len(s_filt.entries), 1)
        self.assertEqual(s_filt.entries[0].name, "fresh.md")

    def test_breadcrumbs(self):
        sub = self.tmp / "work" / "2026"
        sub.mkdir(parents=True)
        crumbs = ui_helpers.build_breadcrumbs(self.tmp, sub)
        self.assertEqual(len(crumbs), 3)
        self.assertEqual(crumbs[0][1], "~")
        self.assertEqual(crumbs[1], ("work", "work"))
        self.assertEqual(crumbs[2], ("2026", "work/2026"))

    def test_preview_intent(self):
        p_idle = ui_helpers.preview_intent("", self.tmp)
        self.assertEqual(p_idle.state, "idle")

        p_match = ui_helpers.preview_intent("create folder ideas in work", self.tmp)
        self.assertEqual(p_match.state, "matched")
        self.assertEqual(p_match.action, "mkdir")
        self.assertIn("ideas", p_match.title)

        p_part = ui_helpers.preview_intent("move", self.tmp)
        self.assertEqual(p_part.state, "partial")

        p_unk = ui_helpers.preview_intent("random gibberish phrase", self.tmp)
        self.assertEqual(p_unk.state, "unknown")

    def test_autocomplete(self):
        self.assertEqual(ui_helpers.autocomplete("cre", self.tmp), "create folder ")
        self.assertEqual(ui_helpers.autocomplete("delete no", self.tmp), "delete notes.txt")
        self.assertEqual(ui_helpers.autocomplete("go to wo", self.tmp), "go to work")


if __name__ == "__main__":
    unittest.main()
