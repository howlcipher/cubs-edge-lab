"""Cohort, feature, outcome, and ranking helpers for the triage study."""

from datetime import date

from .probe.parse import innings_outs


def select_cohort(rows, year):
    """Select DFA elections; duplicate people retain their earliest date."""
    selected = {}
    null_person_rows = 0
    start, end = date(year, 11, 1), date(year, 12, 31)
    for row in rows:
        try:
            election_date = date.fromisoformat(row["date"])
        except (KeyError, TypeError, ValueError):
            continue
        description = row.get("description") or ""
        if (
            row.get("code") != "DFA"
            or "elected free agency" not in description.lower()
            or not start <= election_date <= end
        ):
            continue
        person_id = row.get("player_id")
        if person_id is None:
            null_person_rows += 1
            continue
        if (
            person_id not in selected
            or election_date.isoformat() < selected[person_id]["date"]
        ):
            selected[person_id] = {
                "person_id": person_id,
                "date": election_date.isoformat(),
            }
    return list(selected.values()), null_person_rows


def age_on(birth_date, on_date):
    birth = (
        date.fromisoformat(birth_date)
        if isinstance(birth_date, str)
        else birth_date
    )
    day = date.fromisoformat(on_date) if isinstance(on_date, str) else on_date
    return (
        day.year
        - birth.year
        - ((day.month, day.day) < (birth.month, birth.day))
    )


def as_of_features(
    player_id, election_date, birth_date, season_stats, transaction_rows=()
):
    """Extract season features and only pre-election transactions."""
    election = date.fromisoformat(election_date)
    transactions_before = [
        r
        for r in transaction_rows
        if r.get("player_id") == player_id
        and r.get("date")
        and date.fromisoformat(r["date"]) <= election
    ]
    allowed_years = {election.year, election.year - 1}
    stats = [
        r
        for r in season_stats
        if r.get("person_id") == player_id
        and int(r.get("season", 0)) in allowed_years
    ]
    current = [r for r in stats if int(r["season"]) == election.year]
    # MLB Stats API sport IDs used here are ordered from MLB (1) down through
    # AAA (11), AA (12), A (13), and Rookie (14). The smallest represented ID
    # is therefore the highest level reached in the season.
    level = min((int(r.get("sport_id") or 0) for r in current
                 if int(r.get("sport_id") or 0) > 0), default=0)
    pitching = [r for r in current if r.get("group") == "pitching"]

    def number(value):
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0

    def total(group_rows, key):
        return sum(number((r.get("stat") or {}).get(key, 0))
                   for r in group_rows)

    def innings(rows):
        return sum(innings_outs(str((r.get("stat") or {}).get(
            "inningsPitched", "0.0"))) for r in rows) / 3

    level_rows = [r for r in current if r.get("sport_id") == level]
    level_hit = [r for r in level_rows if r.get("group") == "hitting"]
    level_pitch = [r for r in level_rows if r.get("group") == "pitching"]
    pa = total(level_hit, "plateAppearances")
    walks = total(level_hit, "baseOnBalls")
    strikeouts = total(level_hit, "strikeOuts")
    ip = innings(level_pitch)
    p_strikeouts = total(level_pitch, "strikeOuts")
    p_walks = total(level_pitch, "baseOnBalls")
    batters = total(level_pitch, "battersFaced")
    mlb_y = [r for r in current if r.get("sport_id") == 1]
    mlb_appearance_y = any(
        number((r.get("stat") or {}).get("gamesPlayed", 0)) > 0
        for r in mlb_y
    )
    prior = [r for r in stats if int(r["season"]) == election.year - 1
             and r.get("sport_id") == 1]
    return {
        "person_id": player_id,
        "age": age_on(birth_date, election),
        "highest_level": level,
        "season_stats": stats,
        "player_type": "pitcher" if pitching else "hitter",
        "pa": pa,
        "ops": max((number((r.get("stat") or {}).get("ops", 0))
                    for r in level_hit), default=0.0),
        "bb_pct": walks / pa if pa else 0.0,
        "k_pct": strikeouts / pa if pa else 0.0,
        "ip": ip,
        "k_bb_pct": ((p_strikeouts - p_walks) / batters
                     if batters else 0.0),
        "era": max((number((r.get("stat") or {}).get("era", 0))
                    for r in level_pitch), default=0.0),
        "mlb_pa_y": total(
            [r for r in mlb_y if r.get("group") == "hitting"],
            "plateAppearances",
        ),
        "mlb_appearance_y": mlb_appearance_y,
        "mlb_ip_y": innings([r for r in mlb_y
                             if r.get("group") == "pitching"]),
        "mlb_pa_y1": total(
            [r for r in prior if r.get("group") == "hitting"],
            "plateAppearances",
        ),
        "mlb_ip_y1": innings(
            [r for r in prior if r.get("group") == "pitching"]
        ),
        "transactions_as_of": transactions_before,
    }


def outcome(mlb_stats, year):
    """Return outcomes, applying the prespecified scale for 2020."""
    scale = 60 / 162 if year == 2019 else 1
    pa = sum(
        float(r.get("stat", {}).get("plateAppearances", 0) or 0)
        for r in mlb_stats
        if r.get("group") == "hitting"
    )
    outs = sum(
        innings_outs(str(r.get("stat", {}).get("inningsPitched", "0.0")))
        for r in mlb_stats
        if r.get("group") == "pitching"
    )
    any_appearance = any(
        float(r.get("stat", {}).get("gamesPlayed", 0) or 0) > 0
        for r in mlb_stats
    )
    return {
        "positive": pa >= 50 * scale or outs >= 60 * scale,
        "any_appearance": any_appearance,
        "pa": pa,
        "outs": outs,
    }


def primary_segment(row):
    return "pitcher" if row.get("player_type") == "pitcher" else "hitter"


def rank(rows, method):
    """Stable rank ordering; API sport level IDs are used as level proxy."""

    def number(row, *keys):
        return next(
            (float(row[k]) for k in keys if row.get(k) is not None), 0.0
        )

    def level_score(row):
        return number(row, "highest_level")

    def score(row):
        pa = number(row, "mlb_pa_y")
        ip = number(row, "mlb_ip_y")
        age = number(row, "age")
        hitter = primary_segment(row) == "hitter"
        if method == "B0":
            return (-(pa + ip), level_score(row) or 999, age if row.get("age") is not None else float("inf"), int(row["person_id"]))
        if method == "B1":
            return (
                level_score(row) or 999,
                -number(row, "ops" if hitter else "k_bb_pct"),
                age if row.get("age") is not None else float("inf"),
                int(row["person_id"]),
            )
        if method == "B2":
            return (-number(row, "b2_probability"), int(row["person_id"]))
        if method == "P":
            return (
                not bool(row.get("met_threshold_y")),
                int(row["person_id"]),
            )
        if method == "M":
            return (-number(row, "m_probability"), int(row["person_id"]))
        raise ValueError("unknown ranking: " + method)

    return sorted(rows, key=score)


def attach_features(cohort, people, stats_rows, transaction_rows):
    """Build ID-joined decision rows; names are never read or emitted."""
    people_by_id = {row.get("person_id"): row for row in people
                    if row.get("person_id") is not None}
    output = []
    missing_birth_date = 0
    missing_person = 0
    for member in cohort:
        person_id = member["person_id"]
        person = people_by_id.get(person_id)
        if not person:
            missing_person += 1
            continue
        if not person.get("birth_date"):
            missing_birth_date += 1
            birth_date = "2000-01-01"
        else:
            birth_date = person["birth_date"]
        features = as_of_features(
            person_id, member["date"], birth_date, stats_rows,
            transaction_rows,
        )
        if not person.get("birth_date"):
            features["age"] = None
        features["no_mlb_appearance_y"] = not features["mlb_appearance_y"]
        output.append({**features, "election_date": member["date"]})
    return output, {"missing_person": missing_person,
                    "missing_birth_date": missing_birth_date}


def coverage(pool, features, attach_reasons=None):
    """Summarize mutually exclusive reasons for missing season-Y features."""
    by_id = {row["person_id"]: row for row in features}
    reasons = {
        "no_season_y_stats_in_cached_levels": 0,
        "person_record_missing": 0,
    }
    del attach_reasons  # Missing rows are classified from the joined result.
    no_mlb = 0
    known_mlb = 0
    for member in pool:
        row = by_id.get(member["person_id"])
        if row is None:
            reasons["person_record_missing"] += 1
            continue
        if not any(int(stat.get("season", 0)) == int(member["date"][:4])
                   for stat in row.get("season_stats", [])):
            reasons["no_season_y_stats_in_cached_levels"] += 1
        else:
            known_mlb += 1
            if row["mlb_pa_y"] == 0 and row["mlb_ip_y"] == 0:
                no_mlb += 1
    unmatched = sum(reasons.values())
    matched = len(pool) - unmatched
    return {"pool_size": len(pool), "matched": matched,
            "unmatched": unmatched, "unmatched_reasons": reasons,
            "no_mlb_in_y": no_mlb,
            "no_mlb_in_y_known_denominator": known_mlb,
            "no_mlb_in_y_share": no_mlb / known_mlb if known_mlb else None}
