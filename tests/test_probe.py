import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from cubs_edge_lab.probe.client import (
    ApiError,
    Client,
    MalformedResponseError,
    RateLimiter,
)
from cubs_edge_lab.probe.parse import (
    innings_outs,
    stats,
    teams_summary,
    transactions,
)
from cubs_edge_lab.probe.report import render


class ProbeTests(unittest.TestCase):
    def test_limiter(self):
        now = [0.0]
        limiter = RateLimiter(
            lambda: now[0], lambda delay: now.__setitem__(0, now[0] + delay)
        )
        times = []
        for _ in range(4):
            limiter.wait()
            times.append(now[0])
        self.assertEqual(times, [0, 0.5, 1, 1.5])

    def test_client_and_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            response = Mock(status_code=200, content=b'{"sports": []}')
            session = Mock()
            session.get.return_value = response
            client = Client(root, session=session)
            self.assertEqual(client.get("sports"), {"sports": []})
            client.get("sports")
            self.assertEqual(session.get.call_count, 1)
            self.assertIn(
                "User-Agent", session.get.call_args.kwargs["headers"]
            )
            manifest = json.loads(
                (root / "research/raw_manifest.json").read_text()
            )
            self.assertEqual(len(manifest), 1)
            entry = manifest[0]
            raw = (root / entry["file"]).read_bytes()
            self.assertEqual(entry["sha256"], hashlib.sha256(raw).hexdigest())
            self.assertEqual(entry["byte_size"], len(raw))
            self.assertTrue(entry["retrieved_utc"].endswith("+00:00"))
            self.assertEqual(entry["params"], {})
            self.assertTrue(entry["endpoint"].endswith("/sports"))

    def test_failures(self):
        for status, body, error in [
            (500, b"{}", ApiError),
            (404, b"{}", ApiError),
            (200, b"no", MalformedResponseError),
            (200, b"[]", MalformedResponseError),
            (200, b"{", MalformedResponseError),
        ]:
            with self.subTest(status=status, body=body):
                with tempfile.TemporaryDirectory() as directory:
                    session = Mock()
                    session.get.return_value = Mock(
                        status_code=status, content=body
                    )
                    with self.assertRaises(error):
                        Client(Path(directory), session=session).get("sports")

    def test_parse(self):
        path = Path(__file__).resolve().parent / "fixtures/sample.json"
        fixture = json.loads(path.read_text())
        rows = transactions(fixture)
        self.assertEqual(len(rows), 1)
        summary = teams_summary(
            {
                "teams": [
                    {"id": 10, "league": {"name": "Synthetic League"}},
                    {"id": 10, "league": {}},
                ]
            }
        )
        self.assertEqual(summary["ids"], [10])
        names = [item["name"] for item in summary["league_counts"]]
        self.assertEqual(names, [None, "Synthetic League"])
        self.assertTrue(
            all(item["count"] == 1 for item in summary["league_counts"])
        )
        self.assertIsNone(rows[0]["from_team"])
        self.assertIsNone(rows[0]["type_desc"])
        self.assertEqual(transactions({"transactions": []}), [])
        with self.assertRaises(MalformedResponseError):
            transactions({})
        self.assertEqual(stats(fixture)[0]["sport_id"], 12)
        self.assertIsNone(stats({"stats": [{}]}))
        partial = {
            "stats": [
                {
                    "group": {"displayName": "hitting"},
                    "splits": [
                        {"sport": {"id": 11}, "stat": {"gamesPlayed": 1}}
                    ],
                },
                {"group": {"displayName": "pitching"}},
            ]
        }
        self.assertEqual(len(stats(partial)), 1)
        self.assertEqual(innings_outs("12.2"), 38)
        for value in ["12.3", "bad", "-1.0"]:
            with self.assertRaises(MalformedResponseError):
                innings_outs(value)

    def test_offline_report(self):
        report = render(None)
        self.assertIn("UNKNOWN", report)
        self.assertIn("live probe was not run", report)
        for line in report.splitlines():
            if line:
                self.assertTrue(
                    line.startswith(("FACT", "INFERENCE", "UNKNOWN"))
                )
        self.assertNotIn("FEASIBLE", report)


class IntegrationTests(unittest.TestCase):
    def test_probe_records_failure(self):
        from cubs_edge_lab.probe.probes import run

        client = Mock()
        client.get.side_effect = ApiError("unavailable")
        result = run(client)
        self.assertTrue(all("failure" in item for item in result))
        self.assertFalse(any("matched_events" in item for item in result))

    def test_cli_offline_and_failure(self):
        from cubs_edge_lab.probe.__main__ import main
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(main(["--offline", "--root", directory]), 0)
            self.assertIn(
                "UNKNOWN",
                (Path(directory) / "research/FEASIBILITY.md").read_text(),
            )
            with patch(
                "cubs_edge_lab.probe.__main__.run",
                side_effect=ApiError("failure"),
            ):
                self.assertEqual(main(["--root", directory]), 1)

    def test_report_punctuation(self):
        for line in render(None).splitlines():
            self.assertNotIn(" — ", line)
            self.assertNotIn(" – ", line)
            self.assertNotIn(" - ", line)

    def test_cache_corruption_and_offline_miss(self):
        with tempfile.TemporaryDirectory() as directory:
            client = Client(Path(directory), offline=True)
            with self.assertRaises(ApiError):
                client.get("sports")

    def test_replay_cache_miss_has_no_network_or_manifest_write(self):
        from cubs_edge_lab.probe.__main__ import main
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as directory:
            with patch(
                "requests.Session.get",
                side_effect=AssertionError("network forbidden"),
            ):
                self.assertEqual(main(["--replay", "--root", directory]), 1)
            research = Path(directory) / "research"
            self.assertFalse((research / "raw_manifest.json").exists())
            report = (research / "FEASIBILITY.md").read_text()
            self.assertIn("UNKNOWN:", report)

    def test_modified_cache_is_rejected_without_network(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            session = Mock()
            session.get.return_value = Mock(status_code=200, content=b"{}")
            Client(root, session=session).get("sports")
            entry = json.loads(
                (root / "research/raw_manifest.json").read_text()
            )[0]
            (root / entry["file"]).write_text('{"modified": true}')
            with self.assertRaisesRegex(ApiError, "matching manifest"):
                Client(root, session=session, offline=True).get("sports")
            self.assertEqual(session.get.call_count, 1)

    def test_probe_counts(self):
        from cubs_edge_lab.probe.probes import run

        path = Path(__file__).resolve().parent / "fixtures/sample.json"
        fixture = json.loads(path.read_text())
        client = Mock()
        client.get.side_effect = lambda endpoint, **params: (
            fixture if endpoint == "transactions" else {"sports": []}
        )
        result = run(client)
        windows = [r for r in result if "window_union_matches" in r]
        self.assertTrue(all(r["rows"] == 1 for r in windows))
        self.assertTrue(all(r["window_union_matches"] for r in windows))
        self.assertEqual(
            windows[0]["groups"][0]["examples"][0]["player_id"], 900000001
        )

    def test_malformed_transactions_are_not_zero(self):
        from cubs_edge_lab.probe.probes import run

        def get(endpoint, **params):
            if endpoint == "transactions":
                return {"transactions": "bad"}
            return {"sports": []}

        client = Mock()
        client.get.side_effect = get
        result = run(client)
        self.assertTrue(any("failure" in item for item in result))
        self.assertFalse(any("matched_events" in item for item in result))


class ValidationTests(unittest.TestCase):
    def test_returned_scope(self):
        from cubs_edge_lab.probe.parse import scoped_stats

        data = {
            "stats": [
                {
                    "splits": [
                        {
                            "season": "2023",
                            "sport": {"id": 11},
                            "stat": {"gamesPlayed": 2},
                        },
                        {"season": "2022", "sport": {"id": 1}, "stat": {}},
                    ]
                }
            ]
        }
        result = scoped_stats(data, 2023, 11)
        self.assertEqual(len(result["splits"]), 1)
        self.assertEqual(result["excluded_splits"], 1)


if __name__ == "__main__":
    unittest.main()
