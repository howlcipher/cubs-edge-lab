"""Offline exploratory evaluation tests with synthetic local fixtures."""

import builtins
import hashlib
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from cubs_edge_lab import exploratory_whole_pool
from cubs_edge_lab.exploratory_whole_pool import evaluate, main
from cubs_edge_lab.triage_eval import choose_comparator, paired_bootstrap
from cubs_edge_lab.triage_experiment import _rank_eval, _round
from tests import test_triage_experiment

VALIDATION_SHA256 = (
    "cb4ca78fd4d695aec40f2c6edd5166255888ec1b4c5d7af0b6c0e36fdf270247"
)
PRIMARY_SHA256 = (
    "2a5e2b60432cfb1a8d1586979dd1bb156c4f37be108f1ee31db68ca4f676386e"
)


def _tokens(value):
    without_separators = re.sub(r"(?m)^\|[-|: ]+\|\s*$", "", value)
    return set(
        re.findall(r"(?<![A-Za-z0-9])-?\d+(?:\.\d+)?", without_separators)
    )


def _json_number_tokens(value):
    if isinstance(value, bool) or value is None:
        return set()
    if isinstance(value, (int, float)):
        return {str(value)}
    if isinstance(value, dict):
        return set().union(
            *(_json_number_tokens(item) for item in value.values())
        )
    if isinstance(value, list):
        return set().union(*(_json_number_tokens(item) for item in value))
    return set()


class ExploratoryWholePoolTests(unittest.TestCase):
    def fixture(self, root):
        test_triage_experiment.ExperimentTests.write_complete_fixture(
            root, validation_positives=32
        )
        poison = root / "data/cohorts/2025.json"
        poison.write_text("not valid json and must never be read")
        (root / "research").mkdir(exist_ok=True)
        (root / "research/validation.json").write_bytes(
            b"primary validation sentinel"
        )
        (root / "research/EXPERIMENT.md").write_bytes(
            b"primary report sentinel\n"
        )

    def test_2025_never_loaded_client_not_constructed_and_payload_excludes_it(
        self,
    ):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root)
            reads = []
            original = Path.read_text

            def tracked(path, *args, **kwargs):
                reads.append(str(path))
                return original(path, *args, **kwargs)

            original_open = builtins.open

            def tracked_open(path, *args, **kwargs):
                reads.append(str(path))
                return original_open(path, *args, **kwargs)

            with (
                patch.object(Path, "read_text", tracked),
                patch("builtins.open", tracked_open),
                patch(
                    "cubs_edge_lab.triage_eval.guard_outcome_build",
                    wraps=__import__(
                        "cubs_edge_lab.triage_eval",
                        fromlist=["guard_outcome_build"],
                    ).guard_outcome_build,
                ) as guard,
                patch(
                    "cubs_edge_lab.probe.client.Client",
                    side_effect=AssertionError("Client constructed"),
                ) as client,
            ):
                payload = evaluate(root, resamples=40)
            self.assertFalse(
                any("/cohorts/2025.json" in path for path in reads)
            )
            self.assertFalse(
                any(
                    call.kwargs.get(
                        "year", call.args[1] if len(call.args) > 1 else None
                    )
                    == 2025
                    for call in guard.call_args_list
                )
            )
            client.assert_not_called()
            self.assertNotIn("2025", json.dumps(payload["validation"]))
            self.assertEqual(payload["config"]["holdout_excluded"], 2025)

    def test_whole_pool_comparator_and_recorded_validation_tie_order(self):
        # Existing comparator helper's tie order is exercised on validation
        # rankings.
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root)
            original_metric_rows = exploratory_whole_pool._metric_rows
            original_rank_eval = exploratory_whole_pool._rank_eval_cached
            validation_rows = []
            validation_training = []

            def split_population(root_arg, cohort, stats):
                rows = original_metric_rows(root_arg, cohort, stats)
                if cohort["year"] == 2024:
                    for index, row in enumerate(rows):
                        row["no_mlb_appearance_y"] = index < 20
                        row["mlb_pa_y"] = 60 if index >= 20 else 0
                        row["met_threshold_y"] = index >= 20
                    validation_rows.extend(rows)
                return rows

            def separated_rankings(rows, training, strength):
                result = original_rank_eval(rows, training, strength)
                if len(rows) == 40:
                    validation_training[:] = training
                    hits = {"B0": 4, "B1": 3, "B2": 5, "P": 10}
                elif len(rows) == 20:
                    hits = {"B0": 8, "B1": 3, "B2": 5, "P": 4}
                else:
                    return result
                for method, count in hits.items():
                    result["rankings"][method]["top_k"]["50"]["hits"] = count
                return result

            with (
                patch.object(
                    exploratory_whole_pool,
                    "_metric_rows",
                    side_effect=split_population,
                ),
                patch.object(
                    exploratory_whole_pool,
                    "_rank_eval_cached",
                    side_effect=separated_rankings,
                ),
            ):
                payload = evaluate(root, resamples=30)
                primary_only = separated_rankings(
                    [
                        row
                        for row in validation_rows
                        if row["no_mlb_appearance_y"]
                    ],
                    validation_training,
                    payload["config"]["chosen_l2_strength"],
                )
            self.assertEqual(
                payload["comparator"],
                choose_comparator(
                    payload["validation"]["whole_pool"]["rankings"]
                ),
            )
            self.assertEqual(
                choose_comparator(
                    {
                        method: {"top_k": {"50": {"hits": 4}}}
                        for method in ("B0", "B1", "B2", "P")
                    }
                ),
                "B2",
            )
            self.assertIn("whole_pool", payload["validation"])
            self.assertEqual(choose_comparator(primary_only["rankings"]), "B0")
            self.assertEqual(payload["comparator"], "P")

    def test_bootstrap_determinism_seed_record_and_rank_eval_equivalence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root)
            first = evaluate(root)
            second = evaluate(root)
            self.assertEqual(first, second)
            self.assertEqual(first["config"]["bootstrap_resamples"], 2000)
            self.assertEqual(first["config"]["bootstrap_seed"], 43017)
            y, m, baseline = (
                [0, 1, 1, 0],
                [0.1, 0.8, 0.6, 0.3],
                [0.4, 0.5, 0.9, 0.2],
            )
            self.assertNotEqual(
                paired_bootstrap(y, m, baseline, 100, 43017),
                paired_bootstrap(y, m, baseline, 100, 43018),
            )

            # Whole-pool rank metrics match the existing direct implementation.
            stats = __import__(
                "cubs_edge_lab.triage_experiment", fromlist=["_stats"]
            )._stats(root)
            cohorts = {}
            for year in (2018, 2019, 2021, 2022, 2023, 2024):
                source = json.loads(
                    (root / f"data/cohorts/{year}.json").read_text()
                )
                from cubs_edge_lab.triage_experiment import _metric_rows

                cohorts[year] = _metric_rows(root, source, stats)
            training = [
                row
                for year in (2018, 2019, 2021, 2022, 2023)
                for row in cohorts[year]
            ]
            direct = _rank_eval(
                cohorts[2024], training, first["config"]["chosen_l2_strength"]
            )
            observed = first["validation"]["whole_pool"]
            for field in (
                "n",
                "positives",
                "base_rate",
                "rankings",
                "calibration",
            ):
                self.assertEqual(observed[field], _round(direct[field]))

    def test_labels_numbers_privacy_and_primary_files_stay_unchanged(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root)
            report_path = root / "research/EXPERIMENT.md"
            report_path.write_bytes(
                b"primary report sentinel\n"
                + exploratory_whole_pool.START.encode()
                + b"\nold exploratory section\n"
                + exploratory_whole_pool.END.encode()
                + b"\n\n## Cubs case (descriptive)\nFACT: preserved tail\n"
            )
            validation = (root / "research/validation.json").read_bytes()
            report = (root / "research/EXPERIMENT.md").read_bytes()
            self.assertEqual(
                main(["--root", str(root), "--resamples", "25"]), 0
            )
            first = (root / "research/EXPERIMENT.md").read_bytes()
            self.assertIn(b"## Cubs case (descriptive)", first)
            self.assertIn(b"FACT: preserved tail", first)
            json_text = (
                root / "research/exploratory_whole_pool.json"
            ).read_text()
            section = first.decode().split(
                "<!-- EXPLORATORY WHOLE POOL START -->", 1
            )[1].split("<!-- EXPLORATORY WHOLE POOL END -->", 1)[0]
            section = "<!-- EXPLORATORY WHOLE POOL START -->" + section
            for token in _tokens(section):
                self.assertIn(
                    token, _json_number_tokens(json.loads(json_text))
                )
            lines = section.splitlines()
            for index, line in enumerate(lines):
                if line.startswith("EXPLORATORY FACT:") and "table" in line:
                    self.assertTrue(lines[index + 1].startswith("|"))
                    self.assertTrue(lines[index + 2].startswith("|---"))
                    width = len(lines[index + 1].split("|"))
                    self.assertEqual(len(lines[index + 2].split("|")), width)
                elif line.startswith("|"):
                    self.assertGreater(index, 0)
                    self.assertTrue(
                        any(
                            "EXPLORATORY FACT:" in prior and "table" in prior
                            for prior in reversed(lines[:index])
                        )
                    )
                elif line and not line.startswith(("##", "<!--")):
                    self.assertRegex(
                        line, r"^EXPLORATORY (FACT|INFERENCE|UNKNOWN):"
                    )
            self.assertIn(
                "supports no usefulness claim or recommendation", section
            )
            self.assertNotRegex(
                json_text, r'"(?:person_id|name|player_name)"\s*:'
            )
            self.assertEqual(
                (root / "research/validation.json").read_bytes(), validation
            )
            self.assertEqual(
                first.split(exploratory_whole_pool.START.encode(), 1)[0],
                report.split(exploratory_whole_pool.START.encode(), 1)[0],
            )
            self.assertEqual(
                main(["--root", str(root), "--resamples", "25"]), 0
            )
            self.assertEqual(
                (root / "research/EXPERIMENT.md").read_bytes(), first
            )

    def test_missing_inputs_fail_before_writing_outputs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaises(SystemExit) as raised:
                main(["--root", str(root)])
            self.assertEqual(raised.exception.code, 2)
            self.assertFalse(
                (root / "research/exploratory_whole_pool.json").exists()
            )
            self.assertFalse((root / "research/EXPERIMENT.md").exists())

    def test_committed_primary_hashes_and_rendered_numbers(self):
        root = Path(__file__).resolve().parents[1]
        validation = (root / "research/validation.json").read_bytes()
        report = (root / "research/EXPERIMENT.md").read_bytes()
        primary = report.split(b"<!-- EXPLORATORY WHOLE POOL START -->")[0]
        self.assertEqual(
            hashlib.sha256(validation).hexdigest(), VALIDATION_SHA256
        )
        self.assertEqual(hashlib.sha256(primary).hexdigest(), PRIMARY_SHA256)
        output = root / "research/exploratory_whole_pool.json"
        if not output.is_file():
            self.skipTest(
                "exploratory output is generated after implementation tests"
            )
        payload = json.loads(output.read_text())
        section = report.split(
            b"<!-- EXPLORATORY WHOLE POOL START -->", 1
        )[1].split(b"<!-- EXPLORATORY WHOLE POOL END -->", 1)[0].decode()
        for token in _tokens(section):
            self.assertIn(token, _json_number_tokens(payload))
        self.assertIn(
            "EXPLORATORY FACT: 2024 whole_pool ranking metrics table", section
        )


if __name__ == "__main__":
    unittest.main()
