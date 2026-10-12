"""Pure UI logic tests — no display, no tkinter: tween engine, typewriter,
colour maths and as-you-type suggestions."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from thans.ui import logic  # noqa: E402
from thans.ui import theme as T  # noqa: E402


class TestColourMaths(unittest.TestCase):
    def test_hex_roundtrip(self):
        self.assertEqual(T.hex2rgb("#5b8cff"), (91, 140, 255))
        self.assertEqual(T.rgb2hex((91, 140, 255)), "#5b8cff")
        self.assertEqual(T.hex2rgb("#abc"), (170, 187, 204))

    def test_mix_endpoints_and_middle(self):
        self.assertEqual(T.mix("#000000", "#ffffff", 0.0), "#000000")
        self.assertEqual(T.mix("#000000", "#ffffff", 1.0), "#ffffff")
        self.assertEqual(T.mix("#000000", "#ffffff", 0.5), "#808080")

    def test_mix_clamps(self):
        self.assertEqual(T.mix("#000000", "#ffffff", -3), "#000000")
        self.assertEqual(T.mix("#000000", "#ffffff", 9), "#ffffff")

    def test_fade_in_simulates_alpha(self):
        self.assertEqual(T.fade_in("#ffffff", "#000000", 0.0), "#000000")
        self.assertEqual(T.fade_in("#ffffff", "#000000", 1.0), "#ffffff")

    def test_ramp_has_requested_steps(self):
        r = T.ramp("#000000", "#ffffff", 5)
        self.assertEqual(len(r), 5)
        self.assertEqual(r[0], "#000000")
        self.assertEqual(r[-1], "#ffffff")

    def test_status_colors_known(self):
        self.assertEqual(T.status_color("ready"), T.OK)
        self.assertEqual(T.status_color("missing"), T.WARN)
        self.assertEqual(T.status_color("nonsense"), T.FG_FAINT)

    def test_font_resolution_prefers_first_installed(self):
        fams = ["DejaVu Sans", "Ubuntu", "Consolas"]
        self.assertEqual(T.resolve_family(fams, T.UI_FAMILIES), "Ubuntu")
        self.assertEqual(T.resolve_family(fams, T.MONO_FAMILIES), "Consolas")
        self.assertEqual(T.resolve_family([], T.UI_FAMILIES), T.UI_FAMILIES[-1])

    def test_font_resolution_is_case_insensitive(self):
        self.assertEqual(T.resolve_family(["segoe ui"], T.UI_FAMILIES), "segoe ui")

    def test_symbols_cover_both_sets(self):
        self.assertEqual(set(T.symbols(True)), set(T.symbols(False)))
        self.assertNotEqual(T.symbols(True)["folder"], T.symbols(False)["folder"])


class TestEasing(unittest.TestCase):
    def test_all_easings_are_fixed_points(self):
        for fn in (logic.linear, logic.out_cubic, logic.out_quart, logic.in_out_cubic,
                   logic.out_back, logic.out_elastic):
            self.assertAlmostEqual(fn(0.0), 0.0, places=6, msg=fn.__name__)
            self.assertAlmostEqual(fn(1.0), 1.0, places=6, msg=fn.__name__)

    def test_out_cubic_starts_fast_and_settles(self):
        # ease-out: always ahead of linear, i.e. covers ground early and eases in
        for t in (0.05, 0.25, 0.5, 0.75, 0.95):
            self.assertGreaterEqual(logic.out_cubic(t), t, f"t={t}")
        self.assertLess(logic.out_cubic(0.9) - logic.out_cubic(0.8),
                        logic.out_cubic(0.2) - logic.out_cubic(0.1))   # decelerating

    def test_clamp01(self):
        self.assertEqual(logic.clamp01(-1), 0.0)
        self.assertEqual(logic.clamp01(2), 1.0)
        self.assertEqual(logic.clamp01(0.4), 0.4)


class TestTween(unittest.TestCase):
    def test_progress_reaches_one_and_fires_once(self):
        seen, done = [], []
        tw = logic.Tween(0.1, on_update=seen.append, on_done=lambda: done.append(1))
        for _ in range(20):
            if tw.advance(0.05):
                break
        self.assertTrue(tw.done)
        self.assertEqual(seen[-1], 1.0)
        self.assertEqual(len(done), 1)
        tw.advance(1.0)                     # idempotent
        self.assertEqual(len(done), 1)

    def test_reverse_goes_1_to_0(self):
        seen = []
        tw = logic.Tween(0.1, easing=logic.linear, reverse=True, on_update=seen.append)
        tw.advance(0.05)
        self.assertAlmostEqual(seen[0], 0.5)      # half-way in, half-way back
        tw.advance(0.05)
        self.assertAlmostEqual(seen[-1], 0.0)     # must land exactly on 0

    def test_delay_defers_start(self):
        seen = []
        tw = logic.Tween(0.1, delay=5.0, on_update=seen.append)
        self.assertFalse(tw.advance(0.05))
        self.assertEqual(seen, [])

    def test_zero_duration_snaps(self):
        seen = []
        tw = logic.Tween(0.0, on_update=seen.append)
        tw.advance(0.016)
        self.assertEqual(seen, [1.0])

    def test_finish_jumps_to_end(self):
        seen = []
        tw = logic.Tween(10.0, on_update=seen.append)
        tw.finish()
        self.assertTrue(tw.done)
        self.assertEqual(seen[-1], 1.0)

    def test_animator_ticks_until_empty(self):
        anim = logic.Animator(fps=60)
        anim.add(logic.Tween(0.1), logic.Tween(0.05), logic.Tween(0.2))
        self.assertEqual(anim.active, 3)
        for _ in range(3):
            anim.tick(0.05)
        self.assertEqual(anim.active, 1)

    def test_animator_snap_when_duration_zero(self):
        anim = logic.Animator()
        out = []
        anim.add(logic.Tween(0.0, on_update=out.append))
        anim.tick()
        self.assertEqual(out, [1.0])

    def test_stop_removes_tween(self):
        anim = logic.Animator()
        tw = logic.sweep(1.0)
        anim.add(tw)
        anim.stop(tw)
        self.assertFalse(tw.running)
        self.assertEqual(anim.active, 0)

    def test_pulse_oscillates_between_0_and_1(self):
        vals = []
        p = logic.pulse(1.0, on_update=vals.append)
        for _ in range(120):
            p.advance(1 / 60)
        self.assertGreater(max(vals), 0.95)
        self.assertLess(min(vals), 0.05)
        self.assertFalse(p.done)                    # endless until stopped
        p.stop()
        self.assertTrue(p.advance(0.016))

    def test_sweep_goes_0_to_1_and_wraps(self):
        vals = []
        s = logic.sweep(1.0, on_update=vals.append)
        for _ in range(130):                        # 1.3 periods at 10 ms steps
            s.advance(0.01)
        self.assertLess(vals[0], 0.05)
        self.assertGreater(max(vals), 0.9)
        self.assertAlmostEqual(vals[-1], 0.3, delta=0.05)   # wrapped past 1.0

    def test_chain_keeps_order(self):
        order = []
        a = logic.Tween(0.05, on_done=lambda: order.append("a"))
        b = logic.Tween(0.05, on_done=lambda: order.append("b"))
        anim = logic.Animator()
        anim.add(logic.Tween.chain(a, b))
        # a must not start before b's delay-only sequencing matters, but both must fire
        for _ in range(20):
            anim.tick(0.016)
        self.assertEqual(order, ["a", "b"])


class TestTypewriter(unittest.TestCase):
    def test_reveals_progressively_then_completes(self):
        tw = logic.Typewriter(cps=100)
        tw.start("hello world")
        self.assertEqual(tw.advance(0.0), "")
        self.assertEqual(tw.advance(0.04), "hell")
        self.assertEqual(tw.advance(0.5), "hello world")
        self.assertTrue(tw.done)

    def test_long_text_types_faster(self):
        short = logic.Typewriter(cps=320)
        short.start("x" * 50)
        long = logic.Typewriter(cps=320)
        long.start("x" * 6000)
        self.assertGreater(long.rate(), short.rate())
        self.assertLessEqual(long.rate(), long.max_cps)

    def test_not_started_reports_done(self):
        tw = logic.Typewriter()
        self.assertTrue(tw.done)
        self.assertEqual(tw.advance(1.0), "")


class TestSuggestions(unittest.TestCase):
    NAMES = ["report.pdf", "notes.txt", "invoice-2024.pdf"]
    DIRS = ["work", "archive", "drafts"]

    def test_empty_input_shows_templates(self):
        s = logic.suggest("")
        self.assertTrue(s)
        self.assertTrue(all(isinstance(x, str) for x in s))
        self.assertLessEqual(len(s), 6)

    def test_partial_verb_completes_template(self):
        s = logic.suggest("cre")
        self.assertTrue(any(t.startswith("create") for t in s), s)

    def test_verb_completes_real_file_names(self):
        s = logic.suggest("move rep", self.NAMES, self.DIRS)
        self.assertIn("report.pdf", s)

    def test_verb_with_no_text_lists_items(self):
        s = logic.suggest("delete ", self.NAMES, self.DIRS)
        self.assertTrue(any("report.pdf" in x for x in s), s)

    def test_destination_suggests_folders_only(self):
        s = logic.suggest("move report.pdf to ar", self.NAMES, self.DIRS)
        self.assertIn("archive", s)
        self.assertNotIn("report.pdf", s)

    def test_no_match_returns_empty(self):
        self.assertEqual(logic.suggest("zzzz", self.NAMES, self.DIRS), [])

    def test_limit_respected(self):
        many = [f"file{i}.txt" for i in range(50)]
        self.assertLessEqual(len(logic.suggest("delete file", many, self.DIRS, limit=4)), 4)

    def test_score_ranks_exact_over_prefix_over_contains(self):
        self.assertGreater(logic._score("work", "work"), logic._score("workshop", "work"))
        self.assertGreater(logic._score("workshop", "work"), logic._score("my-work-x", "work"))


class TestHealthAndFormatting(unittest.TestCase):
    def test_grade_health_thresholds(self):
        self.assertEqual(logic.grade_health(0.2)[1], "ok")
        self.assertEqual(logic.grade_health(0.85)[1], "warn")
        self.assertEqual(logic.grade_health(0.99)[1], "error")

    def test_format_bytes(self):
        self.assertEqual(logic.format_bytes(0), "0 B")
        self.assertEqual(logic.format_bytes(999), "999 B")
        self.assertEqual(logic.format_bytes(1024), "1.0 KB")
        self.assertEqual(logic.format_bytes(5 * 1024 ** 3), "5.0 GB")

    def test_progress_label(self):
        self.assertEqual(logic.progress_label(1, 4), "1/4 · 25%")
        self.assertEqual(logic.progress_label(0, 0), "nothing to do")

    def test_greeting_by_hour(self):
        import datetime as dt
        self.assertEqual(logic.greeting(dt.datetime(2026, 1, 1, 8)), "Good morning")
        self.assertEqual(logic.greeting(dt.datetime(2026, 1, 1, 14)), "Good afternoon")
        self.assertEqual(logic.greeting(dt.datetime(2026, 1, 1, 19)), "Good evening")
        self.assertEqual(logic.greeting(dt.datetime(2026, 1, 1, 2)), "Working late")

    def test_truncate(self):
        self.assertEqual(logic.truncate("a" * 100, 10), "a" * 9 + "…")
        self.assertEqual(logic.truncate("short", 10), "short")

    def test_keys_hint_mentions_shortcuts(self):
        self.assertIn("Tab", logic.keys_hint())


if __name__ == "__main__":
    unittest.main()
