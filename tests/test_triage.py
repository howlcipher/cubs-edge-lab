"""Offline tests for free-agent triage contracts."""

import json
from pathlib import Path
import tempfile
import unittest

from cubs_edge_lab.triage import age_on, outcome, rank, select_cohort
from cubs_edge_lab.triage_cli import fetch
from cubs_edge_lab.triage_eval import (
    LogisticModel,
    auc,
    calibration,
    guard_outcome_build,
    paired_bootstrap,
    preregistration_payload,
)


class TriageTests(unittest.TestCase):
    def test_evaluation_auroc_scores_follow_original_rows_and_ranker(self):
        from cubs_edge_lab.triage_eval import evaluate_rows

        rows = [
            {
                "person_id": 1,
                "positive": True,
                "mlb_pa_y": 0,
                "mlb_ip_y": 0,
                "highest_level": 1,
                "age": 30,
                "ops": 0.1,
                "k_bb_pct": 0.0,
                "met_threshold_y": False,
                "no_mlb_appearance_y": True,
            },
            {
                "person_id": 2,
                "positive": False,
                "mlb_pa_y": 0,
                "mlb_ip_y": 0,
                "highest_level": 1,
                "age": 20,
                "ops": 0.9,
                "k_bb_pct": 0.0,
                "met_threshold_y": False,
                "no_mlb_appearance_y": True,
            },
        ]
        result = evaluate_rows(rows)
        # B0 tie-break favors the younger non-outcome player; B1 favors its
        # better OPS. Scores still correspond to each person's label.
        self.assertEqual(result["rankings"]["B0"]["auroc"], 0.0)
        self.assertEqual(result["rankings"]["B1"]["auroc"], 0.0)

    def test_as_of_features_ignore_later_stats_and_transactions(self):
        from cubs_edge_lab.triage import as_of_features

        stats = [
            {
                "person_id": 7,
                "season": 2023,
                "sport_id": 1,
                "group": "hitting",
                "stat": {"plateAppearances": 11},
            },
            {
                "person_id": 7,
                "season": 2024,
                "sport_id": 1,
                "group": "hitting",
                "stat": {"plateAppearances": 99},
            },
        ]
        transactions = [
            {"player_id": 7, "date": "2023-11-01", "description": "old"},
            {"player_id": 7, "date": "2023-11-03", "description": "new"},
        ]
        result = as_of_features(
            7, "2023-11-02", "2000-11-02", stats, transactions
        )
        self.assertEqual(result["age"], 23)
        self.assertEqual(result["mlb_pa_y"], 11)
        descriptions = [r["description"] for r in result["transactions_as_of"]]
        self.assertEqual(descriptions, ["old"])

    def test_feature_rates_classification_and_baseball_innings(self):
        from cubs_edge_lab.triage import as_of_features

        rows = [
            {
                "person_id": 5,
                "season": 2023,
                "sport_id": 11,
                "group": "hitting",
                "stat": {
                    "plateAppearances": 100,
                    "baseOnBalls": 10,
                    "strikeOuts": 20,
                    "ops": ".800",
                },
            },
            {
                "person_id": 5,
                "season": 2023,
                "sport_id": 11,
                "group": "pitching",
                "stat": {
                    "inningsPitched": "12.1",
                    "strikeOuts": 15,
                    "baseOnBalls": 3,
                    "battersFaced": 50,
                    "era": "3.50",
                },
            },
            {
                "person_id": 5,
                "season": 2022,
                "sport_id": 1,
                "group": "pitching",
                "stat": {"inningsPitched": "1.2"},
            },
        ]
        result = as_of_features(5, "2023-11-01", "2000-01-01", rows)
        self.assertEqual(result["player_type"], "pitcher")
        self.assertEqual(result["bb_pct"], 0.1)
        self.assertEqual(result["k_pct"], 0.2)
        self.assertAlmostEqual(result["ip"], 37 / 3)
        self.assertEqual(result["mlb_ip_y1"], 5 / 3)

    def test_cohort_boundaries_duplicates_null_and_name_only(self):
        rows = [
            {
                "date": "2018-11-01",
                "code": "DFA",
                "description": "Elected free agency",
                "player_id": 1,
            },
            {
                "date": "2018-12-31",
                "code": "DFA",
                "description": "elected free agency",
                "player_id": 2,
            },
            {
                "date": "2018-10-31",
                "code": "DFA",
                "description": "elected free agency",
                "player_id": 3,
            },
            {
                "date": "2019-01-01",
                "code": "DFA",
                "description": "elected free agency",
                "player_id": 4,
            },
            {
                "date": "2018-11-02",
                "code": "X",
                "description": "elected free agency",
                "player_id": 5,
            },
            {
                "date": "2018-11-03",
                "code": "DFA",
                "description": "outrighted",
                "player_id": 6,
            },
            {
                "date": "2018-11-04",
                "code": "DFA",
                "description": "elected free agency",
                "player_id": None,
            },
            {
                "date": "2018-11-15",
                "code": "DFA",
                "description": "elected free agency",
                "player_id": 1,
                "person_name": "ignored",
            },
        ]
        cohort, nulls = select_cohort(rows, 2018)
        self.assertEqual(
            [(r["person_id"], r["date"]) for r in cohort],
            [(1, "2018-11-01"), (2, "2018-12-31")],
        )
        self.assertEqual(nulls, 1)

    def test_age_and_outcome_thresholds(self):
        self.assertEqual(age_on("2000-10-09", "2024-10-09"), 24)
        self.assertEqual(age_on("2000-10-10", "2024-10-10"), 24)
        self.assertTrue(
            outcome(
                [{"group": "hitting", "stat": {"plateAppearances": 50}}], 2023
            )["positive"]
        )
        self.assertFalse(
            outcome(
                [{"group": "hitting", "stat": {"plateAppearances": 49}}], 2023
            )["positive"]
        )
        self.assertTrue(
            outcome(
                [{"group": "pitching", "stat": {"inningsPitched": "20.0"}}],
                2023,
            )["positive"]
        )
        self.assertFalse(
            outcome(
                [{"group": "pitching", "stat": {"inningsPitched": "19.2"}}],
                2023,
            )["positive"]
        )
        self.assertTrue(
            outcome(
                [{"group": "hitting", "stat": {"plateAppearances": 19}}], 2019
            )["positive"]
        )
        self.assertFalse(
            outcome(
                [{"group": "hitting", "stat": {"plateAppearances": 18}}], 2019
            )["positive"]
        )
        self.assertTrue(
            outcome(
                [{"group": "pitching", "stat": {"inningsPitched": "7.2"}}],
                2019,
            )["positive"]
        )
        self.assertFalse(outcome([], 2023)["positive"])
        self.assertTrue(
            outcome([{"group": "hitting", "stat": {"gamesPlayed": 1}}], 2023)[
                "any_appearance"
            ]
        )

    def test_rankings_and_ties(self):
        rows = [
            {
                "person_id": 2,
                "mlb_pa_y": 10,
                "mlb_ip_y": 0,
                "highest_level": 14,
                "age": 24,
                "ops": 0.8,
                "k_bb_pct": 0.1,
                "m_probability": 0.8,
                "b2_probability": 0.2,
                "met_threshold_y": False,
                "player_type": "hitter",
            },
            {
                "person_id": 1,
                "mlb_pa_y": 10,
                "mlb_ip_y": 0,
                "highest_level": 13,
                "age": 23,
                "ops": 0.8,
                "k_bb_pct": 0.1,
                "m_probability": 0.8,
                "b2_probability": 0.2,
                "met_threshold_y": True,
                "player_type": "hitter",
            },
        ]
        self.assertEqual([x["person_id"] for x in rank(rows, "B0")], [1, 2])
        self.assertEqual([x["person_id"] for x in rank(rows, "B1")], [1, 2])
        self.assertEqual([x["person_id"] for x in rank(rows, "B2")], [1, 2])
        self.assertEqual([x["person_id"] for x in rank(rows, "P")], [1, 2])
        self.assertEqual([x["person_id"] for x in rank(rows, "M")], [1, 2])

    def test_rankings_level_age_missing_age_and_id_tiebreaks(self):
        base = {
            "mlb_pa_y": 0,
            "mlb_ip_y": 0,
            "ops": 0.5,
            "k_bb_pct": 0.1,
            "m_probability": 0.5,
            "b2_probability": 0.5,
            "met_threshold_y": False,
            "player_type": "hitter",
        }
        rows = [
            {**base, "person_id": 4, "highest_level": 14, "age": 20},
            {**base, "person_id": 3, "highest_level": 13, "age": None},
            {**base, "person_id": 2, "highest_level": 11, "age": 24},
            {**base, "person_id": 1, "highest_level": 11, "age": 22},
        ]
        for method in ("B0", "B1"):
            self.assertEqual(
                [r["person_id"] for r in rank(rows, method)], [1, 2, 3, 4]
            )

    def test_auc_calibration_bootstrap(self):
        self.assertEqual(auc([0, 1], [0.5, 0.5]), 0.5)
        self.assertEqual(calibration([1], [1.0])[-1]["count"], 1)
        first = paired_bootstrap(
            [0, 1, 0, 1], [0, 1, 1, 0], [1, 0, 1, 0], resamples=2000, seed=42
        )
        again = paired_bootstrap(
            [0, 1, 0, 1], [0, 1, 1, 0], [1, 0, 1, 0], resamples=2000, seed=42
        )
        other = paired_bootstrap(
            [0, 1, 0, 1], [0, 1, 1, 0], [1, 0, 1, 0], resamples=2000, seed=43
        )
        self.assertEqual(first, again)
        self.assertNotEqual(first, other)
        self.assertEqual(first["resamples"], 2000)

    def test_holdout_guard_and_request_ceiling(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(RuntimeError):
                guard_outcome_build(root, 2025)
            for path in [
                root / "cubs_edge_lab/triage.py",
                root / "cubs_edge_lab/triage_eval.py",
                root / "cubs_edge_lab/triage_config.py",
                root / "cubs_edge_lab/triage_cli.py",
                root / "cubs_edge_lab/triage_experiment.py",
                root / "cubs_edge_lab/triage_report.py",
                root / "research/validation.json",
            ]:
                path.parent.mkdir(parents=True, exist_ok=True)
                if not path.exists():
                    path.write_text("{}")
            (root / "research/validation.json").write_text("{}")
            payload = preregistration_payload(root)
            (root / "research/preregistration.json").write_text(
                json.dumps(payload)
            )
            self.assertTrue(guard_outcome_build(root, 2025))
            (root / "research/validation.json").unlink()
            with self.assertRaises(RuntimeError):
                guard_outcome_build(root, 2025)
            (root / "research/validation.json").write_text("{}")
            payload = preregistration_payload(root)
            (root / "research/preregistration.json").write_text(
                json.dumps(payload)
            )
            (root / "cubs_edge_lab/triage_new.py").write_text("new file")
            with self.assertRaises(RuntimeError):
                guard_outcome_build(root, 2025)
            (root / "cubs_edge_lab/triage_new.py").unlink()
            (root / "cubs_edge_lab/triage.py").write_text("mismatch")
            with self.assertRaises(RuntimeError):
                guard_outcome_build(root, 2025)
            self.assertTrue(guard_outcome_build(root, 2024))
            (root / "research/preregistration.json").write_text("{")
            with self.assertRaises(RuntimeError):
                guard_outcome_build(root, 2025)
            self.assertTrue(guard_outcome_build(root, 2024))

        class FakeClient:
            def __init__(self, root):
                self.root, self.calls = root, []

            def get(self, endpoint, **params):
                self.calls.append((endpoint, params))
                if endpoint == "stats":
                    return {
                        "stats": [
                            {
                                "group": {"displayName": params["group"]},
                                "totalSplits": 0,
                                "splits": [],
                            }
                        ]
                    }
                return {"transactions": []}

        with tempfile.TemporaryDirectory() as directory:
            client = FakeClient(Path(directory))
            fetch(client)
        stat_seasons = [
            params.get("season")
            for endpoint, params in client.calls
            if endpoint == "stats"
        ]
        self.assertTrue(stat_seasons)
        self.assertLess(max(stat_seasons), 2026)
        with self.assertRaises(ValueError):
            guard_outcome_build(Path("."), 2026)

    def test_logistic_model_fits_training_statistics_only(self):
        model = LogisticModel(iterations=200).fit(
            [{"x": 0}, {"x": 2}], [0, 1], ["x"]
        )
        self.assertEqual(model.means, [1.0])
        self.assertEqual(model.scales, [1.0])
        self.assertGreater(model.predict_proba([{"x": 2}], ["x"])[0], 0.5)

    def test_logistic_model_imputes_missing_value_with_training_mean(self):
        model = LogisticModel(iterations=20).fit(
            [{"age": 20}, {"age": None}, {"age": 30}], [0, 0, 1], ["age"]
        )
        self.assertEqual(model.means, [25.0])
        self.assertEqual(
            model.predict_proba([{"age": None}], ["age"]),
            model.predict_proba([{"age": 25}], ["age"]),
        )


if __name__ == "__main__":
    unittest.main()
