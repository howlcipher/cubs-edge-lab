"""Offline regression tests for evaluation output and holdout protections."""

import json
from pathlib import Path
import re
import tempfile
import unittest
from cubs_edge_lab import triage_cli

from cubs_edge_lab.triage_eval import choose_comparator, paired_bootstrap
from cubs_edge_lab.triage_experiment import (
    _bootstrap_deltas,
    _metric_rows,
    _rank_eval,
    _stats,
    evaluate,
)
from cubs_edge_lab.triage_report import render
from unittest.mock import patch


class ExperimentTests(unittest.TestCase):
    @staticmethod
    def write_complete_fixture(
        root, validation_positives=32, empty_rolling=False
    ):
        (root / "data/cohorts").mkdir(parents=True)
        (root / "data/stats").mkdir(parents=True)
        years = (2018, 2019, 2021, 2022, 2023, 2024)
        for year in years:
            count = 40
            features = [
                {
                    "person_id": year * 1000 + index,
                    "no_mlb_appearance_y": True,
                    "player_type": "pitcher" if index % 2 else "hitter",
                    "mlb_pa_y": index,
                    "mlb_ip_y": index / 2,
                    "age": None if index == 0 else 20 + index % 15,
                    "highest_level": 11 + index % 4,
                    "ops": 0.3 + index / 100,
                    "bb_pct": 0.05,
                    "k_pct": 0.2,
                    "k_bb_pct": 0.1,
                    "era": 4.0,
                    "mlb_pa_y1": index % 3,
                    "mlb_ip_y1": index % 2,
                }
                for index in range(count)
            ]
            (root / f"data/cohorts/{year}.json").write_text(
                json.dumps({"year": year, "features": features})
            )
        outcome_seasons = {year + 1: year for year in years}
        for season, cohort_year in outcome_seasons.items():
            features_path = root / f"data/cohorts/{cohort_year}.json"
            if features_path.exists():
                features = json.loads(features_path.read_text())["features"]
            else:
                features = []
            positive_count = (
                validation_positives if cohort_year == 2024 else 32
            )
            rows = [
                {
                    "person_id": row["person_id"],
                    "group": "hitting",
                    "stat": {"plateAppearances": 50, "gamesPlayed": 1},
                }
                for row in features[:positive_count]
            ]
            for group in ("hitting", "pitching"):
                artifact_rows = rows if group == "hitting" else []
                (root / f"data/stats/{season}_1_{group}.json").write_text(
                    json.dumps(
                        {
                            "season": season,
                            "sport_id": 1,
                            "group": group,
                            "rows": artifact_rows,
                            "truncated": False,
                            "coverage_unknown": False,
                        }
                    )
                )

    def test_comparator_tie_order(self):
        def metrics(values):
            return {
                name: {"top_k": {"50": {"hits": value}}}
                for name, value in values.items()
            }

        self.assertEqual(
            choose_comparator(metrics({"B0": 2, "B1": 3, "B2": 4, "P": 1})),
            "B2",
        )
        for values, winner in [
            ({"B2": 1, "B0": 1, "B1": 0, "P": 0}, "B2"),
            ({"B2": 0, "B0": 1, "B1": 1, "P": 0}, "B0"),
            ({"B2": 0, "B0": 0, "B1": 1, "P": 1}, "B1"),
        ]:
            self.assertEqual(choose_comparator(metrics(values)), winner)

    def test_bootstrap_order_independent(self):
        y, m, b = [0, 1, 1, 0], [0.1, 0.8, 0.6, 0.3], [0.4, 0.5, 0.9, 0.2]
        first = paired_bootstrap(y, m, b, 100, 17)
        permuted = [2, 0, 3, 1]
        second = paired_bootstrap(
            [y[i] for i in permuted],
            [m[i] for i in permuted],
            [b[i] for i in permuted],
            100,
            17,
        )
        self.assertEqual(first, second)
        self.assertNotEqual(first, paired_bootstrap(y, m, b, 100, 18))

    def test_non_early_stop_scores_feed_real_bootstrap_metrics(self):
        training = []
        for index in range(80):
            positive = index % 2 == 0
            training.append(
                {
                    "person_id": index + 1,
                    "positive": positive,
                    "no_mlb_appearance_y": True,
                    "met_threshold_y": positive,
                    "mlb_pa_y": index % 5,
                    "mlb_ip_y": index % 3,
                    "highest_level": 11 + index % 4,
                    "age": 20 + index % 12,
                    "ops": 0.3 + 0.01 * index,
                    "bb_pct": 0.05,
                    "k_pct": 0.2 + 0.001 * index,
                    "k_bb_pct": 0.1,
                    "era": 4 - 0.01 * index,
                    "mlb_pa_y1": index % 7,
                    "mlb_ip_y1": index % 4,
                }
            )
        validation = []
        for index in range(40):
            row = dict(training[index])
            row["person_id"] = index + 1000
            row["positive"] = index < 20
            row["met_threshold_y"] = index < 20
            row["ops"] = 0.2 + 0.02 * index
            validation.append(row)
        result = _rank_eval(validation, training, 0.1)
        scores = result["_auc_scores"]
        self.assertEqual(len(set(scores["M"])), len(validation))
        self.assertEqual(len(set(scores["B2"])), len(validation))
        bootstrap = _bootstrap_deltas(
            [int(row["positive"]) for row in validation], scores
        )
        self.assertEqual(set(bootstrap), {"B0", "B1", "B2", "P"})
        self.assertTrue(
            all(item["valid_resamples"] > 0 for item in bootstrap.values())
        )
        self.assertEqual(
            result["rankings"]["M"]["auroc"],
            __import__("cubs_edge_lab.triage_eval", fromlist=["auc"]).auc(
                [int(row["positive"]) for row in validation], scores["M"]
            ),
        )

    def test_early_stop_and_report_number_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "data/cohorts").mkdir(parents=True)
            (root / "data/stats").mkdir(parents=True)
            for year in (2018, 2019, 2021, 2022, 2023, 2024):
                count = 29 if year == 2024 else 0
                features = [
                    {
                        "person_id": i,
                        "positive": False,
                        "no_mlb_appearance_y": True,
                        "player_type": "hitter",
                        "mlb_pa_y": 0,
                        "mlb_ip_y": 0,
                        "age": 25,
                        "highest_level": 14,
                        "ops": 0.5,
                        "bb_pct": 0,
                        "k_pct": 0,
                        "k_bb_pct": 0,
                        "era": 0,
                        "mlb_pa_y1": 0,
                        "mlb_ip_y1": 0,
                    }
                    for i in range(1, count + 1)
                ]
                (root / f"data/cohorts/{year}.json").write_text(
                    json.dumps({"year": year, "features": features})
                )
            for season in range(2019, 2026):
                for group in ("hitting", "pitching"):
                    rows = (
                        [
                            {
                                "person_id": i,
                                "group": "hitting",
                                "stat": {
                                    "plateAppearances": 50,
                                    "gamesPlayed": 1,
                                },
                            }
                            for i in range(1, 30)
                        ]
                        if season == 2025 and group == "hitting"
                        else []
                    )
                    artifact = {
                        "season": season,
                        "sport_id": 1,
                        "group": group,
                        "rows": rows,
                        "truncated": False,
                        "coverage_unknown": False,
                    }
                    (root / f"data/stats/{season}_1_{group}.json").write_text(
                        json.dumps(artifact)
                    )
            result = evaluate(root)
            self.assertTrue(result["early_stop"])
            self.assertEqual(
                result["base_rates"]["2024"]["primary"]["positives"], 29
            )
            self.assertIsNone(result["validation"])
            self.assertIsNone(result["rolling_origin"])
            with self.assertRaises(SystemExit):
                triage_cli.main(["preregister", "--root", str(root)])
            report = render(result)
            tokens = set(re.findall(r"\d+(?:\.\d+)?", report))
            json_text = json.dumps(result)
            for token in tokens:
                self.assertIn(token, json_text)

    def test_cli_full_evaluation_report_and_preregister_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaises(SystemExit):
                triage_cli.main(["preregister", "--root", str(root)])
            self.write_complete_fixture(root)
            self.assertEqual(
                triage_cli.main(["evaluate", "--root", str(root)]), 0
            )
            payload = json.loads(
                (root / "research/validation.json").read_text()
            )
            report = (root / "research/EXPERIMENT.md").read_text()
            self.assertFalse(payload["early_stop"])
            self.assertIsNotNone(payload["chosen_l2_strength"])
            self.assertIn(
                payload["chosen_comparator"], ("B0", "B1", "B2", "P")
            )
            self.assertEqual(
                set(payload["rolling_origin"]), {"2021", "2022", "2023"}
            )
            self.assertEqual(render(payload), report)
            for token in set(re.findall(r"\d+(?:\.\d+)?", report)):
                self.assertIn(token, json.dumps(payload))
            self.assertEqual(
                triage_cli.main(["preregister", "--root", str(root)]), 0
            )
            prereg = json.loads(
                (root / "research/preregistration.json").read_text()
            )
            self.assertIn("research/validation.json", prereg["sha256"])

    def test_empty_rolling_segment_renders_null_metrics(self):
        payload = {
            "config": {},
            "base_rates": {},
            "early_stop": False,
            "validation": {
                "rankings": {},
                "bootstrap_m_minus_baseline": {},
                "calibration": [],
            },
            "chosen_l2_strength": 0.1,
            "chosen_comparator": "B2",
            "rolling_origin": {
                "2021": {
                    "n": 0,
                    "positives": 0,
                    "base_rate": None,
                    "rankings": {},
                }
            },
        }
        report = render(payload)
        self.assertIn("| 2021 | 0 | 0 | None | None | None | None |", report)

    def test_persistence_uses_full_season_y_threshold(self):
        row = {
            "person_id": 7,
            "mlb_pa_y": 19,
            "mlb_ip_y": 7.2,
            "no_mlb_appearance_y": True,
        }
        result = _metric_rows(
            Path("."),
            {"year": 2019, "features": [row]},
            {2020: []},
        )
        self.assertFalse(result[0]["met_threshold_y"])

    def test_committed_markdown_is_json_derived(self):
        root = Path(__file__).resolve().parents[1]
        payload = json.loads((root / "research/validation.json").read_text())
        report = (root / "research/EXPERIMENT.md").read_text()
        primary = report.split("<!-- EXPLORATORY WHOLE POOL START -->")[0]
        self.assertEqual(render(payload), primary)
        for token in set(re.findall(r"\d+(?:\.\d+)?", primary)):
            self.assertIn(token, json.dumps(payload))

    def test_stats_loader_rejects_prohibited_season(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "data/stats"
            path.mkdir(parents=True)
            (path / "2026_1_hitting.json").write_text(
                json.dumps({"season": 2026, "rows": []})
            )
            with self.assertRaises(ValueError):
                _stats(temp)

    def test_evaluate_does_not_construct_client(self):
        from cubs_edge_lab import triage_cli

        with (
            tempfile.TemporaryDirectory() as temp,
            patch.object(
                triage_cli,
                "Client",
                side_effect=AssertionError("network client"),
            ) as client,
        ):
            with self.assertRaises((FileNotFoundError, RuntimeError)):
                triage_cli.main(["evaluate", "--root", temp])
            client.assert_not_called()


if __name__ == "__main__":
    unittest.main()
