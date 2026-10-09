"""Bounded public API measurements; no inferred contract status."""

from collections import Counter, defaultdict
import re

from .client import BASE, ApiError, MalformedResponseError
from .parse import scoped_stats, stats, teams_summary, transactions

MILB_YEARS = [2018, 2019, 2021, 2022, 2023, 2024, 2025]
RULE5_YEARS = list(range(2015, 2026))
MILB_SPORTS = [11, 12, 13, 14, 16]
LEVEL_SPORTS = [11, 12, 13, 14]


def rule_text(row):
    return bool(
        re.search(r"\brule\s+(5|v)\b", row["description"] or "", re.IGNORECASE)
    )


def rule_groups(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[(row["code"], row["type_desc"])].append(row)
    return [
        {
            "code": code,
            "type_desc": desc,
            "count": len(events),
            "rule_text_count": sum(rule_text(r) for r in events),
            "examples": events[:3],
            "rule_text_examples": [r for r in events if rule_text(r)][:3],
            "non_rule_examples": [r for r in events if not rule_text(r)][:3],
        }
        for (code, desc), events in sorted(
            groups.items(), key=lambda pair: str(pair[0])
        )
    ]


def classify(events, team_levels, histories):
    """Two proxies, never label missing MLB stats as confirmed absence."""
    evidence = []
    for event in events:
        levels = set()
        for field in ["from_team", "to_team"]:
            levels.update(team_levels.get(event[field], []))
        a = "mlb" if 1 in levels else "minor" if levels else "unresolved"
        history = histories.get(event["player_id"], {})
        sports = sorted(s for s, present in history.items() if present)
        b = (
            "mlb"
            if 1 in sports
            else "minor"
            if set(sports) & set(MILB_SPORTS)
            and all(s in history for s in [1] + MILB_SPORTS)
            else "unresolved"
        )
        evidence.append(
            {
                "event": event,
                "team_sports": sorted(levels),
                "season_sports": sports,
                "queried_sports": sorted(history),
                "A": a,
                "B": b,
            }
        )
    counts = {
        "A": dict(Counter(e["A"] for e in evidence)),
        "B": dict(Counter(e["B"] for e in evidence)),
        "agreement": sum(e["A"] == e["B"] != "unresolved" for e in evidence),
        "disagreement": sum(
            e["A"] != e["B"] and "unresolved" not in (e["A"], e["B"])
            for e in evidence
        ),
        "unresolved": sum("unresolved" in (e["A"], e["B"]) for e in evidence),
        "minor_only_proxy": sum(e["A"] == e["B"] == "minor" for e in evidence),
        "confirmed_minor_contract_elections": None,
    }
    return counts, evidence


def run(client):
    observations = []

    def fetch(endpoint, parser=lambda x: x, **params):
        query = {"endpoint": BASE + endpoint, "params": params}
        try:
            return parser(client.get(endpoint, **params)), query
        except (ApiError, ValueError, TypeError, KeyError) as exc:
            observations.append({"query": query, "failure": str(exc)})
            return None, query

    for year in RULE5_YEARS:
        rows, query = fetch(
            "transactions",
            transactions,
            startDate=f"{year}-11-01",
            endDate=f"{year}-12-31",
        )
        if rows is None:
            continue
        narrow = set()
        complete = True
        for month, end in [("11", 30), ("12", 31)]:
            part, pq = fetch(
                "transactions",
                transactions,
                startDate=f"{year}-{month}-01",
                endDate=f"{year}-{month}-{end}",
            )
            observations.append(
                {"query": pq, "rows": len(part) if part is not None else None}
            )
            if part is None:
                complete = False
            else:
                narrow.update(r["id"] for r in part)
        groups = rule_groups(rows)
        identifiers = {
            (g["code"], g["type_desc"]) for g in groups if g["rule_text_count"]
        }
        events = [
            r for r in rows if (r["code"], r["type_desc"]) in identifiers
        ]
        observations.append(
            {
                "candidate": "RULE5",
                "season": year,
                "query": query,
                "rows": len(rows),
                "groups": groups,
                "window_union_matches": {r["id"] for r in rows} == narrow
                if complete
                else None,
                "identifiers": sorted([list(k) for k in identifiers], key=str),
                "matched_events": len(events),
                "text_matched_events": sum(rule_text(r) for r in events),
                "events": events,
                "r5_without_text": sum(
                    r["code"] == "R5" and not rule_text(r) for r in rows
                ),
                "dr_with_text": sum(
                    r["code"] == "DR" and rule_text(r) for r in rows
                ),
                "dr_without_text": sum(
                    r["code"] == "DR" and not rule_text(r) for r in rows
                ),
            }
        )
        if year not in MILB_YEARS:
            continue
        elections = [
            r
            for r in rows
            if "elected free agency" in (r["description"] or "").lower()
        ]
        team_levels = defaultdict(list)
        team_queries = []
        for sport in [1] + MILB_SPORTS:
            summary, tq = fetch(
                "teams", teams_summary, sportId=sport, season=year
            )
            team_queries.append(tq)
            if summary is not None:
                for team in summary["ids"]:
                    team_levels[team].append(sport)
            observations.append(
                {
                    "query": tq,
                    "season": year,
                    "sport_id": sport,
                    "teams": summary,
                }
            )
        histories = defaultdict(dict)
        history_queries = []
        players = sorted(
            {r["player_id"] for r in elections if r["player_id"] is not None}
        )
        for sport in [1] + MILB_SPORTS:
            for offset in range(0, len(players), 100):
                hydrate = (
                    "stats(group=[hitting,pitching],type=[season],"
                    f"season={year},sportId={sport})"
                )
                people, pq = fetch(
                    "people",
                    personIds=",".join(
                        map(str, players[offset:offset + 100])
                    ),
                    hydrate=hydrate,
                )
                history_queries.append(pq)
                if people is None:
                    continue
                try:
                    if not isinstance(people.get("people"), list):
                        raise MalformedResponseError("Missing people array")
                    for person in people["people"]:
                        splits = stats(person)
                        # Empty stats is observed missingness, not no play.
                        histories[person["id"]][sport] = any(
                            str(s["season"]) == str(year)
                            and s["sport_id"] == sport
                            for s in (splits or [])
                        )
                except (ApiError, KeyError, TypeError) as exc:
                    observations.append({"query": pq, "failure": str(exc)})
        counts, evidence = classify(elections, team_levels, histories)
        observations.append(
            {
                "candidate": "MILBFA",
                "season": year,
                "query": query,
                "team_queries": team_queries,
                "history_queries": history_queries,
                "matched_events": len(elections),
                "counts": counts,
                "evidence": evidence,
            }
        )
    for year in MILB_YEARS:
        for sport in LEVEL_SPORTS:
            data, query = fetch(
                "stats",
                stats="season",
                group="hitting",
                season=year,
                sportIds=sport,
                limit=1,
                sortStat="plateAppearances",
                order="desc",
            )
            if data is None:
                continue
            try:
                groups = data.get("stats")
                if not isinstance(groups, list) or not groups:
                    raise MalformedResponseError("Missing leaderboard stats")
                splits = groups[0].get("splits")
                if not isinstance(splits, list):
                    raise MalformedResponseError("Missing leaderboard splits")
                player = splits[0]["player"]["id"] if splits else None
                observations.append(
                    {
                        "candidate": "CALLUP",
                        "query": query,
                        "season": year,
                        "sport_id": sport,
                        "selected_player": player,
                        "returned_splits": len(splits),
                        "total_splits": groups[0].get("totalSplits"),
                    }
                )
                if player is None:
                    continue
                scope, sq = fetch(
                    f"people/{player}/stats",
                    lambda d: scoped_stats(d, year, sport),
                    stats="gameLog",
                    group="hitting",
                    season=year,
                    sportId=sport,
                )
                rows = scope["splits"] if scope else None
                dates = [r["date"] for r in (rows or []) if r["date"]]
                observations.append(
                    {
                        "candidate": "CALLUP",
                        "query": sq,
                        "season": year,
                        "sport_id": sport,
                        "sample_player": player,
                        "independent_level_sample": True,
                        "dated_splits": len(dates)
                        if rows is not None
                        else None,
                        "through_june": sum(
                            d <= f"{year}-06-30" for d in dates
                        )
                        if rows is not None
                        else None,
                        "first_date": min(dates) if dates else None,
                        "last_date": max(dates) if dates else None,
                    }
                )
            except (ApiError, KeyError, TypeError) as exc:
                observations.append({"query": query, "failure": str(exc)})
    return observations
