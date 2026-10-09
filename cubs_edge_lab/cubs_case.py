"""Build an additive, offline Cubs signing opportunity description."""

from datetime import date as calendar_date
import hashlib
import json
from pathlib import Path
import re

from .triage import outcome
from .triage_config import INVITATION_PATTERN, MINOR_CONTRACT_PATTERN

YEARS = (2021, 2022, 2023, 2024)
TEAM_ID = 112
DATA_SOURCE = "MLBAM, MLB Stats API; cached local responses"
AS_OF_DATE = "2026-10-09"


def _read_json(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError) as exc:
        raise RuntimeError("unable to read valid JSON: " + str(path)) from exc


def _transaction_rows(root, year):
    manifest = _read_json(Path(root) / "research/raw_manifest.json")
    start, end = f"{year}-11-01", f"{year + 1}-03-31"
    matches = [
        item
        for item in manifest
        if item.get("endpoint", "").endswith("/transactions")
        and item.get("params")
        == {"teamId": TEAM_ID, "startDate": start, "endDate": end}
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"expected one cached Cubs transaction window for {year}"
        )
    item = matches[0]
    path = Path(root) / item["file"]
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != item.get("sha256"):
        raise RuntimeError(
            "cached Cubs transaction checksum mismatch: " + str(path)
        )
    try:
        payload = json.loads(raw)
    except ValueError as exc:
        raise RuntimeError(
            "invalid cached transaction JSON: " + str(path)
        ) from exc
    if not isinstance(payload.get("transactions"), list):
        raise RuntimeError(
            "cached transaction response has no transactions list"
        )
    return payload["transactions"]


def _stats_by_person(root, season):
    result = {}
    for group in ("hitting", "pitching"):
        path = Path(root) / "data/stats" / f"{season}_1_{group}.json"
        artifact = _read_json(path)
        if int(artifact.get("season", -1)) != season:
            raise RuntimeError("stats artifact season mismatch: " + str(path))
        if artifact.get("truncated") or artifact.get("coverage_unknown"):
            raise RuntimeError("incomplete outcome stats: " + str(path))
        for row in artifact.get("rows", []):
            person_id = row.get("person_id")
            if person_id is not None:
                result.setdefault(person_id, []).append(row)
    return result


def _signed_person_dates(transactions, cohort, year):
    players = {}
    for source in cohort.get("features", []):
        person_id = source.get("person_id")
        election_date = source.get("election_date")
        if person_id is None or election_date is None:
            raise ValueError(
                "cohort player is missing person ID or election date"
            )
        try:
            calendar_date.fromisoformat(election_date)
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid player election date") from exc
        if person_id in players and players[person_id] != election_date:
            raise ValueError(
                "conflicting election dates for person " + str(person_id)
            )
        players[person_id] = election_date

    signed = {}
    end = f"{year + 1}-03-31"
    for transaction in transactions:
        person_id = (transaction.get("person") or {}).get("id")
        transaction_date = transaction.get("date")
        description = transaction.get("description") or ""
        qualifies = bool(
            re.search(MINOR_CONTRACT_PATTERN, description, re.I)
            or re.search(INVITATION_PATTERN, description, re.I)
        )
        if person_id not in players or not qualifies:
            continue
        if not transaction_date:
            raise ValueError("qualifying transaction is missing its date")
        try:
            calendar_date.fromisoformat(transaction_date)
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid qualifying transaction date") from exc
        if players[person_id] <= transaction_date <= end:
            signed[person_id] = min(
                transaction_date, signed.get(person_id, transaction_date)
            )
    return signed


def calculate(root):
    """Return counts from only the four allowed cohorts and cached sources."""
    root = Path(root)
    validation = _read_json(root / "research/validation.json")
    rows, examples = [], []
    for year in YEARS:
        cohort = _read_json(root / "data/cohorts" / f"{year}.json")
        if int(cohort.get("year", -1)) != year:
            raise RuntimeError("cohort year mismatch: " + str(year))
        transactions = _transaction_rows(root, year)
        signed = _signed_person_dates(transactions, cohort, year)
        outcomes_by_person = _stats_by_person(root, year + 1)
        people = {}
        for source in cohort.get("features", []):
            person_id = source.get("person_id")
            if person_id is None:
                continue
            if person_id in people:
                continue
            people[person_id] = source
        no_mlb_people = {
            person_id: source
            for person_id, source in people.items()
            if bool(source.get("no_mlb_appearance_y"))
        }
        positives = {
            person_id
            for person_id in people
            if outcome(
                outcomes_by_person.get(person_id, []), year + 1
            )["positive"]
        }
        no_mlb_positives = positives & set(no_mlb_people)
        signed_positive = set(signed) & positives
        signed_no_mlb = set(signed) & set(no_mlb_people)
        signed_no_mlb_positive = signed_no_mlb & no_mlb_positives
        base = (
            validation.get("base_rates", {})
            .get(str(year), {})
            .get("primary", {})
        )
        if "positives" not in base:
            raise RuntimeError(
                "validation base rate is missing for cohort " + str(year)
            )
        league_positives = int(base["positives"])
        rows.append(
            {
                "cohort_year": year,
                "outcome_season": year + 1,
                "cubs_signed": len(signed),
                "cubs_signed_outcome_positive": len(signed_positive),
                "cubs_signed_no_mlb_in_y": len(signed_no_mlb),
                "cubs_signed_no_mlb_in_y_outcome_positive": len(
                    signed_no_mlb_positive
                ),
                "league_no_mlb_in_y_outcome_positive": league_positives,
                "share_of_league_no_mlb_positives": (
                    len(signed_no_mlb_positive) / league_positives
                    if league_positives
                    else None
                ),
                "share_display": (
                    f"{len(signed_no_mlb_positive) / league_positives:.6f}"
                    if league_positives
                    else "UNKNOWN"
                ),
            }
        )
        for person_id in sorted(signed_no_mlb_positive):
            if len(examples) == 5:
                break
            examples.append(
                {
                    "cohort_year": year,
                    "person_id": person_id,
                    "election_date": people[person_id]["election_date"],
                    "signing_date": signed[person_id],
                    "outcome_season": year + 1,
                }
            )
    return {
        "as_of_date": AS_OF_DATE,
        "source": DATA_SOURCE,
        "team_id": TEAM_ID,
        "cohort_years": list(YEARS),
        "thresholds": {"pa": 50, "ip": 20},
        "signing_window": (
            "player election date through March 31 of cohort year + 1, "
            "inclusive"
        ),
        "matching_rules": {
            "minor_contract_regex": MINOR_CONTRACT_PATTERN,
            "spring_invitation_regex": INVITATION_PATTERN,
            "case_insensitive": True,
        },
        "join_key": "person_id only",
        "method_status": _method_status(validation),
        "interpretation": (
            "illustrates the size of the opportunity only; "
            "not a recommendation"
        ),
        "unknowns": ["availability", "contract terms", "competing offers"],
        "cohorts": rows,
        "examples": examples,
    }


def _method_status(validation):
    """Derive the report wording from the recorded validation stop."""
    if (
        validation.get("early_stop") is True
        and validation.get("validation") is None
        and validation.get("early_stop_reason")
        == "validation primary positives below 30"
    ):
        return "failed its pre-registered test"
    return "did not record the pre-registered early-stop failure"


def render_section(payload):
    """Render every numeric claim from the supplied case payload."""
    lines = [
        "## Cubs case (descriptive)",
        "",
        (
            f"FACT: Dated {payload['as_of_date']}; "
            f"source: {payload['source']}; "
            f"Cubs team ID {payload['team_id']}."
        ),
        (
            f"FACT: Cohorts: {', '.join(map(str, payload['cohort_years']))}; "
            f"outcome thresholds: at least {payload['thresholds']['pa']} MLB "
            f"PA or {payload['thresholds']['ip']} MLB IP in the following "
            "season, any club."
        ),
        (
            "FACT: A qualifying Cubs transaction matches the recorded "
            "minor-contract or spring-invitation rules and falls within the "
            "player's election-date-through-March-31 window, inclusive; "
            f"joins use {payload['join_key']}."
        ),
        "",
        "FACT: Counts and shares by cohort are:",
        "| Evidence | Cohort | Outcome season | Cubs signed | "
        "Signed, positive | "
        "No MLB in Y signed | No MLB in Y signed, positive | "
        "League no-MLB-in-Y positives | Cubs share of those positives |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in payload["cohorts"]:
        share = row["share_display"]
        lines.append(
            "| FACT | "
            f"{row['cohort_year']} | {row['outcome_season']} | "
            f"{row['cubs_signed']} | {row['cubs_signed_outcome_positive']} | "
            f"{row['cubs_signed_no_mlb_in_y']} | "
            f"{row['cubs_signed_no_mlb_in_y_outcome_positive']} | "
            f"{row['league_no_mlb_in_y_outcome_positive']} | {share} |"
        )
    lines.extend(
        [
            "",
            f"FACT: The method {payload['method_status']}.",
            f"INFERENCE: This case {payload['interpretation']}.",
            "UNKNOWN: Availability, contract terms, and competing offers "
            "are unknown.",
            "FACT: Examples below are limited to five and identify people "
            "by person ID with source dates.",
        ]
    )
    for example in payload["examples"]:
        lines.append(
            f"FACT: Cohort {example['cohort_year']}, person ID "
            f"{example['person_id']}: election {example['election_date']}, "
            f"Cubs transaction {example['signing_date']}, outcome season "
            f"{example['outcome_season']}."
        )
    return "\n".join(lines) + "\n"


def write_artifacts(root):
    """Write only the new JSON and append its generated section."""
    root = Path(root)
    payload = calculate(root)
    json_path = root / "research/cubs_case.json"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    report_path = root / "research/EXPERIMENT.md"
    report = report_path.read_text()
    marker = "## Cubs case (descriptive)"
    if report.count(marker) > 1:
        raise RuntimeError("report contains duplicate Cubs case sections")
    if marker in report:
        report = report[: report.index(marker)].rstrip() + "\n\n"
    report_path.write_text(report.rstrip() + "\n\n" + render_section(payload))
    return payload
