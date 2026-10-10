"""Offline checks of the SENDHOLD EVALUATE stage (synthetic fixtures only).

The fixtures are invented for these tests; nothing here touches real data.
"""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from cubs_edge_lab.probe.sendhold_evaluate import (
    MAX_EXAMPLES, SPECS, criteria, evaluate_rows, main, render, run_evaluate,
    score, verdict_for)
from cubs_edge_lab.probe.sendhold_fit import (
    build_fit, fit_pipeline, prepare_rows, re_states, run_fit)

from .sendhold_fixtures import (
    RE_TABLE, RE_TABLE_NO_FLAGS, make_rows, write_root)

RESAMPLES = 30


def passing(**overrides):
    checks = {
        "brier_beats_constant": {"passed": True},
        "calibration_slope": {"passed": True},
        "runs_left_excludes_zero": {"passed": True},
        "negative_control": {"passed": True}}
    for key, value in overrides.items():
        checks[key] = {"passed": value}
    return checks


class VerdictRuleTests(unittest.TestCase):
    def test_rules(self):
        self.assertEqual(verdict_for(passing(), "DESCRIPTIVE ONLY"),
                         "DESCRIPTIVE ONLY")
        self.assertEqual(verdict_for(passing(), "MODEL"), "POSITIVE")
        self.assertEqual(
            verdict_for(passing(brier_beats_constant=False), "MODEL"),
            "NEGATIVE")
        self.assertEqual(
            verdict_for(passing(calibration_slope=False), "MODEL"),
            "NEGATIVE")
        self.assertEqual(
            verdict_for(passing(runs_left_excludes_zero=False), "MODEL"),
            "INCONCLUSIVE")
        self.assertEqual(
            verdict_for(passing(negative_control=False), "MODEL"),
            "INCONCLUSIVE")

    def test_criteria_are_separate_and_conservative(self):
        point = {"brier_diff_constant": -0.05, "calibration_slope": 1.31,
                 "runs_left": 4.0, "flagged_send_realized": 0.8,
                 "flagged_send_mean_predicted": 0.8, "flagged_sends": 40}
        interval = {"lower": -0.08, "upper": -0.01}
        boot = {"intervals_95": {
            "brier_diff_constant": interval,
            "calibration_slope": None,
            "runs_left": {"lower": 0.0, "upper": 9.0},
            "flagged_send_mean_predicted": {"lower": 0.7, "upper": 0.79}}}
        checks = criteria(point, boot)
        self.assertTrue(checks["brier_beats_constant"]["passed"])
        self.assertFalse(checks["calibration_slope"]["passed"])
        self.assertFalse(checks["runs_left_excludes_zero"]["passed"])
        self.assertFalse(checks["negative_control"]["passed"])
        point["calibration_slope"] = 0.7
        point["flagged_send_realized"] = 0.79
        boot["intervals_95"]["runs_left"]["lower"] = 0.1
        checks = criteria(point, boot)
        self.assertTrue(checks["calibration_slope"]["passed"])
        self.assertTrue(checks["runs_left_excludes_zero"]["passed"])
        self.assertTrue(checks["negative_control"]["passed"])
        point["flagged_send_realized"] = None
        self.assertFalse(
            criteria(point, boot)["negative_control"]["passed"])


class SupportFilterTests(unittest.TestCase):
    def test_holds_below_threshold_are_dropped_and_counted(self):
        def model(coefficients):
            return {"columns": ["sprint_speed"],
                    "center": {"sprint_speed": 0.0},
                    "scale": {"sprint_speed": 1.0},
                    "coefficients": coefficients}
        pipeline = {
            "send_success_model": model([2.0, 0.0]),  # P(safe) = 0.88
            "propensity_model": model([0.0, 1.0]),
            "support_threshold": 0.5,
            "constant_rate": 0.5, "outs_rates": {}}
        states = re_states(RE_TABLE)

        def hold(speed):
            return {"lab": "HOLD", "sprint_speed": speed, "outs": 0,
                    "hit_type": "single", "batting_team_id": 112,
                    "game_id": 1}
        # propensity = sigmoid(speed): -1 -> 0.27 (dropped), 0 -> 0.5 (kept,
        # exactly at the threshold), 1 and 2 kept.
        rows = [hold(-1.0), hold(0.0), hold(1.0), hold(2.0)]
        result = score(pipeline, rows, states)
        self.assertEqual(result["holds_supported"], 3)
        self.assertEqual(result["holds_dropped_share"], 0.25)
        self.assertEqual(result["flagged_holds"], 3)
        gain = 0.88079707797788 * (0.9 + 1.0) + 0.11920292202212 * 0.55 - 1.5
        self.assertAlmostEqual(result["runs_left"], 3 * gain, places=6)
        self.assertEqual(result["cubs_flagged_holds"], 3)
        # Holds below p* + 0.05 are not flagged: raise p* past P(safe).
        high = dict(states)
        high["single|0"] = dict(states["single|0"], p_star=0.9)
        self.assertEqual(score(pipeline, rows, high)["flagged_holds"], 0)


class SyntheticEvaluationTests(unittest.TestCase):
    def build(self, rows_2025, rows_2026, table=RE_TABLE):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        write_root(root, rows_2025 + rows_2026, table)
        with contextlib.redirect_stdout(io.StringIO()):
            run_fit(root)
        return root

    def evaluate(self, rows_2025, rows_2026, table=RE_TABLE):
        root = self.build(rows_2025, rows_2026, table)
        report = run_evaluate(root, resamples=RESAMPLES)
        return root, report

    def test_positive_known_verdict(self):
        self.positive_report()

    def positive_report(self):
        # The 2026 synthetic world is slightly flatter than 2025 so the
        # flagged sends' realized rate sits inside the predicted interval.
        root, report = self.evaluate(make_rows(2025, 500, 1.5),
                                     make_rows(2026, 500, 1.15))
        primary = report["analyses"]["v3_primary"]
        checks = primary["criteria"]
        self.assertEqual(report["verdict"], "POSITIVE",
                         json.dumps(checks, indent=1))
        for name, check in checks.items():
            self.assertTrue(check["passed"], name)
        self.assertLess(
            primary["point_2026"]["brier_diff_constant"], 0)
        self.assertGreater(primary["point_2026"]["flagged_holds"], 0)
        self.assertGreater(primary["point_2026"]["runs_left"], 0)
        self.assertEqual(primary["bootstrap"]["resamples"], RESAMPLES)
        self.assertEqual(set(report["analyses"]), {s[0] for s in SPECS})
        for name in ("v2_preregistered", "v3_ambiguous_as_safe",
                     "v3_fallback_dropped"):
            self.assertIn("verdict", report["analyses"][name])
        self.assertLess(
            report["analyses"]["v3_fallback_dropped"]["rows_2026"],
            primary["rows_2026"])
        self.assertEqual(report["verdict_v2_preregistered_definition"],
                         report["analyses"]["v2_preregistered"]["verdict"])
        return root, report

    def test_outputs_are_aggregate_only_and_labelled(self):
        root, report = self.positive_report()
        text = (root / "research/SENDHOLD_EXPERIMENT.md").read_text()
        published = json.loads(
            (root / "research/sendhold_experiment.json").read_bytes())
        self.assertEqual(
            (root / "research/sendhold_experiment.json").read_bytes(),
            (json.dumps(published, indent=2) + "\n").encode())
        self.assertEqual(published["verdict"], "POSITIVE")
        self.assertLessEqual(len(published["examples"]), MAX_EXAMPLES)
        self.assertGreater(len(published["examples"]), 0)
        for example in published["examples"]:
            self.assertEqual(set(example), {
                "game_id", "hit_type", "outs", "p_safe", "p_star"})
        self.assertRegex(published["fit_sha256"], r"^[a-f0-9]{64}$")
        self.assertEqual(text, render(published))
        for tag in ("FACT:", "INFERENCE:", "UNKNOWN:"):
            self.assertIn(tag, text)
        self.assertIn("POSITIVE", text)
        self.assertNotIn("runner_id", json.dumps(published))
        # Each criterion appears on its own table row.
        for label in ("Brier difference", "Calibration slope", "Runs left",
                      "Negative control"):
            self.assertIn(label, text)
        for season in ("2025", "2026"):
            self.assertIn(season, report["analyses"]["v3_primary"]["cubs"])

    def test_negative_known_verdict(self):
        _, report = self.evaluate(make_rows(2025, 500, 1.5),
                                  make_rows(2026, 500, -1.5))
        self.assertEqual(report["verdict"], "NEGATIVE")
        checks = report["analyses"]["v3_primary"]["criteria"]
        self.assertFalse(checks["brier_beats_constant"]["passed"])
        self.assertFalse(checks["calibration_slope"]["passed"])

    def test_inconclusive_known_verdict(self):
        _, report = self.evaluate(make_rows(2025, 500, 1.5),
                                  make_rows(2026, 500, 1.5),
                                  table=RE_TABLE_NO_FLAGS)
        primary = report["analyses"]["v3_primary"]
        self.assertEqual(report["verdict"], "INCONCLUSIVE")
        self.assertTrue(primary["criteria"]["brier_beats_constant"]["passed"])
        self.assertTrue(primary["criteria"]["calibration_slope"]["passed"])
        self.assertEqual(primary["point_2026"]["flagged_holds"], 0)
        self.assertFalse(
            primary["criteria"]["runs_left_excludes_zero"]["passed"])
        self.assertEqual(report["examples"], [])

    def test_descriptive_only_when_fewer_than_30_sent_out(self):
        _, report = self.evaluate(make_rows(2025, 120, 1.5),
                                  make_rows(2026, 120, 1.5))
        primary = report["analyses"]["v3_primary"]
        self.assertEqual(report["verdict"], "DESCRIPTIVE ONLY")
        self.assertLess(primary["sent_out_2025"], 30)
        self.assertNotIn("bootstrap", primary)
        for season in ("2025", "2026"):
            item = primary["descriptive_" + season]
            self.assertIn("out_at_home_interval_95", item)

    def test_bootstrap_is_deterministic_under_seed(self):
        rows_2025, rows_2026 = (make_rows(2025, 300, 1.5),
                                make_rows(2026, 300, 1.5))
        frozen = build_fit(rows_2025, RE_TABLE)
        first = evaluate_rows(rows_2025, rows_2026, frozen, resamples=8)
        again = evaluate_rows(rows_2025, rows_2026, frozen, resamples=8)
        other = evaluate_rows(rows_2025, rows_2026, frozen, resamples=8,
                              seed=1)
        self.assertEqual(json.dumps(first), json.dumps(again))
        self.assertNotEqual(
            first["analyses"]["v3_primary"]["bootstrap"]["intervals_95"],
            other["analyses"]["v3_primary"]["bootstrap"]["intervals_95"])

    def test_refuses_without_frozen_fit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_root(root, make_rows(2025, 50, 1.0))
            with self.assertRaises(FileNotFoundError):
                run_evaluate(root, resamples=2)
            error = io.StringIO()
            with contextlib.redirect_stderr(error):
                with self.assertRaises(SystemExit) as raised:
                    main(["--root", directory, "--resamples", "2"])
            self.assertEqual(raised.exception.code, 2)
            self.assertIn("sendhold_fit.json", error.getvalue())
            self.assertFalse(
                (root / "research/SENDHOLD_EXPERIMENT.md").exists())

    def test_changed_inputs_do_not_match_frozen_fit(self):
        rows_2025 = make_rows(2025, 500, 1.5)
        root = self.build(rows_2025, make_rows(2026, 100, 1.5))
        changed = make_rows(2025, 500, 0.5) + make_rows(2026, 100, 1.5)
        (root / "data/sendhold_opportunity_table.json").write_text(
            json.dumps(changed))
        with self.assertRaises(RuntimeError):
            run_evaluate(root, resamples=2)

    def test_design_hash_mismatch_is_refused(self):
        root = self.build(make_rows(2025, 500, 1.5), make_rows(2026, 50, 1.5))
        path = root / "data/sendhold_fit.json"
        frozen = json.loads(path.read_text())
        frozen["design_sha256"] = "0" * 64
        path.write_text(json.dumps(frozen))
        with self.assertRaises(RuntimeError):
            run_evaluate(root, resamples=2)

    def test_refit_inside_each_resample(self):
        from unittest.mock import patch
        import cubs_edge_lab.probe.sendhold_evaluate as module
        rows_2025 = prepare_rows(make_rows(2025, 300, 1.5), "v3")
        rows_2026 = prepare_rows(make_rows(2026, 300, 1.5), "v3")
        calls = []
        real = fit_pipeline

        def counting(rows, columns=None):
            calls.append(len(rows))
            return real(rows, columns=columns)
        with patch.object(module, "fit_pipeline", counting):
            boot = module.bootstrap_scores(
                rows_2025, rows_2026, re_states(RE_TABLE),
                ["sprint_speed", "outs"], 6, 3)
        self.assertEqual(len(calls), 6)
        self.assertEqual(boot["usable_resamples"], 6)


if __name__ == "__main__":
    unittest.main()
