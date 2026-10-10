"""Offline contract tests for resumable send/hold data retrieval."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import requests

from cubs_edge_lab.probe.client import atomic_json
from cubs_edge_lab.probe.sendhold import main, regular_season_games, retrieve


def schedule_fixture():
    games = [
        {"gamePk": 12, "season": 2025, "gameType": "R"},
        {"gamePk": 10, "season": 2025, "gameType": "R"},
        {"gamePk": 10, "season": 2025, "gameType": "R"},
        {"gamePk": 13, "season": 2025, "gameType": "S"},
        {"gamePk": 14, "season": 2025, "gameType": "P"},
        {"gamePk": 15, "season": 2026, "gameType": "R"},
    ]
    return {"dates": [{"games": games}]}


def response_for(url, params):
    if url.endswith("/schedule"):
        season = params["season"]
        if season == 2025:
            return json.dumps(schedule_fixture()).encode()
        return json.dumps({"dates": [{"games": [
            {"gamePk": 20, "season": 2026, "gameType": "R"}
        ]}]}).encode()
    if "/playByPlay" in url:
        return b'{"allPlays": []}'
    return b"player_id,player_name\n"


class RetrieveTests(unittest.TestCase):
    def client_session(self, failing=None):
        session = Mock()

        def get(url, params, **kwargs):
            if failing and failing(url):
                return Mock(content=b"unavailable", status_code=500)
            return Mock(content=response_for(url, params), status_code=200)

        session.get.side_effect = get
        return session

    def test_schedule_filters_deduplicates_and_sorts(self):
        self.assertEqual(
            regular_season_games(schedule_fixture(), 2025),
            [
                {"season": 2025, "gamePk": 10},
                {"season": 2025, "gamePk": 12},
            ],
        )

    def test_command_form_parses_retrieve_subcommand(self):
        with tempfile.TemporaryDirectory() as temp:
            Path(temp, "data").mkdir()
            atomic_json(Path(temp, "data/sendhold_request_ledger.json"),
                        {"count": 4899})
            with self.assertRaises(SystemExit) as raised:
                main(["retrieve", "--root", temp, "--max-requests", "2"])
            self.assertEqual(raised.exception.code, 2)

    def test_max_requests_and_resume_reuse_cache(self):
        with tempfile.TemporaryDirectory() as temp:
            session = self.client_session()
            with patch(
                "cubs_edge_lab.probe.client.RateLimiter.wait", Mock()
            ):
                first = retrieve(temp, 4, session=session)
                self.assertEqual(first["new_requests_this_invocation"], 4)
                self.assertFalse(first["complete"])
                initial_calls = session.get.call_count
                second = retrieve(temp, 20, session=session)
            self.assertEqual(initial_calls, 4)
            self.assertEqual(session.get.call_count, 11)
            self.assertEqual(second["cached"], 4)
            self.assertEqual(second["new_requests_this_invocation"], 7)
            manifest = json.loads(
                Path(temp, "data/sendhold_manifest.json").read_text()
            )
            self.assertEqual(len(manifest), 11)
            self.assertFalse(Path(temp, "research/raw_manifest.json").exists())

    def test_persistent_ceiling_allows_last_three_then_stops(self):
        with tempfile.TemporaryDirectory() as temp:
            Path(temp, "data").mkdir()
            atomic_json(Path(temp, "data/sendhold_request_ledger.json"),
                        {"count": 4897})
            session = self.client_session()
            with patch(
                "cubs_edge_lab.probe.client.RateLimiter.wait", Mock()
            ):
                status = retrieve(temp, 3, session=session)
            self.assertEqual(status["new_requests_this_invocation"], 3)
            self.assertEqual(status["ledger_count"], 4900)
            self.assertEqual(session.get.call_count, 3)
            with self.assertRaises(SystemExit):
                main(["retrieve", "--root", temp, "--max-requests", "1"])
            self.assertEqual(session.get.call_count, 3)

    def test_final_chunk_uses_remaining_ceiling_budget(self):
        with tempfile.TemporaryDirectory() as temp:
            Path(temp, "data").mkdir()
            atomic_json(Path(temp, "data/sendhold_request_ledger.json"),
                        {"count": 4889})
            session = self.client_session()
            with patch(
                "cubs_edge_lab.probe.client.RateLimiter.wait", Mock()
            ):
                with self.assertRaises(Exception):
                    retrieve(temp, 200, session=session)
                session.get.assert_not_called()
                status = retrieve(temp, 11, session=session)
            self.assertTrue(status["complete"])
            self.assertEqual(status["new_requests_this_invocation"], 11)
            self.assertEqual(status["ledger_count"], 4900)
            self.assertEqual(session.get.call_count, 11)

    def test_max_requests_above_budget_fails_before_network(self):
        with tempfile.TemporaryDirectory() as temp:
            Path(temp, "data").mkdir()
            atomic_json(Path(temp, "data/sendhold_request_ledger.json"),
                        {"count": 4899})
            session = self.client_session()
            with self.assertRaises(Exception):
                retrieve(temp, 2, session=session)
            session.get.assert_not_called()

    def test_failure_status_is_recorded_and_not_retried(self):
        with tempfile.TemporaryDirectory() as temp:
            session = self.client_session(
                failing=lambda url: "/game/10/playByPlay" in url
            )
            with patch(
                "cubs_edge_lab.probe.client.RateLimiter.wait", Mock()
            ):
                first = retrieve(temp, 20, session=session)
                calls = session.get.call_count
                second = retrieve(temp, 20, session=session)
            failures = json.loads(
                Path(temp, "data/sendhold_failures.json").read_text()
            )
            game_failures = [item for item in failures
                             if item["gamePk"] == 10]
            self.assertEqual(game_failures[0]["http_status"], 500)
            self.assertFalse(first["complete"])
            self.assertEqual(second["remaining"], 1)
            self.assertEqual(session.get.call_count, calls)
            self.assertEqual(first["ledger_count"], second["ledger_count"])
            response = next(
                item for item in json.loads(
                    Path(temp, "data/sendhold_manifest.json").read_text()
                )
                if item["endpoint"].endswith("/game/10/playByPlay")
            )
            self.assertEqual(response["http_status"], 500)

    def test_http_404_is_recorded_with_status(self):
        with tempfile.TemporaryDirectory() as temp:
            session = Mock()

            def get(url, params, **kwargs):
                if "/game/10/playByPlay" in url:
                    return Mock(content=b"unavailable", status_code=404)
                return Mock(content=response_for(url, params), status_code=200)

            session.get.side_effect = get
            with patch(
                "cubs_edge_lab.probe.client.RateLimiter.wait", Mock()
            ):
                status = retrieve(temp, 20, session=session)
            failures = json.loads(
                Path(temp, "data/sendhold_failures.json").read_text()
            )
            game_failure = next(
                item for item in failures if item["gamePk"] == 10
            )
            self.assertEqual(game_failure["http_status"], 404)
            self.assertEqual(status["failed"], 1)
            self.assertEqual(status["remaining"], 1)

    def test_request_exception_is_recorded_as_exception(self):
        with tempfile.TemporaryDirectory() as temp:
            session = self.client_session()
            original = session.get.side_effect

            def get(url, params, **kwargs):
                if "/game/10/playByPlay" in url:
                    raise requests.RequestException("offline fixture")
                return original(url, params, **kwargs)

            session.get.side_effect = get
            with patch(
                "cubs_edge_lab.probe.client.RateLimiter.wait", Mock()
            ):
                status = retrieve(temp, 20, session=session)
            failures = json.loads(
                Path(temp, "data/sendhold_failures.json").read_text()
            )
            self.assertEqual(
                next(item for item in failures if item["gamePk"] == 10)[
                    "http_status"
                ],
                "exception",
            )
            self.assertEqual(status["remaining"], 1)

    def test_season_specific_failures_do_not_suppress_other_requests(self):
        with tempfile.TemporaryDirectory() as temp:
            session = Mock()
            requested = []

            def get(url, params, **kwargs):
                requested.append((url, dict(params)))
                failed_schedule = (
                    url.endswith("/schedule")
                    and params.get("season") == 2025
                )
                failed_leaderboard = (
                    url.endswith("/sprint_speed")
                    and params.get("min_season") == 2024
                )
                if failed_schedule or failed_leaderboard:
                    return Mock(content=b"unavailable", status_code=503)
                return Mock(content=response_for(url, params), status_code=200)

            session.get.side_effect = get
            with patch(
                "cubs_edge_lab.probe.client.RateLimiter.wait", Mock()
            ):
                status = retrieve(temp, 20, session=session)
                calls = session.get.call_count
                retrieve(temp, 20, session=session)
            self.assertEqual(session.get.call_count, calls)
            self.assertTrue(any(
                url.endswith("/schedule") and params.get("season") == 2026
                for url, params in requested
            ))
            self.assertTrue(any(
                url.endswith("/sprint_speed")
                and params.get("min_season") == 2025
                for url, params in requested
            ))
            failures = json.loads(
                Path(temp, "data/sendhold_failures.json").read_text()
            )
            self.assertEqual(
                {(item["endpoint"], item["params"].get("season"),
                  item["params"].get("min_season"))
                 for item in failures},
                {
                    ("https://statsapi.mlb.com/api/v1/schedule", 2025, None),
                    ("https://baseballsavant.mlb.com/leaderboard/sprint_speed",
                     None, 2024),
                },
            )
            self.assertGreaterEqual(status["remaining"], 2)

    def test_missing_ledger_bootstraps_from_legacy_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            Path(temp, "research").mkdir()
            atomic_json(Path(temp, "research/raw_manifest.json"), [
                {"endpoint": "https://statsapi.mlb.com/api/v1/schedule",
                 "params": {"season": 2025, "gameType": "R"}},
            ])
            status = retrieve(temp, 0, session=self.client_session())
            self.assertEqual(status["ledger_count"], 1)
            self.assertEqual(
                json.loads(Path(temp, "data/sendhold_request_ledger.json")
                           .read_text())["count"],
                1,
            )


if __name__ == "__main__":
    unittest.main()
