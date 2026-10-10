"""Offline checks of the SENDHOLD FIT stage (synthetic fixtures only)."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from cubs_edge_lab.probe.sendhold_fit import (
    build_fit, fit_pipeline, label_for, load_fit_rows, main, prepare_rows,
    re_states, run_fit)

from .sendhold_fixtures import (
    HAND_P_STAR, RE_TABLE, make_rows, write_root)

ROW_LEVEL_KEYS = {"runner_id", "game_id", "hit_coordinates", "season_rows"}


def keys_anywhere(value):
    found = set()
    if isinstance(value, dict):
        for key, child in value.items():
            found.add(key)
            found |= keys_anywhere(child)
    elif isinstance(value, list):
        for child in value:
            found |= keys_anywhere(child)
    return found


class FitTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.addCleanup(self.directory.cleanup)
        self.rows_2025 = make_rows(2025, 500, 1.5)

    def fit(self, rows, **kwargs):
        write_root(self.root, rows, **kwargs)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            run_fit(self.root)
        return out.getvalue().strip()

    def test_break_even_states_match_hand_values(self):
        states = re_states(RE_TABLE)
        for key, expected in HAND_P_STAR.items():
            self.assertAlmostEqual(states[key]["p_star"], expected)
        self.assertEqual(states["single|0"]["re_hold"], 1.5)
        self.assertEqual(states["double|1"]["re_out_at_home"], 0.35)
        self.assertEqual(states["double|1"]["re_scored"], 0.7)

    def test_missing_state_gives_null_break_even(self):
        table = dict(RE_TABLE)
        del table[(5, 0)]
        self.assertIsNone(re_states(table)["single|0"]["p_star"])

    def test_fit_writes_both_label_versions_and_hash(self):
        printed = self.fit(self.rows_2025 + make_rows(2026, 200, 1.5))
        data_bytes = (self.root / "data/sendhold_fit.json").read_bytes()
        self.assertEqual(printed, hashlib.sha256(data_bytes).hexdigest())
        published = json.loads(
            (self.root / "research/sendhold_fit.json").read_bytes())
        self.assertEqual(set(published["versions"]), {"v3", "v2"})
        self.assertEqual(published["primary_label_version"], "v3")
        v3 = published["versions"]["v3"]
        v2 = published["versions"]["v2"]
        self.assertTrue(v3["primary"])
        self.assertFalse(v2["primary"])
        self.assertEqual(v3["mode"], "MODEL")
        # v3 keeps runners that v2 excluded, so it has more SENT_SAFE.
        self.assertGreater(v3["label_counts"]["SENT_SAFE"],
                           v2["label_counts"]["SENT_SAFE"])
        self.assertEqual(v3["label_counts"]["SENT_OUT"],
                         v3["sent_out"])
        self.assertEqual(v3["covariate_choice"]["name"], "reduced")
        self.assertEqual(len(v3["send_success_model"]["coefficients"]),
                         len(v3["send_success_model"]["standard_errors"]))
        self.assertGreater(v3["send_success_model"]["coefficients"][1], 0)
        self.assertGreater(v3["support_threshold"], 0)
        self.assertEqual(len(published["state_mapping"]) > 5, True)
        self.assertFalse(keys_anywhere(published) & ROW_LEVEL_KEYS)
        self.assertEqual(
            (self.root / "research/sendhold_fit.json").read_bytes(),
            (json.dumps(published, indent=2) + "\n").encode())

    def test_decision_chart_counts_and_marks_small_cells(self):
        self.fit(self.rows_2025)
        chart = json.loads((self.root / "data/sendhold_fit.json")
                           .read_text())["versions"]["v3"]["decision_chart"]
        cells = chart["cells"]
        action = [r for r in self.rows_2025
                  if r["label_v3"] in ("SENT_SAFE", "SENT_OUT", "HOLD")]
        self.assertEqual(sum(c["n"] for c in cells), len(action))
        self.assertEqual(chart["min_cell_n"], 10)
        for cell in cells:
            self.assertEqual(cell["low_n"], cell["n"] < 10)
            self.assertTrue(0 <= cell["mean_p_safe"] <= 1)
            self.assertAlmostEqual(
                cell["p_star"], HAND_P_STAR["{}|{}".format(
                    cell["hit_type"], cell["outs"])])

    def test_descriptive_only_below_30_sent_out(self):
        rows = make_rows(2025, 120, 1.5)
        self.fit(rows)
        v3 = json.loads((self.root / "data/sendhold_fit.json")
                        .read_text())["versions"]["v3"]
        self.assertLess(v3["sent_out"], 30)
        self.assertEqual(v3["mode"], "DESCRIPTIVE ONLY")
        for absent in ("send_success_model", "propensity_model",
                       "decision_chart"):
            self.assertNotIn(absent, v3)
        rate = v3["out_at_home"]
        self.assertAlmostEqual(rate["rate"], rate["sent_out"] / rate["sends"])
        self.assertLessEqual(rate["interval_95"]["lower"], rate["rate"])
        self.assertGreaterEqual(rate["interval_95"]["upper"], rate["rate"])

    def test_fit_never_reads_2026_rows(self):
        poison = make_rows(2026, 400, -3.0, send_rate=0.9)
        for row in poison:
            row.update(label="SENT_OUT", label_v3="SENT_OUT",
                       sprint_speed=1e6, outs=99, hit_type="triple")
        seasons = {"2026": {"label_counts": {"SENT_OUT": 10 ** 6}}}
        clean_hash = self.fit(self.rows_2025)
        clean = (self.root / "data/sendhold_fit.json").read_bytes()
        clean_published = (self.root / "research/sendhold_fit.json"
                           ).read_bytes()
        poisoned_hash = self.fit(self.rows_2025 + poison,
                                 report_seasons=seasons)
        self.assertEqual(poisoned_hash, clean_hash)
        self.assertEqual(
            (self.root / "data/sendhold_fit.json").read_bytes(), clean)
        self.assertEqual(
            (self.root / "research/sendhold_fit.json").read_bytes(),
            clean_published)
        loaded = load_fit_rows(
            self.root / "data/sendhold_opportunity_table.json")
        self.assertEqual({row["season"] for row in loaded}, {2025})
        self.assertEqual(len(loaded), len(self.rows_2025))

    def test_only_2026_rows_gives_no_fit_rows(self):
        write_root(self.root, make_rows(2026, 50, 1.5))
        self.assertEqual(load_fit_rows(
            self.root / "data/sendhold_opportunity_table.json"), [])

    def test_stale_table_without_v3_labels_is_refused(self):
        row = dict(make_rows(2025, 1, 1.0)[0])
        del row["label_v3"]
        with self.assertRaises(ValueError):
            label_for(row, "v3")
        self.assertEqual(label_for(row, "v2"), row["label"])
        with self.assertRaises(ValueError):
            label_for(make_rows(2025, 1, 1.0)[0], "v4")

    def test_label_versions_and_fallback_drop(self):
        rows = [dict(r) for r in make_rows(2025, 60, 1.5)]
        rows[0]["label_v3"] = "AMBIGUOUS"
        self.assertEqual(label_for(rows[0], "v3_ambiguous_as_safe"),
                         "SENT_SAFE")
        kept = prepare_rows(rows, "v3", drop_fallback=True)
        flagged = sum(bool(r["sprint_speed_same_season_fallback"])
                      for r in rows)
        self.assertGreater(flagged, 0)
        self.assertEqual(len(kept), len(rows) - flagged)

    def test_pipeline_columns_override_keeps_chosen_set(self):
        rows = prepare_rows(self.rows_2025, "v3")
        pipeline = fit_pipeline(rows, columns=("sprint_speed", "outs"))
        self.assertEqual(pipeline["send_success_model"]["columns"],
                         ["sprint_speed", "outs"])
        self.assertEqual(pipeline["covariate_choice"]["name"], "reduced")

    def test_build_fit_is_deterministic(self):
        first = build_fit(self.rows_2025, RE_TABLE)
        second = build_fit(self.rows_2025, RE_TABLE)
        self.assertEqual(json.dumps(first), json.dumps(second))

    def test_cli_runs_in_a_root(self):
        write_root(self.root, self.rows_2025)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["--root", str(self.root)]), 0)
        self.assertTrue((self.root / "data/sendhold_fit.json").exists())


if __name__ == "__main__":
    unittest.main()
