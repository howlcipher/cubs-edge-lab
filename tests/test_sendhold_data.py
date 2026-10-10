"""Offline fixture checks for the frozen SENDHOLD data products."""

import json
from pathlib import Path
import unittest

from cubs_edge_lab.probe.sendhold_data import (
    LABELS,
    assign_label,
    assign_label_v3,
    batting_score_difference,
    build_data,
    make_report,
    _flatten_schedule,
    parse_leaderboard_values,
    pre_play_score,
    prior_or_fallback,
    render,
    run_expectancy,
)

ROOT = Path(__file__).resolve().parent.parent


def play(inning, half, outs, runners, away=0, home=0):
    return {
        "game_id": 1,
        "about": {"inning": inning, "halfInning": half},
        "count": {"outs": outs},
        "result": {"awayScore": away, "homeScore": home},
        "runners": runners,
    }


def runner(person, start, end, is_out=False, out_base=None):
    return {"details": {"runner": {"id": person}},
            "movement": {"originBase": start, "start": start, "end": end,
                         "isOut": is_out, "outBase": out_base}}


class SendholdDataTests(unittest.TestCase):
    def test_schedule_filters_season_and_deduplicates_game_pk(self):
        game = {"gamePk": 12, "season": 2025, "gameType": "R",
                "teams": {"home": {"team": {"id": 1}}}}
        duplicate = {**game, "teams": {"home": {"team": {"id": 2}}}}
        payload = {"dates": [
            {"games": [game, {**game, "gamePk": 13},
                       {**game, "gamePk": 14, "season": 2026},
                       {**game, "gamePk": 15, "gameType": "P"}]},
            {"games": [duplicate]},
        ]}
        selected = _flatten_schedule(payload, 2025)
        self.assertEqual([item["gamePk"] for item in selected], [12, 13])
        self.assertEqual(selected[0]["teams"]["home"]["team"]["id"], 2)

    def test_run_expectancy_hand_computed_and_walkoff_excluded(self):
        plays = [
            play(1, "top", 0, [runner(1, None, "1B")]),
            play(1, "top", 0, [runner(1, "1B", "score")], away=1),
            play(1, "top", 3, [runner(2, None, "1B", True, "1B")], away=1),
            play(1, "bottom", 1, [runner(3, "2B", "score")], home=1),
        ]
        result = run_expectancy(plays)
        states = {(row["bases_mask"], row["outs"]): row
                  for row in result["states"]}
        self.assertEqual(states[(0, 0)]["mean_runs"], 1)
        self.assertEqual(states[(1, 0)]["mean_runs"], 1)
        self.assertEqual(len(result["states"]), 24)
        self.assertEqual(result["complete_half_innings"], 1)
        self.assertEqual(result["excluded_half_innings"], 1)

    def test_batting_team_score_difference_top_and_bottom(self):
        top = play(1, "top", 0, [], away=5, home=3)
        bottom = play(1, "bottom", 0, [], away=5, home=4)
        self.assertEqual(batting_score_difference(top, "top", (4, 3)), 1)
        self.assertEqual(
            batting_score_difference(
                bottom, "bottom", (5, 3)), -2)

    def test_pre_play_score_uses_play_scoring_segments(self):
        top = play(1, "top", 0, [runner(8, "3B", "score")], away=5,
                   home=3)
        bottom = play(1, "bottom", 0, [runner(9, "2B", "score")], away=5,
                      home=4)
        self.assertEqual(pre_play_score(top), (4, 3))
        self.assertEqual(pre_play_score(bottom), (5, 3))
        self.assertIsNone(pre_play_score({"about": {"halfInning": "top"}}))

    def test_leaderboard_values_and_prior_season_fallback(self):
        parsed = parse_leaderboard_values(
            "player_id,sprint_speed\n12,28.4\n13,27.1\n", "sprint_speed")
        self.assertEqual(parsed, {12: 28.4, 13: 27.1})
        self.assertEqual(prior_or_fallback(12, parsed, {12: 30.0}),
                         (28.4, False))
        self.assertEqual(prior_or_fallback(13, {}, parsed), (27.1, True))

    def test_ordered_labels_count_fixture(self):
        cases = [
            ({"movement": {}, "segments": [
             runner(1, "2B", "home", True, "home")]}, "SENT_OUT"),
            ({"movement": {}, "segments": [
                runner(2, "2B", "3B", True, "3B"),
                runner(2, "3B", "score")]}, "OUT_ELSEWHERE"),
            ({"movement": {}, "segments": [
             runner(3, "2B", "score")]}, "SENT_SAFE"),
            ({"movement": {}, "segments": [
             runner(4, "2B", "3B"), runner(4, "3B", "score")]}, "AMBIGUOUS"),
            ({"movement": {}, "segments": [runner(5, "2B", "3B")]}, "HOLD"),
            ({"movement": {}, "segments": [runner(6, "2B", "2B")]}, "OTHER"),
        ]
        counts = {label: 0 for label in LABELS}
        for record, expected in cases:
            label = assign_label(record)
            self.assertEqual(label, expected)
            counts[label] += 1
        self.assertEqual(counts, {label: 1 for label in LABELS})

    def test_v3_requires_matching_later_segment_events(self):
        def segment(start, end, event):
            row = runner(20, start, end)
            row["details"] = {"event": event}
            return row
        same = {"segments": [segment("2B", "3B", "Single"),
                             segment("3B", "score", "Single")]}
        error = {"segments": [segment("2B", "3B", "Single"),
                              segment("3B", "score", "Error")]}
        mixed = {"segments": [segment("2B", "3B", "Single"),
                              segment("3B", "score", "Single"),
                              segment("score", "score", "Error")]}
        self.assertEqual(assign_label_v3(same, "Single"), "SENT_SAFE")
        self.assertEqual(assign_label_v3(error, "Single"), "AMBIGUOUS")
        self.assertEqual(assign_label_v3(mixed, "Single"), "AMBIGUOUS")
        self.assertEqual(assign_label(same), "AMBIGUOUS")
        out = {"segments": [segment("2B", "3B", "Double"),
                            {**segment("3B", "2B", "Runner Out"),
                             "movement": {"end": "2B", "isOut": True,
                                          "outBase": "2B"}}]}
        self.assertEqual(assign_label_v3(out, "Double"), "OUT_ELSEWHERE")

    def test_v3_double_runner_out_event_and_unchanged_non_scoring(self):
        def segment(start, end, event):
            row = runner(21, start, end)
            row["details"] = {"event": event}
            return row
        double_then_out = {"segments": [
            segment("1B", "3B", "Double"),
            segment("3B", "score", "Runner Out")]}
        self.assertEqual(assign_label_v3(double_then_out, "Double"),
                         "AMBIGUOUS")
        # Event names compare case-insensitively (result event vs type).
        single = {"segments": [segment("2B", "3B", "Single"),
                               segment("3B", "score", "Single")]}
        self.assertEqual(assign_label_v3(single, "single"), "SENT_SAFE")
        # Without a play event a later segment cannot be confirmed.
        self.assertEqual(assign_label_v3(single, None), "AMBIGUOUS")
        self.assertEqual(
            assign_label_v3({"segments": [segment("2B", "score", "Single")]},
                            None), "SENT_SAFE")
        # Runners who never score keep their v2 labels.
        for record in (
                {"segments": [segment("2B", "3B", "Single")]},
                {"segments": [segment("1B", "2B", "Double"),
                              segment("2B", "3B", "Error")]},
                {"segments": [segment("2B", "2B", "Single")]}):
            self.assertEqual(assign_label_v3(record, "Single"),
                             assign_label(record))

    def test_report_gives_both_label_versions_with_v3_primary(self):
        table = []
        for season in (2025, 2026):
            for label, v3 in (("AMBIGUOUS", "SENT_SAFE"),
                              ("SENT_OUT", "SENT_OUT"), ("HOLD", "HOLD")):
                table.append({
                    "season": season, "label": label, "label_v3": v3,
                    "sprint_speed": 27.0,
                    "sprint_speed_same_season_fallback": False,
                    "arm_strength": 80.0,
                    "arm_strength_same_season_fallback": False,
                    "fielder_outfielder": True})
        schedules = {2025: [1], 2026: [1]}
        report = make_report(table, schedules, {2025: 1, 2026: 1}, 7,
                             run_expectancy([]))
        facts = report["facts"]
        self.assertEqual(facts["primary_label_version"], "v3")
        for season in ("2025", "2026"):
            row = facts["seasons"][season]
            self.assertEqual(row["label_counts_v3"]["SENT_SAFE"], 1)
            self.assertEqual(row["label_counts_v3"]["AMBIGUOUS"], 0)
            self.assertEqual(row["label_counts_v2"]["SENT_SAFE"], 0)
            self.assertEqual(row["label_counts_v2"]["AMBIGUOUS"], 1)
        text = render(report)
        self.assertLess(text.index("v3 definition (primary)"),
                        text.index("v2 definition (pre-registered"))


@unittest.skipUnless((ROOT / "data/sendhold_retrieve_status.json").exists(),
                     "full cached data not present")
class CachedSendholdDataTests(unittest.TestCase):
    def test_report_reproduces_published_json(self):
        _, report = build_data(ROOT)
        published = json.loads(
            (ROOT / "research/sendhold_data.json").read_text())
        self.assertEqual(report, published)
        self.assertEqual(
            render(report),
            (ROOT / "research/SENDHOLD_DATA.md").read_text())


if __name__ == "__main__":
    unittest.main()
