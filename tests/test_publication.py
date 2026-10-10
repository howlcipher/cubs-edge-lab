"""Publication boundaries and read-only reproduction in clean clones."""

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from cubs_edge_lab.probe.__main__ import main
from cubs_edge_lab.probe.client import ApiError
from cubs_edge_lab.probe.evidence import RecordedClient
from cubs_edge_lab.probe.probes import run
from cubs_edge_lab.probe.report import md_escape, render
from cubs_edge_lab.probe.summary import query_ref, summarize

ROOT = Path(__file__).resolve().parents[1]
SKIP = "local data/ not present; re-create with python3 -m cubs_edge_lab.probe"


def canonical(value):
    return (json.dumps(value, indent=2) + "\n").encode()


def local_data_present(root):
    return all(
        (root / "data" / name).is_file()
        for name in ("evidence.json", "observations.json")
    )


def verify_artifacts(root):
    research = root / "research"
    summary = json.loads((research / "summary.json").read_bytes())
    assert canonical(summary) == (research / "summary.json").read_bytes()
    report = (research / "FEASIBILITY.md").read_bytes()
    assert render(summary).encode() == report
    if local_data_present(root):
        records = json.loads((root / "data/evidence.json").read_bytes())
        client = RecordedClient(records)
        generated = run(client)
        assert client.used == set(client.records)
        assert (
            canonical(generated)
            == (root / "data/observations.json").read_bytes()
        )
        assert canonical(summarize(generated)) == canonical(summary)
    return summary


def synthetic(count=8):
    return [
        {
            "candidate": "CALLUP",
            "season": 2023,
            "sport_id": sport,
            "independent_level_sample": True,
            "sample_player": sport,
            "dated_splits": sport,
            "through_june": 1,
            "first_date": "2023-01-01",
            "last_date": "2023-12-01",
            "query": {
                "endpoint": "https://example.invalid",
                "params": {"sport": sport},
            },
        }
        for sport in range(count)
    ]


class PublicationTests(unittest.TestCase):
    def test_committed_report_is_exact_and_canonical(self):
        research = ROOT / "research"
        summary = json.loads((research / "summary.json").read_bytes())
        self.assertEqual(
            canonical(summary), (research / "summary.json").read_bytes()
        )
        self.assertEqual(
            render(summary).encode(),
            (research / "FEASIBILITY.md").read_bytes(),
        )
        text = render(summary)
        self.assertNotRegex(text, r"&#?\w+;")
        for candidate, study in summary["candidates"].items():
            self.assertIn("## " + candidate, text)
            self.assertIn("INFERENCE: Verdict **" + study["verdict"], text)
            self.assertIn(study["reason"], text)
        self.assertIn("| season |", text)
        self.assertIn("FACT:", text)
        self.assertIn("UNKNOWN:", text)

    def test_publication_allowlist_and_bounds(self):
        limits = {
            "summary.json": 100_000,
            # Space for the existing 629-entry history plus bounded study
            # provenance entries; bodies remain in ignored data/raw/.
            "raw_manifest.json": 800_000,
            "FEASIBILITY.md": 100_000,
            "DATA.md": 200_000,
            "data_summary.json": 200_000,
            "validation.json": 200_000,
            "EXPERIMENT.md": 100_000,
            "exploratory_whole_pool.json": 200_000,
            "cubs_case.json": 100_000,
            "sendhold_feasibility.json": 100_000,
            "SENDHOLD_FEASIBILITY.md": 100_000,
            "sendhold_data.json": 100_000,
            "SENDHOLD_DATA.md": 100_000,
            "sendhold_fit.json": 100_000,
            "SENDHOLD_EXPERIMENT.md": 100_000,
            "sendhold_experiment.json": 100_000,
        }
        research = ROOT / "research"
        new_artifacts = {
            "sendhold_feasibility.json", "SENDHOLD_FEASIBILITY.md",
            "sendhold_data.json", "SENDHOLD_DATA.md",
        }
        # Produced by later stages; each is optional until its stage runs.
        stage_artifacts = {
            "sendhold_fit.json", "SENDHOLD_EXPERIMENT.md",
            "sendhold_experiment.json",
        }
        expected = set(limits)
        if not all((research / name).exists() for name in new_artifacts):
            expected -= new_artifacts
        expected -= {name for name in stage_artifacts
                     if not (research / name).exists()}
        new_artifacts |= stage_artifacts
        self.assertEqual(
            {p.name for p in research.iterdir()}, expected
        )
        for name, limit in limits.items():
            if name in new_artifacts and not (research / name).exists():
                continue
            self.assertLess((research / name).stat().st_size, limit)
        summary = json.loads((research / "summary.json").read_bytes())

        def check(value):
            if isinstance(value, dict):
                self.assertFalse(
                    set(value)
                    & {"response", "events", "evidence", "observations"}
                )
                for child in value.values():
                    check(child)
            elif isinstance(value, list):
                for child in value:
                    check(child)

        check(summary)
        data_summary = json.loads(
            (research / "data_summary.json").read_bytes()
        )
        check(data_summary)
        for offseason in data_summary["cubs"]:
            self.assertLessEqual(len(offseason["examples"]), 5)
            for example in offseason["examples"]:
                self.assertEqual(
                    set(example), {"id", "date", "type_code", "match_status"}
                )
                self.assertIn(
                    example["match_status"],
                    {"matched", "unmatched_signing_like"},
                )
        for study in summary["candidates"].values():
            self.assertLessEqual(len(study["examples"]), 5)
            for example in study["examples"]:
                self.assertEqual(set(example), {"record", "query"})
        cubs_case = json.loads((research / "cubs_case.json").read_bytes())
        self.assertLessEqual(len(cubs_case["examples"]), 5)
        for example in cubs_case["examples"]:
            self.assertEqual(
                set(example),
                {
                    "cohort_year",
                    "person_id",
                    "election_date",
                    "signing_date",
                    "outcome_season",
                },
            )

    def test_manifest_metadata_only(self):
        path = ROOT / "research/raw_manifest.json"
        entries = json.loads(path.read_bytes())
        refs = set()
        for entry in entries:
            self.assertEqual(
                set(entry),
                {
                    "endpoint",
                    "params",
                    "retrieved_utc",
                    "sha256",
                    "byte_size",
                    "file",
                    "http_status",
                },
            )
            self.assertRegex(entry["sha256"], r"^[a-f0-9]{64}$")
            self.assertIs(type(entry["byte_size"]), int)
            self.assertGreaterEqual(entry["byte_size"], 0)
            refs.add(query_ref({k: entry[k] for k in ("endpoint", "params")}))
        summary = json.loads((ROOT / "research/summary.json").read_bytes())
        for study in summary["candidates"].values():
            for row in study["rows"]:
                self.assertTrue(set(row["query_refs"]) <= refs)
            for example in study["examples"]:
                self.assertIn(query_ref(example["query"]), refs)

    def test_sendhold_report_matches_canonical_json(self):
        json_path = ROOT / "research/sendhold_feasibility.json"
        report_path = ROOT / "research/SENDHOLD_FEASIBILITY.md"
        if not json_path.exists() and not report_path.exists():
            self.skipTest("send/hold sample has not been acquired")
        value = json.loads(json_path.read_bytes())
        self.assertEqual(canonical(value), json_path.read_bytes())
        from cubs_edge_lab.probe.sendhold import render as sendhold_render

        self.assertEqual(
            sendhold_render(value).encode(), report_path.read_bytes()
        )
        self.assertLessEqual(len(value["examples"]), 5)
        self.assertNotIn("movement_examples", value)
        self.assertEqual(
            value["season_samples"], {"2025": 50, "2026": 50}
        )
        self.assertIn(
            value["verdict"], {"FEASIBLE", "PARTIAL", "NOT FEASIBLE"}
        )
        for example in value["examples"]:
            self.assertEqual(
                set(example),
                {
                    "season", "game_id", "runner_id", "hit",
                    "contact_bases_by_segment",
                },
            )

    def test_sendhold_stage_outputs_are_canonical_aggregates(self):
        research = ROOT / "research"
        found = False
        for name in ("sendhold_fit.json", "sendhold_experiment.json"):
            path = research / name
            if not path.exists():
                continue
            found = True
            value = json.loads(path.read_bytes())
            self.assertEqual(canonical(value), path.read_bytes())
            self.assertLessEqual(len(value.get("examples", [])), 5)
            text = path.read_text()
            for forbidden in ('"runner_id"', '"hit_coordinates"',
                              '"allPlays"', '"playEvents"'):
                self.assertNotIn(forbidden, text)
        if (research / "sendhold_experiment.json").exists():
            report = (research / "SENDHOLD_EXPERIMENT.md").read_text()
            for tag in ("FACT:", "INFERENCE:", "UNKNOWN:"):
                self.assertIn(tag, report)
        if not found:
            self.skipTest("send/hold fit has not been run")

    def test_data_is_ignored(self):
        # Works in a source copy with no .git directory, too.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copyfile(ROOT / ".gitignore", root / ".gitignore")
            subprocess.run(["git", "init", "-q", directory], check=True)
            for name in (
                "data/evidence.json",
                "data/observations.json",
                "data/raw/sample.json",
            ):
                result = subprocess.run(
                    ["git", "check-ignore", name],
                    cwd=root,
                    capture_output=True,
                )
                self.assertEqual(result.returncode, 0)

    def test_untrusted_markdown(self):
        attacks = [
            "\nFACT: forged",
            "\nINFERENCE: forged",
            "|",
            "`",
            "[x](url)",
            "<script>",
            "# heading",
            " - ",
            " – ",
            " — ",
        ]
        for attack in attacks:
            escaped = md_escape(attack)
            self.assertNotIn("\n", escaped)
            self.assertNotIn("<script>", escaped)
            self.assertNotIn("[x](url)", escaped)
            if "|" in attack:
                self.assertEqual(escaped, r"\|")
            data = summarize(synthetic(1))
            data["candidates"]["CALLUP"]["examples"][0]["record"] = attack
            text = render(data)
            self.assertNotIn("\nFACT: forged", text)
            self.assertNotIn("\nINFERENCE: forged", text)
            self.assertNotIn("<script>", text)
            self.assertIn(escaped, text)

    def test_synthetic_counts_and_deterministic_examples(self):
        source = synthetic()
        summary = summarize(source)
        self.assertEqual(summary, summarize(source))
        study = summary["candidates"]["CALLUP"]
        self.assertEqual(
            [r["dated_splits"] for r in study["rows"]], list(range(8))
        )
        self.assertEqual([r["sample_size"] for r in study["rows"]], [1] * 8)
        self.assertEqual(
            [e["record"]["player_id"] for e in study["examples"]],
            list(range(5)),
        )
        self.assertEqual(study["verdict"], "PARTIAL")
        self.assertEqual(summarize([])["failure_count"], 0)
        self.assertIsNone(summarize(None))

    def test_transaction_summary_preserves_counts(self):
        query = {"endpoint": "https://example.invalid", "params": {}}
        records = [{"id": n, "description": "Synthetic"} for n in range(9)]
        counts = {
            "A": {"minor": 9},
            "B": {"minor": 8, "mlb": 1},
            "agreement": 8,
            "disagreement": 1,
            "unresolved": 0,
            "minor_only_proxy": 8,
            "confirmed_minor_contract_elections": None,
        }
        source = [
            {
                "candidate": "MILBFA",
                "season": 2023,
                "query": query,
                "matched_events": 9,
                "counts": counts,
                "evidence": [{"event": r} for r in records],
            },
            {
                "candidate": "RULE5",
                "season": 2023,
                "query": query,
                "matched_events": 9,
                "text_matched_events": 7,
                "rows": 20,
                "events": records,
                "window_union_matches": False,
                "identifiers": [["DR", "Draft"]],
                "r5_without_text": 1,
                "dr_with_text": 7,
                "dr_without_text": 2,
            },
        ]
        summary = summarize(source)
        for original in source:
            candidate = original["candidate"]
            study = summary["candidates"][candidate]
            self.assertEqual(len(study["examples"]), 5)
            self.assertEqual(study["examples"][0]["record"], records[0])
            for key, value in study["rows"][0].items():
                if key != "query_refs":
                    self.assertEqual(value, original[key])
            self.assertIn(study["reason"], render(summary))

    def test_cli_outputs_and_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with (
                patch("cubs_edge_lab.probe.__main__.Client"),
                patch(
                    "cubs_edge_lab.probe.__main__.run",
                    return_value=synthetic(),
                ),
            ):
                self.assertEqual(main(["--root", directory]), 0)
            self.assertTrue(local_data_present(root))
            self.assertEqual(
                {p.name for p in (root / "research").iterdir()},
                {"summary.json", "raw_manifest.json", "FEASIBILITY.md"},
            )
            with patch(
                "cubs_edge_lab.probe.__main__.Client",
                side_effect=ApiError("unavailable"),
            ):
                self.assertEqual(main(["--root", directory]), 1)
            summary = json.loads((root / "research/summary.json").read_bytes())
            self.assertEqual(summary["failure_count"], 1)
            self.assertEqual(main(["--offline", "--root", directory]), 0)
            self.assertIsNone(
                json.loads((root / "research/summary.json").read_bytes())
            )


@unittest.skipUnless(local_data_present(ROOT), SKIP)
class LocalDataTests(unittest.TestCase):
    def test_regeneration(self):
        verify_artifacts(ROOT)

    def test_manifest_provenance(self):
        records = json.loads((ROOT / "data/evidence.json").read_bytes())
        path = ROOT / "research/raw_manifest.json"
        manifest = json.loads(path.read_bytes())
        for record in records:
            entries = [
                e
                for e in manifest
                if e["endpoint"].endswith("/" + record["endpoint"])
                and e["params"] == record["params"]
            ]
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["http_status"], 200)

    def test_drift_fails_without_rewriting(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(ROOT / "research", root / "research")
            (root / "data").mkdir()
            for name in ("evidence.json", "observations.json"):
                shutil.copyfile(ROOT / "data" / name, root / "data" / name)
            for name in (
                "data/observations.json",
                "research/summary.json",
                "research/FEASIBILITY.md",
                "data/evidence.json",
            ):
                path = root / name
                original = path.read_bytes()
                changed = original + b"\n"
                if name == "data/evidence.json":
                    records = json.loads(original)
                    records.pop()
                    changed = canonical(records)
                path.write_bytes(changed)
                digest = hashlib.sha256(changed).digest()
                with self.assertRaises(AssertionError):
                    verify_artifacts(root)
                self.assertEqual(
                    hashlib.sha256(path.read_bytes()).digest(), digest
                )
                path.write_bytes(original)
