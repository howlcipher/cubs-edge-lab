"""Offline tests for synthetic send/hold feed records."""

import json
from pathlib import Path
import unittest

from cubs_edge_lab.probe.sendhold import (
    classify,
    ended_third_no_score,
    extrapolate,
    group_runners,
    identify_opportunities,
    id_join_rate,
    outcome_counts,
    parse_leaderboard,
    reconciliation_lines,
    scored_any,
    sequence_counts,
    stable_sample,
)


def play(hit="single", start="2B", outs=0, end="score", is_out=False):
    return {
        "about": {"outs": outs, "gamePk": 5},
        "result": {"eventType": hit, "awayScore": 1},
        "runners": [
            {
                "details": {"runner": {"id": 42}},
                "movement": {"start": start, "end": end, "isOut": is_out},
            }
        ],
        "hitData": {"coordinates": {"x": 1, "y": 2}},
    }


class SendHoldTests(unittest.TestCase):
    def test_opportunity_filters_and_multirunner(self):
        self.assertEqual(len(identify_opportunities([play()])), 1)
        self.assertEqual(
            len(identify_opportunities([play("double", "1B")])), 1
        )
        self.assertEqual(identify_opportunities([play(outs=2)]), [])
        self.assertEqual(identify_opportunities([play(start="1B")]), [])
        self.assertEqual(identify_opportunities([play("walk")]), [])
        advanced = play()
        advanced["runners"][0]["movement"] = {
            "originBase": "1B",
            "start": "2B",
            "end": "3B",
            "isOut": False,
        }
        self.assertEqual(identify_opportunities([advanced]), [])
        value = play()
        value["runners"].append(
            {
                "details": {"runner": {"id": 43}},
                "movement": {"start": "2B", "end": "3B"},
            }
        )
        self.assertEqual(len(identify_opportunities([value])), 2)

    def test_outcome_classes(self):
        def outcome(end, is_out=False, out_base=None):
            return {
                "movement": {
                    "end": end, "isOut": is_out, "outBase": out_base
                }
            }

        self.assertEqual(classify(outcome("score")), "sent_safe")
        self.assertEqual(classify(outcome(None, True, "home")), "sent_out")
        self.assertEqual(classify(outcome(None, True, "4B")), "sent_out")
        self.assertEqual(classify(outcome("3B")), "held")
        self.assertEqual(classify(outcome("1B")), "other")
        outcomes = [
            outcome("score"), outcome(None, True, "home"),
            outcome(None, True, "4B"), outcome("3B"), outcome("1B"),
        ]
        self.assertEqual(sum(outcome_counts(outcomes).values()), len(outcomes))

    def test_deterministic_sample(self):
        games = [
            {"season": y, "gamePk": n}
            for y in (2025, 2026) for n in range(100)
        ]
        a = stable_sample(games)
        self.assertEqual(a, stable_sample(list(reversed(games))))
        self.assertNotEqual(a, stable_sample(games, seed=1))
        self.assertEqual([len(a[str(y)]) for y in (2025, 2026)], [50, 50])
        self.assertTrue(all(g in games for rows in a.values() for g in rows))

    def test_pilot_shaped_fixture_and_origin_base(self):
        fixture = Path(__file__).parent / "fixtures/sendhold/multirunner.json"
        play_record = json.loads(fixture.read_text())
        opportunities = identify_opportunities([play_record])
        self.assertEqual([r["runner_id"] for r in opportunities], [42])
        self.assertEqual(opportunities[0]["outs"], 1)
        self.assertEqual(opportunities[0]["fielder_id"], 300)
        changed = play()
        changed["playEvents"] = [
            {"details": {"runner": {"id": 42}, "endBase": "3B"}},
            {"details": {"eventType": "single"}},
        ]
        self.assertEqual(identify_opportunities([changed]), [])
        located = play()
        located.pop("hitData")
        located["playEvents"] = [
            {
                "details": {"eventType": "single"},
                "hitData": {
                    "coordinates": {"coordX": 10, "coordY": 20},
                    "location": "8",
                },
            }
        ]
        found = identify_opportunities([located])
        self.assertEqual(
            found[0]["location"]["coordinates"]["coordX"], 10
        )
        self.assertEqual(found[0]["location"]["zone"], "8")

    def test_segment_fixture_counts_whole_runner_movement(self):
        fixture = Path(__file__).parent / "fixtures/sendhold/segments.json"
        plays = json.loads(fixture.read_text())
        records = identify_opportunities(plays)
        self.assertEqual([row["runner_id"] for row in records], [1, 2, 3])
        self.assertEqual(classify(records[0]), "advanced_later")
        self.assertEqual(len(records[0]["segments"]), 2)
        self.assertEqual(classify(records[1]), "held")
        self.assertEqual(classify(records[2]), "sent_out")
        self.assertEqual(records[2]["outs"], 1)

    def test_later_segment_does_not_qualify_runner(self):
        record = {
            "about": {"outs": 0},
            "result": {"eventType": "double"},
            "runners": [
                {"details": {"runner": {"id": 9}},
                 "movement": {"originBase": "2B", "end": "3B"}},
                {"details": {"runner": {"id": 9}},
                 "movement": {"start": "1B", "end": "score"}},
            ],
        }
        self.assertEqual(identify_opportunities([record]), [])
        single_record = {
            "about": {"outs": 0},
            "result": {"eventType": "single"},
            "runners": [
                {"details": {"runner": {"id": 10}},
                 "movement": {"originBase": "1B", "end": "2B"}},
                {"details": {"runner": {"id": 10}},
                 "movement": {"start": "2B", "end": "3B"}},
            ],
        }
        self.assertEqual(identify_opportunities([single_record]), [])

    def test_non_adjacent_segments_keep_feed_order_and_count_once(self):
        def seg(runner, origin, end):
            return {"details": {"runner": {"id": runner}},
                    "movement": {"originBase": origin, "end": end,
                                 "isOut": False}}

        record = {
            "about": {"outs": 0},
            "result": {"eventType": "double"},
            "runners": [
                seg(1, "1B", "3B"), seg(2, "2B", "score"),
                seg(1, "3B", "score"),
                {"movement": {"originBase": "1B", "end": "2B"}},
            ],
        }
        found = identify_opportunities([record])
        self.assertEqual([r["runner_id"] for r in found], [1])
        ends = [s["movement"]["end"] for s in found[0]["segments"]]
        self.assertEqual(ends, ["3B", "score"])
        self.assertEqual(classify(found[0]), "advanced_later")
        self.assertTrue(scored_any(found[0]))
        self.assertFalse(ended_third_no_score(found[0]))
        self.assertEqual(sequence_counts(found), {"3B>score": 1})
        self.assertEqual(group_runners(record)[1], 1)

    def test_views_are_not_partitions(self):
        held = {"movement": {"end": "3B", "isOut": False}}
        self.assertTrue(ended_third_no_score(held))
        self.assertFalse(scored_any(held))

    def test_scored_any_and_ended_third_no_score_cases(self):
        scored_multi = {
            "segments": [
                {"movement": {"originBase": "1B", "end": "3B"}},
                {"movement": {"start": "3B", "end": "score", "isOut": False}},
            ]
        }
        self.assertTrue(scored_any(scored_multi))
        self.assertFalse(ended_third_no_score(scored_multi))

        held_multi = {
            "segments": [
                {"movement": {"originBase": "1B", "end": "2B"}},
                {"movement": {"start": "2B", "end": "3B", "isOut": False}},
            ]
        }
        self.assertFalse(scored_any(held_multi))
        self.assertTrue(ended_third_no_score(held_multi))

        out_at_home = {
            "segments": [
                {"movement": {"originBase": "2B", "end": "score",
                              "isOut": True}},
            ]
        }
        self.assertFalse(scored_any(out_at_home))
        self.assertFalse(ended_third_no_score(out_at_home))

    def test_render_reconciliation_from_json_keys(self):
        view = {"opportunities": 1, "scored_any": 1,
                "ended_at_3b_no_score": 0, "segment_end_sequences": {}}
        data = {
            "seasons": {"2025": {}},
            "examples": [],
            "count_reconciliation": {
                "controller_recount": {"2025": view},
                "first_segment_rule": {"2025": view},
                "any_segment_rule": {"2025": view},
                "unknown_cases": {},
            },
        }
        text = "\n".join(reconciliation_lines(data))
        self.assertIn("INFERENCE: The controller's qualifying totals", text)
        self.assertIn("INFERENCE: Scored and ended-at-3B counts also", text)
        self.assertIn("UNKNOWN: Cases outside the spec", text)
        self.assertNotIn(
            "evaluating qualifying segments only",
            text,
        )
        divergent_data = {
            "seasons": {"2025": {}},
            "examples": [],
            "count_reconciliation": {
                "controller_recount": {
                    "2025": {
                        "opportunities": 1,
                        "scored_any": 0,
                        "ended_at_3b_no_score": 1,
                    }
                },
                "first_segment_rule": {"2025": view},
                "any_segment_rule": {"2025": view},
                "unknown_cases": {},
            },
        }
        divergent_text = "\n".join(reconciliation_lines(divergent_data))
        self.assertIn(
            "UNKNOWN: Scored (any) and ended-at-3B counts differ",
            divergent_text,
        )
        self.assertNotIn("runner 669236", divergent_text)
        self.assertNotIn("runner 665862", divergent_text)

    def test_reconciliation_integrity_labels_and_no_hardcoded_runners(self):
        view = {
            "opportunities": 85,
            "scored_any": 40,
            "ended_at_3b_no_score": 44,
            "segment_end_sequences": {"3B": 44},
        }
        controller_view = {
            "opportunities": 88,
            "scored_any": 35,
            "ended_at_3b_no_score": 47,
        }
        data = {
            "seasons": {"2025": {}},
            "examples": [
                {
                    "season": 2025,
                    "game_id": 100,
                    "runner_id": 999,
                    "hit": "single",
                    "contact_bases_by_segment": ["1B", "2B"],
                }
            ],
            "count_reconciliation": {
                "controller_recount": {"2025": controller_view},
                "first_segment_rule": {"2025": view},
                "any_segment_rule": {"2025": {**view, "opportunities": 88}},
                "unknown_cases": {},
            },
        }
        lines = reconciliation_lines(data)
        for line in lines:
            if not line or line.startswith("##"):
                continue
            self.assertTrue(
                line.startswith(("FACT:", "INFERENCE:", "UNKNOWN:")),
                f"Line missing valid integrity label: {line}",
            )
        text = "\n".join(lines)
        self.assertNotIn("evaluating qualifying segments only", text)
        self.assertIn("runner 999", text)
        self.assertNotIn("669236", text)
        self.assertNotIn("665862", text)

    def test_outcome_counts_cover_opportunities(self):
        records = identify_opportunities(
            json.loads(
                (Path(__file__).parent / "fixtures/sendhold/segments.json")
                .read_text()
            )
        )
        self.assertEqual(sum(outcome_counts(records).values()), len(records))

    def test_count_outs_precedes_play_runner_outs(self):
        record = {
            "count": {"outs": 2}, "about": {"outs": 0},
            "result": {"eventType": "single"},
            "runners": [{"details": {"runner": {"id": 1}},
                         "movement": {"originBase": "2B", "isOut": True,
                                      "outBase": "3B"}}],
        }
        self.assertEqual(identify_opportunities([record])[0]["outs"], 1)

    def test_post_play_outs_and_extrapolation(self):
        record = {
            "count": {"outs": 2},
            "result": {
                "eventType": "single", "awayScore": 0, "homeScore": 0
            },
            "runners": [
                {
                    "details": {"runner": {"id": 1}},
                    "movement": {
                        "originBase": "2B",
                        "end": "3B",
                        "isOut": True,
                        "outBase": "3B",
                    },
                }
            ],
        }
        self.assertEqual(len(identify_opportunities([record])), 1)
        record["runners"][0]["movement"]["isOut"] = False
        self.assertEqual(identify_opportunities([record]), [])
        scaled = extrapolate([2] * 50, 100)
        self.assertEqual(scaled["estimate"], 200)
        self.assertEqual(scaled["interval_95"], [200, 200])

    def test_ids_and_bom(self):
        self.assertEqual(
            parse_leaderboard("\ufeffplayer_id,name\n42,A\n"), {42}
        )
        with self.assertRaises(ValueError):
            parse_leaderboard("id,name\nx,A\n")
        self.assertEqual(
            parse_leaderboard(
                "player_id,primary_position\n42,7\n42,8\n43,3\n",
                positions={"7", "8"},
            ),
            {42},
        )
        self.assertEqual(
            id_join_rate(["42", 43, None, 42], {42}),
            {"matched": 1, "total": 2, "rate": 0.5},
        )

    def test_analyze_offline(self):
        import tempfile
        from cubs_edge_lab.probe.client import atomic_json
        from cubs_edge_lab.probe.sendhold import analyze

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data").mkdir()
            (root / "research").mkdir()
            atomic_json(
                root / "data/sendhold_sampling.json", {"2025": [], "2026": []}
            )
            atomic_json(root / "data/sendhold_schedule.json", [])
            atomic_json(
                root / "data/sendhold_leaderboards.json",
                {
                    "2025": {"sprint_speed": [], "arm_strength": []},
                    "2026": {"sprint_speed": [], "arm_strength": []},
                },
            )
            atomic_json(
                root / "data/sendhold_request_ledger.json", {"count": 107}
            )
            data = analyze(root)
            self.assertEqual(data["new_requests_used"], 107)
            self.assertTrue(
                (root / "research/sendhold_feasibility.json").exists()
            )
            self.assertTrue(
                (root / "research/SENDHOLD_FEASIBILITY.md").exists()
            )

    def test_render_table_and_markdown_structure(self):
        from cubs_edge_lab.probe.sendhold import render

        sample_data = {
            "verdict": "PARTIAL",
            "verdict_reason": "Test reason",
            "location_statement": "FACT: Location statement",
            "seed": 1,
            "schedule_hash": "hash",
            "full_retrieval_request_estimate": 10,
            "new_requests_used": 0,
            "ceiling": 150,
            "examples": [],
            "seasons": {
                "2025": {
                    "season": 2025,
                    "games": 1,
                    "opportunities": 1,
                    "scored_any": 1,
                    "advanced_later": 1,
                    "sent_safe": 0,
                    "sent_out": 0,
                    "ended_at_3b_no_score": 0,
                    "out_elsewhere": 0,
                    "other": 0,
                    "identification_rates": {
                        "runner_id": 1.0,
                        "fielder_id": 1.0,
                        "hit": 1.0,
                        "location": 1.0,
                        "outs": 1.0,
                        "score": 1.0,
                    },
                    "speed_join": {"matched": 1, "total": 1, "rate": 1.0},
                    "arm_join": {"matched": 1, "total": 1, "rate": 1.0},
                    "outcome_rates": {
                        "sent_safe": 0.0,
                        "advanced_later": 1.0,
                        "sent_out": 0.0,
                        "held": 0.0,
                        "out_elsewhere": 0.0,
                        "other": 0.0,
                    },
                    "extrapolation": {
                        "estimate": 100,
                        "interval_95": [90, 110],
                        "full_retrieval_requests_estimate": 100,
                    },
                }
            },
        }
        text = render(sample_data)
        self.assertIn("# Third-base send/hold feasibility", text)
        self.assertIn(
            "FACT: Per-season counts from the deduplicated cached sample.\n\n"
            "| season |",
            text,
        )


if __name__ == "__main__":
    unittest.main()
