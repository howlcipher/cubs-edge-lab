"""Fixture-only tests for the additive Cubs descriptive case."""

import hashlib
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from cubs_edge_lab import cubs_case


class CubsCaseTests(unittest.TestCase):
    def fixture(self, root):
        (root / "research").mkdir()
        (root / "data/cohorts").mkdir(parents=True)
        (root / "data/stats").mkdir(parents=True)
        (root / "data/raw").mkdir(parents=True)
        base_rates = {}
        manifest = []
        for year in cubs_case.YEARS:
            base_rates[str(year)] = {"primary": {"positives": 1}}
            people = [
                {
                    "person_id": year * 10 + 1,
                    "election_date": f"{year}-11-10",
                    "no_mlb_appearance_y": True,
                },
                {
                    "person_id": year * 10 + 2,
                    "election_date": f"{year}-11-10",
                    "no_mlb_appearance_y": False,
                },
                {
                    "person_id": year * 10 + 3,
                    "election_date": f"{year}-11-10",
                    "no_mlb_appearance_y": True,
                },
            ]
            (root / "data/cohorts" / f"{year}.json").write_text(
                json.dumps({"year": year, "features": people})
            )
            transactions = [
                self.transaction(year * 10 + 1, f"{year}-11-10"),
                self.transaction(year * 10 + 2, f"{year + 1}-03-31"),
                self.transaction(year * 10 + 3, f"{year}-11-09"),
            ]
            raw_path = root / "data/raw" / f"{year}.json"
            raw = json.dumps({"transactions": transactions}).encode()
            raw_path.write_bytes(raw)
            manifest.append(
                {
                    "endpoint": "https://statsapi.mlb.com/api/v1/transactions",
                    "params": {
                        "teamId": 112,
                        "startDate": f"{year}-11-01",
                        "endDate": f"{year + 1}-03-31",
                    },
                    "file": str(raw_path.relative_to(root)),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                }
            )
            for group in ("hitting", "pitching"):
                row = {
                    "person_id": year * 10 + 1,
                    "group": group,
                    "stat": {
                        "plateAppearances": 50 if group == "hitting" else 0,
                        "inningsPitched": "0.0",
                        "gamesPlayed": 1,
                    },
                }
                artifact = {
                    "season": year + 1,
                    "rows": [row],
                    "truncated": False,
                    "coverage_unknown": False,
                }
                stats_path = root / "data/stats" / f"{year + 1}_1_{group}.json"
                stats_path.write_text(json.dumps(artifact))
        (root / "research/raw_manifest.json").write_text(json.dumps(manifest))
        (root / "research/validation.json").write_text(
            json.dumps(
                {
                    "base_rates": base_rates,
                    "early_stop": True,
                    "early_stop_reason": (
                        "validation primary positives below 30"
                    ),
                    "validation": None,
                }
            )
        )
        (root / "data/cohorts/2025.json").write_text("must not be read")
        (root / "research/EXPERIMENT.md").write_text("sentinel\n")
        (root / "research/exploratory_whole_pool.json").write_text("unchanged")

    @staticmethod
    def transaction(person_id, date):
        return {
            "person": {"id": person_id, "fullName": "fixture name"},
            "date": date,
            "description": "Signed a minor-league contract",
        }

    def test_year_selection_and_id_only_join_and_inclusive_player_window(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root)
            reads = []
            original = Path.read_text
            original_bytes = Path.read_bytes

            def tracked(path, *args, **kwargs):
                reads.append(str(path))
                return original(path, *args, **kwargs)

            def tracked_bytes(path, *args, **kwargs):
                reads.append(str(path))
                return original_bytes(path, *args, **kwargs)

            with (
                patch.object(Path, "read_text", tracked),
                patch.object(Path, "read_bytes", tracked_bytes),
            ):
                payload = cubs_case.calculate(root)
            self.assertFalse(
                any("cohorts/2025.json" in item for item in reads)
            )
            for row in payload["cohorts"]:
                self.assertEqual(row["cubs_signed"], 2)
                self.assertEqual(row["cubs_signed_outcome_positive"], 1)
                self.assertEqual(row["cubs_signed_no_mlb_in_y"], 1)
                self.assertEqual(
                    row["cubs_signed_no_mlb_in_y_outcome_positive"], 1
                )
                self.assertEqual(row["league_no_mlb_in_y_outcome_positive"], 1)
            self.assertEqual(len(payload["examples"]), 4)

    def test_markdown_numbers_come_from_json_and_primary_files_are_untouched(
        self,
    ):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root)
            protected = [
                root / "research/validation.json",
                root / "research/exploratory_whole_pool.json",
            ]
            before = [path.read_bytes() for path in protected]
            payload = cubs_case.write_artifacts(root)
            report = cubs_case.render_section(payload)
            saved_report = (root / "research/EXPERIMENT.md").read_text()
            saved_json = json.loads(
                (root / "research/cubs_case.json").read_text()
            )
            self.assertTrue(saved_report.startswith("sentinel\n\n"))
            self.assertTrue(saved_report.endswith(report))
            self.assertEqual(saved_json, payload)
            self.assertTrue((root / "research/cubs_case.json").is_file())
            json_text = json.dumps(payload, sort_keys=True)
            for number in re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?", report):
                self.assertIn(number, json_text)
            self.assertIn(
                "FACT: The method was not tested "
                "(pre-registered early stop).", report
            )
            self.assertNotIn("failed its pre-registered test", report)
            self.assertIn(
                "UNKNOWN: Availability, contract terms, and competing offers",
                report,
            )
            self.assertEqual([path.read_bytes() for path in protected], before)
            self.assertLessEqual(len(payload["examples"]), 5)

    def test_method_status_comes_from_validation(self):
        self.assertEqual(
            cubs_case._method_status(
                {
                    "early_stop": True,
                    "validation": None,
                    "early_stop_reason": (
                        "validation primary positives below 30"
                    ),
                }
            ),
            "was not tested (pre-registered early stop)",
        )
        self.assertEqual(
            cubs_case._method_status(
                {"early_stop": False, "validation": {"metrics": {}}}
            ),
            "did not record the pre-registered early-stop failure",
        )

    def test_duplicate_report_marker_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root)
            path = root / "research/EXPERIMENT.md"
            path.write_text("## Cubs case (descriptive)\n\n" * 2)
            with self.assertRaisesRegex(RuntimeError, "duplicate"):
                cubs_case.write_artifacts(root)

    def test_bad_cache_and_conflicting_election_dates_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root)
            manifest_path = root / "research/raw_manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest[0]["sha256"] = "0" * 64
            manifest_path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(RuntimeError, "checksum"):
                cubs_case._transaction_rows(root, cubs_case.YEARS[0])
        cohort = {
            "features": [
                {"person_id": 1, "election_date": "2021-11-01"},
                {"person_id": 1, "election_date": "2021-11-02"},
            ]
        }
        with self.assertRaisesRegex(ValueError, "conflicting election"):
            cubs_case._signed_person_dates([], cohort, 2021)
        invalid = {
            "features": [
                {"person_id": 1, "election_date": "not-a-date"},
            ]
        }
        with self.assertRaisesRegex(ValueError, "election date"):
            cubs_case._signed_person_dates([], invalid, 2021)


if __name__ == "__main__":
    unittest.main()
