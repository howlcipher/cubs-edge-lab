"""Offline fixture checks for the frozen SENDHOLD data products."""

import json
from pathlib import Path
import unittest

from cubs_edge_lab.probe.sendhold_data import (
    LABELS,
    assign_label,
    batting_score_difference,
    build_data,
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
