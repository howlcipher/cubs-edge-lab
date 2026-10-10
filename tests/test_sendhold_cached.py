"""Consistency of the published report with the cached sample, when present."""

import json
from pathlib import Path
import unittest

from cubs_edge_lab.probe.sendhold import build_report, render

ROOT = Path(__file__).resolve().parent.parent
CACHED = (ROOT / "data/sendhold_sampling.json").exists()


@unittest.skipUnless(CACHED, "cached sample (data/) not present")
class CachedReportTests(unittest.TestCase):
    def test_published_report_matches_cached_data(self):
        published = json.loads(
            (ROOT / "research/sendhold_feasibility.json").read_text()
        )
        computed = json.loads(json.dumps(build_report(ROOT)))
        self.assertEqual(published, computed)
        self.assertEqual(
            (ROOT / "research/SENDHOLD_FEASIBILITY.md").read_text(),
            render(computed),
        )
        self.assertLessEqual(len(computed["examples"]), 5)

    def test_every_runner_has_one_class_and_no_double_count(self):
        computed = build_report(ROOT)
        for row in computed["seasons"].values():
            self.assertEqual(
                row["sent_safe"] + row["advanced_later"] + row["sent_out"]
                + row["held"] + row["out_elsewhere"] + row["other"],
                row["opportunities"],
            )
            self.assertEqual(
                row["scored_any"], row["sent_safe"] + row["advanced_later"]
            )
            self.assertEqual(row["ended_at_3b_no_score"], row["held"])


if __name__ == "__main__":
    unittest.main()
