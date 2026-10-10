"""Build aggregate-only data products for the frozen SENDHOLD design."""

import argparse
import csv
import io
import json
from collections import Counter, defaultdict
from pathlib import Path

from .client import Client, atomic_json
from .sendhold import (
    SAVANT,
    SCORE_ENDS,
    base_at_contact,
    identify_opportunities,
    pre_play_outs,
)

LABELS = (
    "SENT_OUT",
    "OUT_ELSEWHERE",
    "SENT_SAFE",
    "AMBIGUOUS",
    "HOLD",
    "OTHER")


def assign_label(record):
    """Assign a mutually exclusive label using the frozen precedence."""
    segments = record.get("segments", [])
    moves = [(segment.get("movement") or {}) for segment in segments]
    if any(m.get("isOut") is True and (
        m.get("end") in SCORE_ENDS | {"home"}
        or m.get("outBase") in {"home", "HOME", "4B"}
    ) for m in moves):
        return "SENT_OUT"
    if any(m.get("isOut") is True for m in moves):
        return "OUT_ELSEWHERE"
    if moves and moves[0].get("end") in SCORE_ENDS:
        return "SENT_SAFE"
    if any(m.get("end") == "3B" for m in moves[:-1]) and any(
        m.get("end") in SCORE_ENDS for m in moves[1:]
    ):
        return "AMBIGUOUS"
    if moves and moves[-1].get("end") == "3B":
        return "HOLD"
    return "OTHER"


def _event_name(value):
    return str(value).strip().lower() if value else None


def assign_label_v3(record, play_event=None):
    """Assign v3 labels (design v3, primary).

    Identical to ``assign_label`` except for runners who score: the runner is
    SENT_SAFE only when every movement segment after the first carries the
    play's own event (for example Single or Double); a later segment with a
    different event (Error, Runner Out, Other Advance) makes it AMBIGUOUS.
    Events compare case-insensitively because the feed spells the play
    result "Single" and the event type "single".
    """
    segments = record.get("segments", [])
    moves = [(segment.get("movement") or {}) for segment in segments]
    if any(m.get("isOut") is True and (
        m.get("end") in SCORE_ENDS | {"home"}
        or m.get("outBase") in {"home", "HOME", "4B"}
    ) for m in moves):
        return "SENT_OUT"
    if any(m.get("isOut") is True for m in moves):
        return "OUT_ELSEWHERE"
    if any(m.get("end") in SCORE_ENDS for m in moves):
        event = _event_name(play_event or record.get("play_event"))
        if all(event and _event_name(
                (segment.get("details") or {}).get("event")) == event
               for segment in segments[1:]):
            return "SENT_SAFE"
        return "AMBIGUOUS"
    if moves and moves[-1].get("end") == "3B":
        return "HOLD"
    return "OTHER"


def batting_score_difference(play, half, previous):
    """Pre-play batting-team lead, based on post-play scores and run delta."""
    result = play.get("result") or {}
    away, home = result.get("awayScore"), result.get("homeScore")
    if away is None or home is None:
        return None
    post = away - home if half == "top" else home - away
    runs = max(
        0,
        away -
        previous[0]) if half == "top" else max(
        0,
        home -
        previous[1])
    return post - runs


def pre_play_score(play):
    """Recover away/home score before the play from feed score and runners."""
    result = play.get("result") or {}
    away, home = result.get("awayScore"), result.get("homeScore")
    if away is None or home is None:
        return None
    runs = sum(
        1 for runner in play.get("runners", [])
        if (runner.get("movement") or {}).get("end") in SCORE_ENDS
        and (runner.get("movement") or {}).get("isOut") is not True
    )
    half = str((play.get("about") or {}).get("halfInning", "")).lower()
    if half == "top":
        return int(away) - runs, int(home)
    if half == "bottom":
        return int(away), int(home) - runs
    return None


def run_expectancy(plays):
    """Compute observed mean remaining runs for complete half-innings only."""
    halves = defaultdict(list)
    for play in plays:
        about = play.get("about") or {}
        half = str(about.get("halfInning", "")).lower()
        if half not in {"top", "bottom"}:
            continue
        key = (
            play.get(
                "game_id",
                about.get("gamePk")),
            about.get("inning"),
            half)
        halves[key].append(play)
    observations = defaultdict(list)
    excluded = 0
    complete = 0
    used_plays = 0
    for sequence in halves.values():
        outs_after = 0
        states = []
        runs_by_play = []
        positions = {}
        for play in sequence:
            outs = pre_play_outs(play)
            # The feed lists runner movements, not a complete base snapshot.
            # Carry each runner's last destination through the half-inning.
            for runner in play.get("runners", []):
                movement = runner.get("movement") or {}
                runner_id = (
                    runner.get("details") or {}).get(
                    "runner",
                    {}).get("id")
                start = movement.get("originBase") or movement.get("start")
                if (runner_id is not None and runner_id not in positions
                        and start):
                    positions[runner_id] = start
            occupied = set(positions.values())
            mask = (int("1B" in occupied) + 2 * int("2B" in occupied)
                    + 4 * int("3B" in occupied))
            states.append((mask, outs))
            runs_by_play.append(sum(
                1 for runner in play.get("runners", [])
                if (runner.get("movement") or {}).get("end") in SCORE_ENDS
                and (runner.get("movement") or {}).get("isOut") is not True
            ))
            for runner in play.get("runners", []):
                movement = runner.get("movement") or {}
                runner_id = (
                    runner.get("details") or {}).get(
                    "runner",
                    {}).get("id")
                if runner_id is None:
                    continue
                end = movement.get("end")
                if movement.get("isOut") is True or end in SCORE_ENDS:
                    positions.pop(runner_id, None)
                elif end in {"1B", "2B", "3B"}:
                    positions[runner_id] = end
            count_outs = (play.get("count") or {}).get("outs")
            added_outs = sum(
                (runner.get("movement") or {}).get("isOut") is True
                for runner in play.get("runners", []))
            observed_outs = (int(count_outs) if count_outs is not None
                             else outs + added_outs)
            outs_after = max(outs_after, observed_outs)
        if outs_after < 3:
            excluded += 1
            continue
        complete += 1
        remaining = [0] * len(states)
        total = 0
        for index in range(len(states) - 1, -1, -1):
            total += runs_by_play[index]
            remaining[index] = total
        for state, value in zip(states, remaining):
            observations[state].append(value)
        used_plays += len(states)
    table = []
    for outs in range(3):
        for mask in range(8):
            values = observations.get((mask, outs), [])
            mean = sum(values) / len(values) if values else None
            table.append({"outs": outs, "bases_mask": mask,
                          "count": len(values), "mean_runs": mean})
    return {"states": table, "complete_half_innings": complete,
            "excluded_half_innings": excluded, "plays_used": used_plays}


def _flatten_schedule(payload, season):
    """Return unique regular-season games for the requested season."""
    games = {}
    for date in payload.get("dates", []):
        for game in date.get("games", []):
            if game.get("gameType") != "R":
                continue
            if int(game.get("season", season)) != int(season):
                continue
            game_pk = game.get("gamePk")
            if game_pk is not None:
                games[int(game_pk)] = game
    return [games[key] for key in sorted(games)]


def _leaderboard(client, season, metric):
    url = SAVANT + ("sprint_speed" if metric ==
                    "sprint_speed" else "arm-strength")
    params = ({"min_season": season,
               "max_season": season,
               "min": 0,
               "position": "",
               "team": ""} if metric == "sprint_speed" else {"year": season,
                                                             "type": "player",
                                                             "position": "OF",
                                                             "min_throws": 0})
    text = client.get_url(url, text=True, csv="true", **params)
    value_key = "sprint_speed" if metric == "sprint_speed" else "arm_overall"
    return parse_leaderboard_values(text, value_key)


def parse_leaderboard_values(text, value_key):
    """Parse numeric leaderboard values keyed by player ID."""
    rows = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    out = {}
    for row in rows:
        player_id = row.get("player_id")
        value = row.get(value_key)
        if player_id and player_id.isdigit() and value not in {None, ""}:
            out[int(player_id)] = float(value)
    return out


def prior_or_fallback(player_id, prior_values, season_values):
    """Return the prior value, or current-season value and fallback flag."""
    value = prior_values.get(player_id)
    if value is not None:
        return value, False
    value = season_values.get(player_id)
    return value, value is not None


def build_data(root):
    root = Path(root)
    client = Client(root, offline=True,
                    allowed_hosts={
                        "statsapi.mlb.com",
                        "baseballsavant.mlb.com"},
                    cache_manifest_paths=["data/sendhold_manifest.json"])
    schedule_payload = json.loads(
        (root / "data/sendhold_retrieve_schedule.json").read_text())
    ledger = json.loads(
        (root / "data/sendhold_request_ledger.json").read_text())
    schedules = {season: _flatten_schedule(
        schedule_payload[str(season)], season) for season in (2025, 2026)}
    values = {year: {metric: _leaderboard(client, year, metric)
                     for metric in ("sprint_speed", "arm_strength")}
              for year in (2024, 2025, 2026)}
    table = []
    season_plays = defaultdict(list)
    retrieved_games = defaultdict(int)
    for season, games in schedules.items():
        for game in games:
            game_id = game["gamePk"]
            feed = client.get("game/{}/playByPlay".format(game_id))
            retrieved_games[season] += 1
            away_id = game["teams"]["away"]["team"]["id"]
            home_id = game["teams"]["home"]["team"]["id"]
            for play in feed.get("allPlays", []):
                play["game_id"] = game_id
                about = play.get("about") or {}
                half = str(about.get("halfInning", "")).lower()
                if season == 2025:
                    season_plays[season].append(play)
                for row in identify_opportunities([play]):
                    event = ((play.get("result") or {}).get("event")
                             or (play.get("result") or {}).get("eventType"))
                    label = assign_label(row)
                    label_v3 = assign_label_v3(row, event)
                    runner = row["runner_id"]
                    prior = season - 1
                    speed, speed_fallback = prior_or_fallback(
                        runner, values[prior]["sprint_speed"],
                        values[season]["sprint_speed"])
                    fielder = row.get("fielder_id")
                    arm, arm_fallback = prior_or_fallback(
                        fielder, values[prior]["arm_strength"],
                        values[season]["arm_strength"])
                    previous = pre_play_score(play)
                    diff = (batting_score_difference(play, half, previous)
                            if previous is not None else None)
                    table.append(
                        {
                            "season": season,
                            "game_id": game_id,
                            "runner_id": runner,
                            "label": label,
                            "label_v3": label_v3,
                            "base_at_contact": base_at_contact(
                                play,
                                row["segments"][0],
                                row["hit"]),
                            "sprint_speed": speed,
                            "sprint_speed_same_season_fallback": (
                                speed_fallback),
                            "arm_strength": arm,
                            "arm_strength_same_season_fallback": arm_fallback,
                            "fielder_outfielder": fielder is not None,
                            "hit_type": row["hit"],
                            "hit_coordinates": (
                                row.get("location") or {}).get("coordinates"),
                            "hit_zone": (
                                row.get("location") or {}).get("zone"),
                            "outs": row["outs"],
                            "inning": about.get("inning"),
                            "score_difference_batting_view": diff,
                            "batting_team_id": (
                                away_id if half == "top" else home_id)})
    report = make_report(table, schedules, retrieved_games, ledger["count"],
                         run_expectancy(season_plays[2025]))
    return table, report


def make_report(table, schedules, retrieved, requests_used, expectancy):
    seasons = {}
    for season in (2025, 2026):
        rows = [row for row in table if row["season"] == season]
        counts_v2 = Counter(row["label"] for row in rows)
        counts_v3 = Counter(row["label_v3"] for row in rows)

        def rate(predicate):
            return sum(predicate(row)
                       for row in rows) / len(rows) if rows else None
        outfielders = [row for row in rows if row["fielder_outfielder"]]

        def arm_rate(predicate):
            return (sum(predicate(row) for row in outfielders) /
                    len(outfielders) if outfielders else None)
        seasons[str(season)] = {
            "games_retrieved": retrieved[season],
            "games_scheduled": len(schedules[season]),
            "label_counts_v3": {label: counts_v3[label] for label in LABELS},
            "label_counts_v2": {label: counts_v2[label] for label in LABELS},
            "covariate_coverage": {
                "prior_season_sprint_match_rate": rate(
                    lambda row: row["sprint_speed"] is not None and
                    not row["sprint_speed_same_season_fallback"]),
                "sprint_same_season_fallback_rate": rate(
                    lambda row: row["sprint_speed_same_season_fallback"]),
                "prior_season_arm_match_rate_among_outfielders": arm_rate(
                    lambda row: row["arm_strength"] is not None and
                    not row["arm_strength_same_season_fallback"]),
                "arm_same_season_fallback_rate_among_outfielders": arm_rate(
                    lambda row: row["arm_strength_same_season_fallback"]),
                "outfielder_share": rate(
                    lambda row: row["fielder_outfielder"]),
            },
        }
    out_count = seasons["2025"]["label_counts_v3"]["SENT_OUT"]
    return {
        "facts": {
            "primary_label_version": "v3",
            "requests_used": requests_used,
            "seasons": seasons,
            "run_expectancy_2025": expectancy,
            "early_stop": {
                "sent_out_2025": out_count,
                "threshold": 30,
                "met": out_count < 30}},
        "inference": [],
        "unknown": []}


def render(report):
    facts = report["facts"]
    lines = [
        "# SENDHOLD data report",
        "",
        "Only frozen-design data counts and coverage are reported.",
        "",
        "## Retrieval and labels",
        ""]
    for season, row in facts["seasons"].items():
        lines.extend(
            [
                "### {}".format(season),
                "",
                ("FACT: Games retrieved/scheduled: {}/{}; requests used "
                 "(shared retrieval ledger): {}.").format(
                    row["games_retrieved"],
                    row["games_scheduled"],
                    facts["requests_used"]),
                "FACT: Label counts, v3 definition (primary): " +
                ", ".join(
                    "{} {}".format(k, v)
                    for k, v in row["label_counts_v3"].items()) + ".",
                "FACT: Label counts, v2 definition (pre-registered, "
                "secondary): " +
                ", ".join(
                    "{} {}".format(k, v)
                    for k, v in row["label_counts_v2"].items()) + ".",
                "FACT: Covariate coverage: " +
                json.dumps(
                    row["covariate_coverage"],
                    sort_keys=True) +
                ".",
                ""])
    re = facts["run_expectancy_2025"]
    lines.extend(
        [
            "## 2025 run expectancy",
            "",
            ("FACT: A half-inning is complete when cumulative outs reach 3. "
             "Half-innings that never reach 3 outs are excluded; this rule "
             "excludes walk-offs and incomplete or suspended halves. "
             "Excluded: {}; complete: {}.").format(
                re["excluded_half_innings"],
                re["complete_half_innings"]),
            ("| Outs | Bases mask (1B=1, 2B=2, 3B=4) | Count | "
             "Mean runs remaining |"),
            "|---:|---:|---:|---:|"])
    for state in re["states"]:
        value = "NA" if state["mean_runs"] is None else "{:.4f}".format(
            state["mean_runs"])
        lines.append(
            "| {} | {} | {} | {} |".format(
                state["outs"],
                state["bases_mask"],
                state["count"],
                value))
    stop = facts["early_stop"]
    lines.extend(["",
                  ("FACT: Early-stop condition: SENT_OUT count in 2025 is {} "
                   "(threshold: fewer than 30); condition met: {}.").format(
                       stop["sent_out_2025"], str(stop["met"]).lower()),
                  "",
                  ("INFERENCE: None; no model was fit and no outcome analysis "
                   "was performed."),
                  ("UNKNOWN: No additional claims are made beyond cached "
                   "values and stated counting rules."),
                  ""])
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    table, report = build_data(args.root)
    atomic_json(args.root / "data/sendhold_opportunity_table.json", table)
    atomic_json(args.root / "research/sendhold_data.json", report)
    (args.root / "research/SENDHOLD_DATA.md").write_text(render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
