"""Small, bounded retrospective third-base decision feasibility study."""

import argparse
import csv
import hashlib
import io
import json
import random
import statistics
from pathlib import Path

from .client import Client, atomic_json

SEED = 20261009
CEILING = 150
SAVANT = "https://baseballsavant.mlb.com/leaderboard/"
# Acceptance targets from the campaign controller's independent audit.
CONTROLLER_RECOUNT = {
    "2025": {
        "opportunities": 88, "scored_any": 35, "ended_at_3b_no_score": 47,
    },
    "2026": {
        "opportunities": 95, "scored_any": 35, "ended_at_3b_no_score": 58,
    },
}


def canonical(value):
    return json.dumps(value, indent=2) + "\n"


def stable_sample(schedule, seed=SEED, per_season=50):
    result = {}
    for season in (2025, 2026):
        games = sorted(
            (g for g in schedule if int(g["season"]) == season),
            key=lambda g: int(g["gamePk"]),
        )
        random.Random(seed + season).shuffle(games)
        result[str(season)] = games[:per_season]
    return result


def pre_play_outs(play):
    """Outs before the play.

    ``about.outs`` is the pre-play value in the synthetic fixtures. Live
    play-by-play records ``count.outs`` after the play, so recorded runner
    outs are removed from that total.
    """
    count = play.get("count") or {}
    if "outs" not in count:
        return int((play.get("about") or {}).get("outs", 0))
    after = int(count["outs"])
    recorded = sum(
        bool((runner.get("movement") or {}).get("isOut"))
        for runner in play.get("runners") or []
    )
    return max(0, after - recorded)


def base_at_contact(play, runner, hit):
    """Base when the ball was hit.

    ``movement.originBase`` is the base at the start of the play.
    ``movement.start`` is the base before the runner's final segment, so a
    runner who began on first and reached third has start ``2B``. Events
    that name this runner and occur before the batted ball can move him.
    """
    movement = runner.get("movement") or {}
    base = movement.get("originBase") or movement.get("start")
    runner_id = ((runner.get("details") or {}).get("runner") or {}).get("id")
    for event in play.get("playEvents") or []:
        details = event.get("details") or {}
        if (
            details.get("isInPlay")
            or event.get("hitData")
            or details.get("eventType") == hit
        ):
            break
        moved = details.get("runner") or {}
        if moved.get("id") == runner_id and details.get("endBase"):
            base = details["endBase"]
    return base


def batted_ball_location(play, hit=None):
    """Coordinates or zone from the hit event, else the play-level hitData."""
    sources = []
    for event in play.get("playEvents") or []:
        details = event.get("details") or {}
        if event.get("hitData"):
            sources.append(event["hitData"])
        elif details.get("hitData"):
            sources.append(details["hitData"])
    if play.get("hitData"):
        sources.append(play["hitData"])
    for hit_data in sources:
        coordinates = hit_data.get("coordinates")
        zone = hit_data.get("location")
        if coordinates or zone is not None:
            found = {}
            if coordinates:
                found["coordinates"] = coordinates
            if zone is not None:
                found["zone"] = zone
            return found
    return None


def fielding_outfielder(play):
    for runner in play.get("runners") or []:
        for credit in runner.get("credits") or []:
            position = (credit.get("position") or {}).get("code")
            if (
                credit.get("credit") == "f_fielded_ball"
                and position in {"7", "8", "9"}
            ):
                return (credit.get("player") or {}).get("id")
    return None


SCORE_ENDS = {"score", "home", "4B"}


def group_runners(play):
    """Group runner segments by runner id in feed order.

    Returns the grouped segments and the count of segments lacking an id.
    """
    grouped = {}
    missing = 0
    for segment in play.get("runners") or []:
        person = (segment.get("details") or {}).get("runner") or {}
        if person.get("id") is None:
            missing += 1
        else:
            grouped.setdefault(person["id"], []).append(segment)
    return grouped, missing


def scored_any(record):
    """True when any segment of the runner's movement scores safely."""
    moves = [
        segment.get("movement") or {} for segment in record.get("segments", [])
    ] or [record.get("movement", {})]
    return any(
        move.get("end") in SCORE_ENDS and move.get("isOut") is not True
        for move in moves
    )


def ended_third_no_score(record):
    """True when a segment ends at third and no segment scores safely."""
    moves = [
        segment.get("movement") or {} for segment in record.get("segments", [])
    ] or [record.get("movement", {})]
    return (
        any(move.get("end") == "3B" for move in moves)
        and not scored_any(record)
    )


def identify_opportunities(plays, rule="first"):
    """Return runner opportunities inferred from recorded event/base fields.

    One record per runner per play. ``rule`` is ``first`` (the runner's
    first segment sets the base at contact) or ``any`` (diagnostic only:
    any segment may qualify the runner).
    """
    output = []
    for play in plays:
        about = play.get("about") or {}
        outs = pre_play_outs(play)
        if outs >= 2:
            continue
        result = play.get("result") or {}
        kind = result.get("eventType", "")
        hit = (
            "single" if kind == "single"
            else "double" if kind == "double" else None
        )
        if not hit:
            continue
        threshold = "2B" if hit == "single" else "1B"
        fielder_id = fielding_outfielder(play)
        away = result.get("awayScore")
        home = result.get("homeScore")
        grouped, _ = group_runners(play)
        for runner_id, segments in grouped.items():
            candidates = segments if rule == "any" else segments[:1]
            if not any(
                base_at_contact(play, segment, hit) == threshold
                for segment in candidates
            ):
                continue
            movement = dict(segments[-1].get("movement") or {})
            first_movement = segments[0].get("movement") or {}
            movement["originBase"] = (
                first_movement.get("originBase")
                or first_movement.get("start")
            )
            movement["isOut"] = any(
                (segment.get("movement") or {}).get("isOut") is True
                for segment in segments
            )
            movement["outBase"] = next(
                ((segment.get("movement") or {}).get("outBase")
                 for segment in segments
                 if (segment.get("movement") or {}).get("isOut") is True),
                movement.get("outBase"),
            )
            movement["stopped_at_3b"] = any(
                (segment.get("movement") or {}).get("end") == "3B"
                for segment in segments[:-1]
            )
            output.append(
                {
                    "runner_id": runner_id,
                    "hit": hit,
                    "outs": outs,
                    "movement": movement,
                    "segments": segments,
                    "fielder_id": fielder_id,
                    "location": batted_ball_location(play, hit),
                    "score": (
                        {"away": away, "home": home}
                        if away is not None and home is not None
                        else None
                    ),
                    "game_id": about.get("gamePk"),
                }
            )
    return output


def classify(record):
    movement = record.get("movement", {})
    segments = record.get("segments")
    if segments:
        moves = [segment.get("movement") or {} for segment in segments]
        if any(
            move.get("isOut") is True
            and (move.get("end") in {"score", "home", "4B"}
                 or move.get("outBase") in {"home", "HOME", "4B"})
            for move in moves
        ):
            return "sent_out"
        if any(move.get("end") == "3B" for move in moves[:-1]) and any(
            move.get("end") in {"score", "home", "4B"}
            and move.get("isOut") is not True for move in moves[1:]
        ):
            return "advanced_later"
        if any(
            move.get("end") in {"score", "home", "4B"}
            and move.get("isOut") is not True for move in moves
        ):
            return "sent_safe"
        if movement.get("end") == "3B" and not movement.get("isOut"):
            return "held"
        if movement.get("isOut"):
            return "out_elsewhere"
        return "other"
    end = movement.get("end")
    is_out = movement.get("isOut")
    out_base = movement.get("outBase")
    if is_out is True and (
        end in {"score", "home", "4B"} or out_base in {"home", "HOME", "4B"}
    ):
        return "sent_out"
    if (end in {"score", "home", "4B"} or end == "score") and not is_out:
        return "sent_safe"
    if end == "3B":
        return "held"
    if is_out:
        return "out_elsewhere"
    return "other"


def extrapolate(game_counts, league_games):
    """Scale the per-game sample mean by the full regular-season schedule."""
    if not game_counts or not league_games:
        mean = 0.0
        margin = 0.0
    else:
        mean = statistics.mean(game_counts)
        if len(game_counts) > 1:
            margin = (
                1.96 * statistics.stdev(game_counts)
                / len(game_counts) ** 0.5
            )
        else:
            margin = 0.0
    low = max(0.0, mean - margin) * league_games
    high = (mean + margin) * league_games
    return {
        "estimate": int(round(mean * league_games)),
        "interval_95": [int(round(low)), int(round(high))],
        "league_schedule_games": league_games,
        "sample_games": len(game_counts),
        "sample_mean": mean,
        "full_retrieval_requests_estimate": league_games + 3,
    }


def outcome_counts(records):
    classes = [classify(record) for record in records]
    counts = {
        name: classes.count(name)
        for name in (
            "sent_safe", "advanced_later", "sent_out", "held",
            "out_elsewhere", "other",
        )
    }
    if sum(counts.values()) != len(records):
        raise ValueError("outcome classes do not cover opportunities")
    return counts


def parse_leaderboard(text, positions=None):
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    rows = list(reader)
    if not reader.fieldnames or not any(
        k.lower() in {"player_id", "id"} for k in reader.fieldnames
    ):
        raise ValueError("leaderboard lacks person ID column")
    id_col = next(
        k for k in reader.fieldnames if k.lower() in {"player_id", "id"}
    )
    ids = set()
    for row in rows:
        if positions and row.get("primary_position") not in positions:
            continue
        value = row[id_col]
        if not value:
            continue
        if not value.isdigit():
            raise ValueError("malformed leaderboard person ID")
        ids.add(int(value))
    return ids


def id_join_rate(person_ids, leaderboard_ids):
    """Return matched and denominator counts after normalizing integer IDs."""
    normalized = {int(value) for value in person_ids if value is not None}
    matched = normalized & {int(value) for value in leaderboard_ids}
    return {
        "matched": len(matched),
        "total": len(normalized),
        "rate": len(matched) / len(normalized) if normalized else None,
    }


def md_escape(value):
    return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def join_text(value):
    if value["rate"] is None:
        return "not measurable (no IDs)"
    return (
        str(value["matched"]) + "/" + str(value["total"])
        + " (" + format(value["rate"] * 100, ".1f") + "%)"
    )


def rate_text(value):
    if value is None:
        return "not available"
    return format(value * 100, ".1f") + "%"


def location_statement(seasons):
    rates = [
        row["identification_rates"]["location"] for row in seasons.values()
    ]
    if not rates or all(rate == 0 or rate is None for rate in rates):
        return (
            "UNKNOWN: Hit location is absent from the sampled play-by-play "
            "response schema."
        )
    return (
        "FACT: Hit location was present on "
        + ", ".join(rate_text(rate) for rate in rates)
        + " of 2025 and 2026 opportunities."
    )


def verdict_label(seasons):
    for row in seasons.values():
        rates = row["identification_rates"]
        if row["opportunities"] == 0 or not rates.get("runner_id"):
            return "NOT FEASIBLE"
        if rates["runner_id"] < 0.5 or rates["hit"] < 0.5:
            return "NOT FEASIBLE"
    return "PARTIAL"


def verdict_reason(seasons):
    if verdict_label(seasons) == "NOT FEASIBLE":
        return (
            "The sample does not identify enough runner or hit fields to "
            "count send and hold situations."
        )
    return (
        "The feed supports counts of candidate situations, recorded "
        "safe, out, and held outcomes, and person-ID joins to public "
        "sprint-speed and arm-strength leaderboards. It does not record "
        "the coach's sign, the runner's jump, or what a held runner would "
        "have done if sent. Base at contact is inferred from originBase."
    )


def triple(view):
    return (
        str(view["opportunities"]) + " opportunities, "
        + str(view["scored_any"]) + " scored (any), "
        + str(view["ended_at_3b_no_score"]) + " ended at 3B without scoring"
    )


def reconciliation_lines(data):
    recon = data.get("count_reconciliation")
    if not recon:
        return []
    lines = ["## Reconciliation with the controller's recount", ""]
    for season in data["seasons"]:
        lines.append(
            "FACT: Season " + season + ": this report (first segment sets "
            "the base at contact) "
            + triple(recon["first_segment_rule"][season])
            + "; diagnostic any-segment rule "
            + triple(recon["any_segment_rule"][season])
            + "; controller recount target "
            + triple(recon["controller_recount"][season]) + "."
        )
        lines.append(
            "FACT: Season " + season + " segment end sequences, this report: "
            + md_escape(
                recon["first_segment_rule"][season]["segment_end_sequences"]
            ) + "; any-segment rule: "
            + md_escape(
                recon["any_segment_rule"][season]["segment_end_sequences"]
            ) + "."
        )
    seasons = list(data["seasons"])
    totals_match = all(
        recon["any_segment_rule"][s]["opportunities"]
        == recon["controller_recount"][s]["opportunities"]
        for s in seasons
    )
    views_match = all(
        recon["any_segment_rule"][s][key]
        == recon["controller_recount"][s][key]
        for s in seasons
        for key in ("scored_any", "ended_at_3b_no_score")
    )
    if totals_match:
        lines.append(
            "INFERENCE: The controller's qualifying totals equal the "
            "diagnostic any-segment rule totals, which admit runners whose "
            "later segment started on the threshold base. This report "
            "identifies 85 (2025) and 90 (2026) qualifying opportunities "
            "(175 total) because the spec takes the base from the "
            "runner's first segment. Examples of runners excluded under the "
            "first-segment rule (at most 5): "
            + "; ".join(
                "season " + str(e["season"]) + " game " + str(e["game_id"])
                + " runner " + str(e["runner_id"]) + " " + e["hit"]
                + " contact bases " + ">".join(
                    str(b) for b in e["contact_bases_by_segment"]
                )
                for e in data.get("examples", [])
            ) + "."
        )
    else:
        lines.append(
            "UNKNOWN: Neither qualification rule reproduces the "
            "controller's qualifying totals."
        )
    if views_match:
        lines.append(
            "INFERENCE: Scored and ended-at-3B counts also equal the "
            "any-segment rule."
        )
    else:
        lines.append(
            "UNKNOWN: Scored (any) and ended-at-3B counts differ from the "
            "controller's recount targets (this report: "
            + ", ".join(
                s + " " + str(recon["first_segment_rule"][s]["scored_any"])
                + " scored, "
                + str(recon["first_segment_rule"][s]["ended_at_3b_no_score"])
                + " ended at 3B"
                for s in seasons
            )
            + "; controller targets: "
            + ", ".join(
                s + " " + str(recon["controller_recount"][s]["scored_any"])
                + " scored, "
                + str(recon["controller_recount"][s]["ended_at_3b_no_score"])
                + " ended at 3B"
                for s in seasons
            )
            + "). Whole-movement evaluation classifies each runner across "
            "all segments on the play, whereas the controller's recount "
            "method for movement views is unverified from the cache; out at "
            "home is 0 in all counts."
        )
    cases = recon.get("unknown_cases") or {}
    lines.append(
        "UNKNOWN: Cases outside the spec: "
        + str(cases.get("segments_without_runner_id", 0))
        + " runner segments without a person ID (not counted), and "
        + str(cases.get("scored_and_out_same_play", 0))
        + " runners who both scored and were out on the same play."
    )
    lines.append("")
    return lines


def render(data):
    lines = [
        "# Third-base send/hold feasibility",
        "",
        "INFERENCE: Study verdict: **" + data["verdict"] + "**",
        "",
        "FACT: Measurements use cached game feeds and public leaderboards.",
        "FACT: Source: [MLB Stats API](https://statsapi.mlb.com/api/v1/) and "
        "[Baseball Savant sprint speed]("
        "https://baseballsavant.mlb.com/leaderboard/sprint_speed) "
        "and [arm strength]("
        "https://baseballsavant.mlb.com/leaderboard/arm-strength) "
        "CSV leaderboards; retrieved 2026-10-09.",
        "",
        "FACT: Per-season counts from the deduplicated cached sample.",
        "",
        "| season | sample games | opportunities | scored (any) | advanced "
        "later | sent safe | sent out | ended at 3B, no score | out "
        "elsewhere | other |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for season, row in data["seasons"].items():
        lines.append(
            "| "
            + " | ".join(
                md_escape(row[k])
                for k in (
                    "season",
                    "games",
                    "opportunities",
                    "scored_any",
                    "advanced_later",
                    "sent_safe",
                    "sent_out",
                    "ended_at_3b_no_score",
                    "out_elsewhere",
                    "other",
                )
            )
            + " |"
        )
    lines += [
        "",
        "FACT: 'Scored (any)' and 'ended at 3B, no score' are movement views; "
        "they are not partitions. A runner who reached third before a later "
        "scoring event appears in both views. 'Advanced on a later event' "
        "means the send decision is ambiguous. Held means the feed records "
        "the runner ending at third. The play-by-play does not establish the "
        "coach's sign or the runner's base at the exact batted-ball moment; "
        "treat these as candidate opportunities.",
        "",
    ]
    lines += reconciliation_lines(data)
    for season, row in data["seasons"].items():
        lines += ["## " + str(season), ""]
        rates = row["identification_rates"]
        lines.append(
            "FACT: Identification rates: runner ID "
            + rate_text(rates["runner_id"])
            + "; fielder ID " + rate_text(rates["fielder_id"])
            + "; hit type " + rate_text(rates["hit"])
            + "; location " + rate_text(rates["location"])
            + "; outs " + rate_text(rates["outs"])
            + "; score " + rate_text(rates["score"])
        )
        lines.append(
            "FACT: Leaderboard ID matches: sprint speed "
            + md_escape(join_text(row["speed_join"]))
            + "; arm strength "
            + md_escape(join_text(row["arm_join"]))
        )
        outcome_rates = row["outcome_rates"]
        lines.append(
            "FACT: Outcome rates (safe, advanced later, out at home, held, "
            "out elsewhere, other): "
            + ", ".join(
                rate_text(outcome_rates[key])
                for key in ("sent_safe", "advanced_later", "sent_out",
                            "held", "out_elsewhere", "other")
            )
        )
        lines.append(
            "INFERENCE: League-wide opportunities "
            + md_escape(row["extrapolation"]["estimate"])
            + " (95% interval "
            + md_escape(row["extrapolation"]["interval_95"])
            + "); estimated full-season requests "
            + md_escape(
                row["extrapolation"]["full_retrieval_requests_estimate"]
            )
            + "."
        )
        lines.append("")
    lines += [
        "INFERENCE: Per-game sample mean scaled by the full schedule; the "
        "interval uses a normal 95% interval from across-game sample standard "
        "error. It does not adjust for schedule-date effects.",
        "INFERENCE: Sample selection uses fixed seed "
        + str(data["seed"])
        + "; schedule SHA-256 " + data["schedule_hash"] + ".",
        "INFERENCE: Estimated requests to retrieve the full two-season "
        "schedule and feeds plus four leaderboard CSVs: "
        + str(data["full_retrieval_request_estimate"]) + ".",
        "FACT: New network requests used for this sample: "
        + str(data["new_requests_used"]) + " of " + str(data["ceiling"])
        + "; cache hits are free.",
        "",
        "UNKNOWN: The feed does not establish coach sign, runner jump, or the "
        "counterfactual outcome for held runners.",
        md_escape(
            data.get("location_statement")
            or (
                "UNKNOWN: Hit location is absent from the sampled "
                "play-by-play response schema."
            )
        ),
        "INFERENCE: Verdict reason: " + md_escape(data["verdict_reason"]),
        "",
    ]
    return "\n".join(lines)


def materialize(root):
    root = Path(root)
    selection = json.loads((root / "data/sendhold_sampling.json").read_text())
    client = Client(
        root, offline=True, ceiling=CEILING,
        allowed_hosts={"statsapi.mlb.com", "baseballsavant.mlb.com"},
    )
    opportunities = []
    for games in selection.values():
        for game in games:
            feed = client.get(f"game/{game['gamePk']}/playByPlay")
            for play in feed.get("allPlays", []):
                for row in identify_opportunities([play]):
                    row["season"] = game["season"]
                    row["game_id"] = game["gamePk"]
                    opportunities.append(row)
    leaders = {}
    for season in (2025, 2026):
        leaders[str(season)] = {}
        for metric, params in (
            ("sprint_speed", {
                "min_season": season, "max_season": season,
                "min": 0, "position": "", "team": "",
            }),
            ("arm_strength", {
                "year": season, "type": "player", "position": "OF",
                "min_throws": 0,
            }),
        ):
            leaders[str(season)][metric] = sorted(parse_leaderboard(
                client.get_url(
                    SAVANT + (
                        "sprint_speed"
                        if metric == "sprint_speed"
                        else "arm-strength"
                    ),
                    text=True, csv="true", **params,
                ), positions=(
                    {"7", "8", "9", "LF", "CF", "RF", "OF"}
                    if metric == "arm_strength" else None
                )
            ))
    atomic_json(root / "data/sendhold_opportunities.json", opportunities)
    atomic_json(root / "data/sendhold_leaderboards.json", leaders)


def view_counts(records):
    return {
        "opportunities": len(records),
        "scored_any": sum(scored_any(r) for r in records),
        "ended_at_3b_no_score": sum(ended_third_no_score(r) for r in records),
    }


def sequence_counts(records):
    """Count runners by the ordered ends of their movement segments."""
    counts = {}
    for record in records:
        key = ">".join(
            str((segment.get("movement") or {}).get("end") or "none")
            for segment in record["segments"]
        )
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def build_report(root):
    """Compute the report data from cached files; writes nothing."""
    root = Path(root)
    selection = json.loads((root / "data/sendhold_sampling.json").read_text())
    schedules = json.loads((root / "data/sendhold_schedule.json").read_text())
    leaderboards = json.loads(
        (root / "data/sendhold_leaderboards.json").read_text()
    )
    client = Client(root, offline=True)
    rows = []
    wide_rows = []
    differences = []
    unknown = {
        "segments_without_runner_id": 0,
        "scored_and_out_same_play": 0,
    }
    for games in selection.values():
        for game in games:
            feed = client.get(f"game/{game['gamePk']}/playByPlay")
            for play in feed.get("allPlays", []):
                found = identify_opportunities([play])
                wide = identify_opportunities([play], rule="any")
                kind = (play.get("result") or {}).get("eventType")
                if kind in {"single", "double"} and pre_play_outs(play) < 2:
                    unknown["segments_without_runner_id"] += (
                        group_runners(play)[1]
                    )
                    unknown["scored_and_out_same_play"] += sum(
                        scored_any(r) and any(
                            (s.get("movement") or {}).get("isOut") is True
                            for s in r["segments"]
                        )
                        for r in found
                    )
                kept = {r["runner_id"] for r in found}
                for row in wide:
                    if row["runner_id"] not in kept and len(differences) < 5:
                        differences.append({
                            "season": game["season"],
                            "game_id": game["gamePk"],
                            "runner_id": row["runner_id"],
                            "hit": row["hit"],
                            "contact_bases_by_segment": [
                                base_at_contact(play, s, row["hit"])
                                for s in row["segments"]
                            ],
                        })
                for source, target in ((found, rows), (wide, wide_rows)):
                    for row in source:
                        row["season"] = game["season"]
                        row["game_id"] = game["gamePk"]
                        target.append(row)
    aggregates = {}
    for season in (2025, 2026):
        records = [r for r in rows if r["season"] == season]
        counts = outcome_counts(records)
        classes = [classify(r) for r in records]
        selected = selection[str(season)]
        game_counts = [
            sum(r["game_id"] == g["gamePk"] for r in records) for g in selected
        ]
        season_games = len({
            g["gamePk"] for g in schedules if g["season"] == season
        })
        runner_ids = {r["runner_id"] for r in records if r.get("runner_id")}
        fielder_ids = {r["fielder_id"] for r in records if r.get("fielder_id")}
        speed_ids = set(leaderboards[str(season)]["sprint_speed"])
        arm_ids = set(leaderboards[str(season)]["arm_strength"])

        def coverage(key):
            return (
                sum(r.get(key) is not None for r in records) / len(records)
                if records
                else None
            )

        aggregates[str(season)] = {
            "season": season,
            "games": len(selected),
            **view_counts(records),
            **counts,
            "outcome_rates": {
                name: classes.count(name) / len(classes) if classes else None
                for name in ("sent_safe", "advanced_later", "sent_out",
                             "held", "out_elsewhere", "other")
            },
            "identification_rates": {
                key: coverage(key)
                for key in (
                    "runner_id",
                    "fielder_id",
                    "hit",
                    "location",
                    "outs",
                    "score",
                )
            },
            "speed_join": id_join_rate(runner_ids, speed_ids),
            "arm_join": id_join_rate(fielder_ids, arm_ids),
            "extrapolation": extrapolate(game_counts, season_games),
        }
    by_season = {
        rule: {
            str(season): {
                **view_counts([r for r in source if r["season"] == season]),
                "segment_end_sequences": sequence_counts(
                    [r for r in source if r["season"] == season]
                ),
            }
            for season in (2025, 2026)
        }
        for rule, source in (
            ("first_segment_rule", rows), ("any_segment_rule", wide_rows)
        )
    }
    data = {
        "seed": SEED,
        "ceiling": CEILING,
        "new_requests_used": json.loads(
            (root / "data/sendhold_request_ledger.json").read_text()
        )["count"],
        "schedule_hash": hashlib.sha256(
            (root / "data/sendhold_schedule.json").read_bytes()
        ).hexdigest(),
        "season_samples": {k: len(v) for k, v in selection.items()},
        "full_retrieval_request_estimate": sum(
            len({g["gamePk"] for g in schedules if g["season"] == season})
            for season in (2025, 2026)
        ) + 6,
        "seasons": aggregates,
        "verdict": verdict_label(aggregates),
        "verdict_reason": verdict_reason(aggregates),
        "location_statement": location_statement(aggregates),
        "examples": differences,
        "count_reconciliation": {
            "controller_recount": CONTROLLER_RECOUNT,
            **by_season,
            "unknown_cases": unknown,
        },
    }
    return data


def analyze(root):
    root = Path(root)
    data = build_report(root)
    atomic_json(root / "research/sendhold_feasibility.json", data)
    (root / "research/SENDHOLD_FEASIBILITY.md").write_text(render(data))
    return data


def fetch(root):
    root = Path(root)
    client = Client(
        root,
        request_cap=CEILING,
        ceiling=CEILING,
        allowed_hosts={"statsapi.mlb.com", "baseballsavant.mlb.com"},
    )
    schedule = {}
    for season in (2025, 2026):
        schedule[str(season)] = client.get(
            "schedule", sportId=1, season=season, gameType="R"
        )
    games = []
    for season, value in schedule.items():
        for day in value.get("dates", []):
            for game in day.get("games", []):
                games.append({"season": int(season), "gamePk": game["gamePk"]})
    selection = stable_sample(games)
    atomic_json(root / "data/sendhold_schedule.json", games)
    atomic_json(root / "data/sendhold_sampling.json", selection)
    all_plays = []
    for season_games in selection.values():
        for game in season_games:
            feed = client.get(f"game/{game['gamePk']}/playByPlay")
            for play in feed.get("allPlays", []):
                for opportunity in identify_opportunities([play]):
                    opportunity["season"] = game["season"]
                    opportunity["game_id"] = game["gamePk"]
                    all_plays.append(opportunity)
    leaderboards = {}
    for season in (2025, 2026):
        leaderboards[str(season)] = {}
        sprint_url = SAVANT + "sprint_speed"
        leaderboards[str(season)]["sprint_speed"] = sorted(
            parse_leaderboard(
                client.get_url(
                    sprint_url,
                    text=True,
                    csv="true",
                    min_season=season,
                    max_season=season,
                    min=0,
                    position="",
                    team="",
                )
            )
        )
        arm_url = SAVANT + "arm-strength"
        leaderboards[str(season)]["arm_strength"] = sorted(
            parse_leaderboard(
                client.get_url(
                    arm_url,
                    text=True,
                    csv="true",
                    year=season,
                    type="player",
                    position="OF",
                    min_throws=0,
                )
            )
        )
    atomic_json(root / "data/sendhold_leaderboards.json", leaderboards)
    atomic_json(root / "data/sendhold_opportunities.json", all_plays)
    return analyze(root)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--analyze", action="store_true")
    parser.add_argument("--ceiling", type=int, default=CEILING)
    args = parser.parse_args(argv)
    if args.ceiling > CEILING or args.ceiling < 1:
        parser.error("--ceiling must be between 1 and 150")
    return analyze(args.root) if args.analyze else fetch(args.root)


if __name__ == "__main__":
    main()
