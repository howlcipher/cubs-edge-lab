"""Offline data-acquisition tests using temporary roots and fixtures."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from unittest.mock import patch

from cubs_edge_lab.probe.client import ApiError, Client
from cubs_edge_lab.triage import (
    as_of_features,
    attach_features,
    coverage,
    select_cohort,
)
from cubs_edge_lab.triage_cli import (
    cached_people_by_id,
    cubs_signings,
    fetch,
    median_k_basis,
    request_guard,
)
from cubs_edge_lab.triage_config import (
    INVITATION_PATTERN,
    MINOR_CONTRACT_PATTERN,
)


class TriageDataTests(unittest.TestCase):
    def test_pagination_and_short_last_page(self):
        class Fake:
            root = Path(tempfile.gettempdir()) / "not-used"

            def __init__(self):
                self.calls = []

            def get(self, endpoint, **params):
                self.calls.append(params)
                if endpoint != "stats":
                    return {"transactions": []}
                off = params["offset"]
                values = [
                    {
                        "season": params["season"],
                        "sport": {"id": 1},
                        "player": {"id": off + n + 1},
                        "team": {"id": 1},
                        "stat": {"gamesPlayed": 1},
                    }
                    for n in range(2 if off == 0 else 1)
                ]
                return {
                    "stats": [
                        {
                            "group": {"displayName": params["group"]},
                            "totalSplits": 3,
                            "splits": values,
                        }
                    ]
                }

        client = Fake()
        with tempfile.TemporaryDirectory() as tmp:
            client.root = Path(tmp)
            with patch("cubs_edge_lab.triage_cli.PAGE_SIZE", 2):
                fetch(client)
            stat_seasons = [
                call["season"] for call in client.calls if "season" in call
            ]
            self.assertTrue(stat_seasons)
            self.assertLess(max(stat_seasons), 2026)
            self.assertEqual(set(stat_seasons), set(range(2017, 2026)))
            artifact = json.loads(
                (Path(tmp) / "data/stats/2017_1_hitting.json").read_text()
            )
            self.assertEqual(
                [p["offset"] for p in client.calls if "offset" in p][:2],
                [0, 2],
            )
            self.assertEqual(len(artifact["rows"]), 3)
            self.assertFalse(artifact["truncated"])

    def test_truncation_flag_and_season_ceiling(self):
        class Fake:
            root = Path()

            def get(self, endpoint, **params):
                if endpoint == "stats":
                    return {
                        "stats": [
                            {
                                "group": {"displayName": "hitting"},
                                "totalSplits": 2,
                                "splits": [
                                    {
                                        "season": params["season"],
                                        "sport": {"id": 1},
                                        "player": {"id": 1},
                                        "stat": {},
                                    }
                                ],
                            }
                        ]
                    }
                return {"transactions": []}

        self.assertRaises(ValueError, request_guard, "stats", {"season": 2026})
        with tempfile.TemporaryDirectory() as tmp:
            fake = Fake()
            fake.root = Path(tmp)
            with patch("cubs_edge_lab.triage_cli.PAGE_SIZE", 2):
                fetch(fake)
            report = json.loads(
                (Path(tmp) / "data/stats/2017_1_hitting.json").read_text()
            )
            self.assertTrue(report["truncated"])

    def test_request_budget_counts_only_new_requests(self):
        with tempfile.TemporaryDirectory() as tmp:
            session = Mock()
            response = Mock(status_code=200, content=b'{"ok": true}')
            session.get.return_value = response
            client = Client(tmp, session=session, request_cap=1)
            client.get("teams")
            client.get("teams")
            self.assertEqual(client.new_request_count, 1)
            with self.assertRaises(ApiError):
                client.get("people", personIds="3")

    def test_id_only_join_same_names_and_missing_id(self):
        pool, _ = select_cohort(
            [
                {
                    "date": "2022-11-01",
                    "code": "DFA",
                    "description": "elected free agency",
                    "player_id": 1,
                },
                {
                    "date": "2022-11-02",
                    "code": "DFA",
                    "description": "elected free agency",
                    "player_id": 2,
                },
            ],
            2022,
        )
        people = [
            {"person_id": 1, "birth_date": "2000-01-01", "name": "Same Name"},
            {"person_id": 2, "birth_date": "2000-01-01", "name": "Same Name"},
        ]
        stats = [
            {
                "person_id": 1,
                "season": 2022,
                "sport_id": 1,
                "group": "hitting",
                "stat": {"plateAppearances": 20},
            },
            {
                "person_id": None,
                "season": 2022,
                "sport_id": 1,
                "group": "hitting",
                "stat": {"plateAppearances": 99},
            },
        ]
        rows, _ = attach_features(pool, people, stats, [])
        self.assertEqual([row["person_id"] for row in rows], [1, 2])
        self.assertEqual(rows[0]["pa"], 20)
        self.assertEqual(rows[1]["pa"], 0)

    def test_highest_level_uses_mlb_over_lower_levels_and_excludes_y_plus_one(
        self,
    ):
        stats = [
            {
                "person_id": 1,
                "season": 2022,
                "sport_id": 14,
                "group": "hitting",
                "stat": {"plateAppearances": 8},
            },
            {
                "person_id": 1,
                "season": 2022,
                "sport_id": 1,
                "group": "hitting",
                "stat": {"plateAppearances": 20},
            },
            {
                "person_id": 1,
                "season": 2022,
                "sport_id": 11,
                "group": "hitting",
                "stat": {"plateAppearances": 12},
            },
            {
                "person_id": 1,
                "season": 2023,
                "sport_id": 1,
                "group": "hitting",
                "stat": {"plateAppearances": 100},
            },
        ]
        result = as_of_features(1, "2022-11-01", "2000-12-01", stats)
        self.assertEqual(result["highest_level"], 1)
        self.assertEqual(result["pa"], 20)
        self.assertEqual(result["age"], 21)
        self.assertEqual(
            {row["season"] for row in result["season_stats"]}, {2022}
        )

    def test_birth_dates_are_reused_from_successful_people_cache_by_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data/raw/people.json"
            path.parent.mkdir(parents=True)
            path.write_text(
                json.dumps(
                    {
                        "people": [
                            {
                                "id": 1,
                                "birthDate": "2000-01-02",
                                "fullName": "Private",
                            },
                            {"id": 2, "fullName": "No birth date"},
                        ]
                    }
                )
            )
            entries = [
                {
                    "endpoint": "https://statsapi.mlb.com/api/v1/people",
                    "http_status": 200,
                    "file": "data/raw/people.json",
                },
                {
                    "endpoint": "https://statsapi.mlb.com/api/v1/people",
                    "http_status": 400,
                    "file": "data/raw/people.json",
                },
            ]
            people = cached_people_by_id(tmp, entries)
            self.assertEqual(people[1]["birth_date"], "2000-01-02")
            self.assertIsNone(people[2]["birth_date"])
            self.assertNotIn("fullName", people[1])

    def test_coverage_reasons_and_no_mlb_share(self):
        pool = [
            {"person_id": 1, "date": "2022-11-01"},
            {"person_id": 2, "date": "2022-11-01"},
            {"person_id": 3, "date": "2022-11-01"},
        ]
        rows = [
            {
                "person_id": 1,
                "season_stats": [{"season": 2022}],
                "mlb_pa_y": 0,
                "mlb_ip_y": 0,
            },
            {"person_id": 2, "season_stats": [], "mlb_pa_y": 2, "mlb_ip_y": 0},
        ]
        result = coverage(pool, rows, {"missing_person": 1})
        self.assertEqual(
            result["unmatched_reasons"],
            {
                "no_season_y_stats_in_cached_levels": 1,
                "person_record_missing": 1,
            },
        )
        self.assertEqual(
            sum(result["unmatched_reasons"].values()), result["unmatched"]
        )
        self.assertEqual(
            result["matched"] + result["unmatched"], result["pool_size"]
        )
        self.assertEqual(result["no_mlb_in_y_share"], 1.0)
        self.assertEqual(result["no_mlb_in_y_known_denominator"], 1)

    def test_main_fetch_never_requests_season_2026(self):
        from cubs_edge_lab.triage_cli import main

        with tempfile.TemporaryDirectory() as tmp:
            with patch("cubs_edge_lab.triage_cli.Client") as client_type:
                fake = client_type.return_value
                fake.root = Path(tmp)
                fake.get.side_effect = lambda endpoint, **params: (
                    {"stats": [{"totalSplits": 0, "splits": []}]}
                    if endpoint == "stats"
                    else {"transactions": []}
                )
                with patch("sys.argv", ["triage", "fetch"]):
                    with patch(
                        "cubs_edge_lab.triage_cli.Client", return_value=fake
                    ):
                        main()
                seasons = [
                    call.kwargs.get("season")
                    for call in fake.get.call_args_list
                    if call.kwargs.get("season") is not None
                ]
                self.assertTrue(seasons)
                self.assertLess(max(seasons), 2026)

    def test_cubs_rules_and_median(self):
        import re

        descriptions = [
            "Signed a minor-league contract",
            "Non-roster invitation",
            "Invited to spring training",
            "Signed and invited to camp",
            "Signed to a contract",
        ]
        minor = [
            bool(re.search(MINOR_CONTRACT_PATTERN, row, re.I))
            for row in descriptions
        ]
        invite = [
            bool(re.search(INVITATION_PATTERN, row, re.I))
            for row in descriptions
        ]
        self.assertEqual(minor, [True, False, False, False, False])
        self.assertEqual(invite, [False, True, True, True, False])
        self.assertEqual(median_k_basis([1, 3, 4]), 3)
        self.assertEqual(median_k_basis([1, 3, 4, 10]), 3.5)

    def test_cubs_counts_overlap_unmatched_and_examples(self):
        class Fake:
            def get(self, endpoint, **params):
                rows = [
                    {
                        "id": 1,
                        "date": "2021-11-01",
                        "typeCode": "SFA",
                        "typeDesc": "Signed",
                        "description": "Minor-league contract",
                        "person": {"id": 1},
                    },
                    {
                        "id": 2,
                        "date": "2021-11-02",
                        "typeCode": "SFA",
                        "typeDesc": "Signed",
                        "description": "Non-roster invitation",
                        "person": {"id": 2},
                    },
                    {
                        "id": 3,
                        "date": "2021-11-03",
                        "typeCode": "SFA",
                        "typeDesc": "Signed",
                        "description": (
                            "Minor-league contract; invited to camp"
                        ),
                        "person": {"id": 3},
                    },
                    {
                        "id": 4,
                        "date": "2021-11-04",
                        "typeCode": "SFA",
                        "typeDesc": "Signed",
                        "description": "Signed to a contract",
                        "person": {"id": 4},
                    },
                ]
                return {"transactions": rows}

        result = cubs_signings(Fake(), 2021)
        self.assertEqual(result["minor_contracts"], 2)
        self.assertEqual(result["spring_invitations"], 2)
        self.assertEqual(result["overlap"], 1)
        self.assertEqual(result["combined"], 3)
        self.assertEqual(result["other_signing_unmatched"], 1)
        self.assertLessEqual(len(result["examples"]), 5)


if __name__ == "__main__":
    unittest.main()
