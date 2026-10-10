"""Offline checks of the SENDHOLD modeling primitives (synthetic data)."""
import math
import unittest

from cubs_edge_lab.probe.sendhold_model import (
    FULL_COLUMNS, REDUCED_COLUMNS, break_even, brier, calibration_slope,
    choose_covariates, clopper_pearson, featurize, fit_logistic_matrix,
    fit_model, game_bootstrap, percentile_interval, predict, quantile,
    state_value, support_threshold, zone_group)

from .sendhold_fixtures import RE_TABLE, frac, make_rows, sigmoid


class BreakEvenTests(unittest.TestCase):
    def test_hand_computed_example(self):
        # (1.2 - 0.3) / (0.9 + 1 - 0.3) = 0.9 / 1.6
        self.assertAlmostEqual(break_even(1.2, 0.3, 0.9), 0.5625)

    def test_three_outs_end_the_inning(self):
        self.assertEqual(state_value(RE_TABLE, 1, 3), 0.0)
        self.assertEqual(state_value(RE_TABLE, 1, 1), 0.55)
        self.assertIsNone(state_value(RE_TABLE, 7, 0))
        # out-at-home on a two-out play: (0.6 - 0) / (0.5 + 1 - 0)
        out = state_value(RE_TABLE, 1, 2 + 1)
        self.assertAlmostEqual(break_even(0.6, out, 0.5), 0.6 / 1.5)

    def test_degenerate_denominator_is_rejected(self):
        with self.assertRaises(ValueError):
            break_even(1.0, 2.0, 0.5)


class CovariateRuleTests(unittest.TestCase):
    def test_events_per_parameter_switch(self):
        parameters = len(FULL_COLUMNS) + 1
        required = 10 * parameters
        below = choose_covariates(required - 1)
        exact = choose_covariates(required)
        above = choose_covariates(required + 50)
        self.assertEqual(below["columns"], list(REDUCED_COLUMNS))
        self.assertEqual(below["name"], "reduced")
        self.assertEqual(exact["columns"], list(FULL_COLUMNS))
        self.assertEqual(above["name"], "full")
        self.assertEqual(exact["required_sent_out"], required)

    def test_custom_columns_and_rate(self):
        choice = choose_covariates(20, full=("a", "b"), reduced=("a",))
        self.assertEqual(choice["name"], "reduced")
        self.assertEqual(choose_covariates(30, full=("a", "b"),
                                           reduced=("a",))["name"], "full")


class SupportTests(unittest.TestCase):
    def test_threshold_is_2_5th_percentile_with_interpolation(self):
        self.assertAlmostEqual(support_threshold(list(range(101))), 2.5)
        self.assertAlmostEqual(support_threshold([0.4]), 0.4)
        with self.assertRaises(ValueError):
            support_threshold([])

    def test_quantile_endpoints(self):
        self.assertEqual(quantile([3, 1, 2], 0), 1)
        self.assertEqual(quantile([3, 1, 2], 1), 3)
        self.assertEqual(quantile([1, 2], 0.5), 1.5)


class LogisticTests(unittest.TestCase):
    def test_recovers_known_coefficients(self):
        matrix, outcomes = [], []
        for index in range(4000):
            x = 4.0 * frac(index, "speed") - 2.0
            p = sigmoid(-0.5 + 1.2 * x)
            matrix.append([1.0, x])
            outcomes.append(float(frac(index, "outcome") < p))
        fit = fit_logistic_matrix(matrix, outcomes)
        self.assertTrue(fit["converged"])
        self.assertAlmostEqual(fit["coefficients"][0], -0.5, delta=0.12)
        self.assertAlmostEqual(fit["coefficients"][1], 1.2, delta=0.12)
        self.assertTrue(all(e > 0 for e in fit["standard_errors"]))

    def test_one_class_is_rejected(self):
        with self.assertRaises(ValueError):
            fit_logistic_matrix([[1.0, 0.0], [1.0, 1.0]], [1.0, 1.0])
        with self.assertRaises(ValueError):
            fit_logistic_matrix([], [])

    def test_near_separation_stays_finite(self):
        matrix = [[1.0, float(x)] for x in range(-5, 6)]
        outcomes = [float(x > 0) for x in range(-5, 6)]
        fit = fit_logistic_matrix(matrix, outcomes)
        self.assertTrue(all(math.isfinite(c) for c in fit["coefficients"]))

    def test_model_standardizes_and_imputes(self):
        rows = [featurize(r) for r in make_rows(2025, 300, 1.5)]
        sends = [r for r in rows if r["label_v3"] in
                 ("SENT_SAFE", "SENT_OUT")]
        model = fit_model(sends, REDUCED_COLUMNS,
                          lambda r: r["label_v3"] == "SENT_SAFE")
        self.assertGreater(model["coefficients"][1], 0)
        missing = dict(sends[0], sprint_speed=None)
        mean_row = dict(sends[0], sprint_speed=model["center"]["sprint_speed"])
        self.assertAlmostEqual(predict(model, missing),
                               predict(model, mean_row))

    def test_zone_groups(self):
        self.assertEqual(
            [zone_group(z) for z in ("7", "5", "8", "2", "9", "4", None, "x")],
            ["left", "left", "center", "center", "right", "right", "center",
             "center"])


class MetricTests(unittest.TestCase):
    def test_brier_and_slope(self):
        self.assertAlmostEqual(brier([0.5, 1.0], [1, 1]), 0.125)
        predictions, outcomes = [], []
        for index in range(3000):
            p = 0.05 + 0.9 * frac(index, "speed")
            predictions.append(p)
            outcomes.append(float(frac(index, "outcome") < p))
        self.assertAlmostEqual(
            calibration_slope(predictions, outcomes), 1.0, delta=0.15)
        self.assertIsNone(calibration_slope([0.2, 0.4], [1, 1]))

    def test_clopper_pearson_known_values(self):
        zero = clopper_pearson(0, 10)
        self.assertEqual(zero["lower"], 0.0)
        self.assertAlmostEqual(zero["upper"], 1 - 0.025 ** (1 / 10), 5)
        full = clopper_pearson(10, 10)
        self.assertEqual(full["upper"], 1.0)
        self.assertAlmostEqual(full["lower"], 0.025 ** (1 / 10), 5)
        half = clopper_pearson(5, 10)
        self.assertAlmostEqual(half["lower"], 0.18709, places=4)
        self.assertAlmostEqual(half["upper"], 0.81291, places=4)
        self.assertIsNone(clopper_pearson(0, 0))


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.fit_games = {g: [{"v": g * 1.0}, {"v": g + 0.5}]
                          for g in range(10)}
        self.eval_games = {g: [{"v": g * 2.0}] for g in range(7)}

    def run_it(self, seed, counter=None):
        def statistic(fit_sample, eval_sample):
            if counter is not None:
                counter.append(len(fit_sample))
            return (sum(r["v"] for r in fit_sample) / len(fit_sample)
                    - sum(r["v"] for r in eval_sample) / len(eval_sample))
        return game_bootstrap(statistic, self.fit_games, self.eval_games,
                              resamples=25, seed=seed)

    def test_same_seed_is_identical_and_other_seed_differs(self):
        self.assertEqual(self.run_it(5), self.run_it(5))
        self.assertNotEqual(self.run_it(5), self.run_it(6))

    def test_statistic_runs_once_per_resample_with_whole_games(self):
        calls = []
        values = self.run_it(5, calls)
        self.assertEqual(len(values), 25)
        self.assertEqual(len(calls), 25)
        self.assertTrue(all(size == 20 for size in calls))

    def test_interval_and_empty_input(self):
        interval = percentile_interval([float(v) for v in range(101)])
        self.assertAlmostEqual(interval["lower"], 2.5)
        self.assertAlmostEqual(interval["upper"], 97.5)
        self.assertIsNone(percentile_interval([None]))
        with self.assertRaises(ValueError):
            game_bootstrap(lambda rows: 0, {}, resamples=2)


if __name__ == "__main__":
    unittest.main()
