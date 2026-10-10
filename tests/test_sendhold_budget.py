"""The send/hold network budget has no network dependency."""

import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock

import requests

from cubs_edge_lab.probe.client import Client, RequestCeilingError
from cubs_edge_lab.probe.sendhold import main


class BudgetTests(unittest.TestCase):
    def test_persistent_ceiling_and_failures_count(self):
        with tempfile.TemporaryDirectory() as temp:
            session = Mock()
            session.get.return_value = Mock(content=b"{}", status_code=200)
            client = Client(
                temp, session=session, ceiling=150, request_cap=200
            )
            client.ledger["count"] = 149
            from cubs_edge_lab.probe.client import atomic_json

            atomic_json(client.ledger_path, client.ledger)
            client.get("x")
            self.assertEqual(session.get.call_count, 1)
            second = Client(
                temp, session=session, ceiling=150, request_cap=200
            )
            with self.assertRaises(RequestCeilingError):
                second.get("y")
            self.assertEqual(session.get.call_count, 1)

    def test_150th_succeeds_151st_is_not_sent(self):
        with tempfile.TemporaryDirectory() as temp:
            session = Mock()
            session.get.return_value = Mock(content=b"{}", status_code=200)
            client = Client(
                temp, session=session, ceiling=150, request_cap=150
            )
            client.limiter.wait = Mock()
            for index in range(150):
                client.get("game/" + str(index))
            with self.assertRaises(RequestCeilingError):
                client.get("game/151")
            self.assertEqual(session.get.call_count, 150)

    def test_cached_hit_is_free(self):
        with tempfile.TemporaryDirectory() as temp:
            session = Mock()
            session.get.return_value = Mock(content=b"{}", status_code=200)
            first = Client(temp, session=session, ceiling=150)
            first.get("x")
            second = Client(temp, session=session, ceiling=150)
            second.get("x")
            self.assertEqual(session.get.call_count, 1)

    def test_http_and_exception_count(self):
        for response in (
            Mock(content=b"{}", status_code=500),
            requests.RequestException("failed"),
        ):
            with (
                self.subTest(response=response),
                tempfile.TemporaryDirectory() as temp,
            ):
                session = Mock()
                if isinstance(response, Exception):
                    session.get.side_effect = response
                else:
                    session.get.return_value = response
                client = Client(temp, session=session, ceiling=150)
                with self.assertRaises(Exception):
                    client.get("x")
                self.assertEqual(client.ledger["count"], 1)

    def test_ceiling_and_host(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                Client(temp, ceiling=151)
            with self.assertRaises(SystemExit):
                main(["--ceiling", "151"])
            client = Client(temp, session=Mock(), ceiling=150)
            with self.assertRaises(Exception):
                client.get_url("https://evil.example/data")

    def test_redirect_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            session = Mock()
            session.get.return_value = Mock(
                content=b"",
                status_code=302,
                headers={"Location": "https://evil.example"},
            )
            client = Client(temp, session=session, ceiling=150)
            client.limiter.wait = Mock()
            with self.assertRaises(Exception):
                client.get("redirect")
            self.assertFalse(session.get.call_args.kwargs["allow_redirects"])

    def test_missing_ledger_uses_manifest_count(self):
        with tempfile.TemporaryDirectory() as temp:
            from cubs_edge_lab.probe.client import atomic_json

            entries = [
                {
                    "endpoint": (
                        "https://statsapi.mlb.com/api/v1/game/7/playByPlay"
                    ),
                    "params": {},
                },
                {
                    "endpoint": "https://statsapi.mlb.com/api/v1/schedule",
                    "params": {"season": 2025, "gameType": "R"},
                },
            ]
            Path(temp, "research").mkdir()
            atomic_json(
                Path(temp, "research/raw_manifest.json"), entries
            )
            client = Client(temp, session=Mock(), ceiling=150)
            self.assertEqual(client.ledger["count"], 2)


if __name__ == "__main__":
    unittest.main()
