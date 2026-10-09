"""Commands for the free-agent triage experiment."""

import argparse
import calendar
import json
import statistics
from pathlib import Path
import re

from .probe.client import Client, atomic_json
from .probe.parse import transactions
from .probe.parse import stats as parse_stats
from .triage import attach_features, coverage, select_cohort
from .triage_config import (
    COHORT_YEARS,
    INVITATION_PATTERN,
    MINOR_CONTRACT_PATTERN,
    OTHER_SIGNING_PATTERN,
    SPORT_IDS,
    STAT_YEARS,
)
from .triage_eval import preregistration_payload

PAGE_SIZE = 1000
MAX_NEW_REQUESTS = 220


def median_k_basis(counts):
    return statistics.median(counts) if counts else None


def request_guard(endpoint, params):
    if endpoint == "stats" and int(params.get("season", 0)) >= 2026:
        raise ValueError("season-2026 and later stats requests are prohibited")


def cached_people_by_id(root, entries):
    """Read birth dates from successful cached /people responses by ID."""
    people_by_id = {}
    for entry in entries:
        if (
            entry.get("endpoint", "").rstrip("/").endswith("/people")
            and entry.get("http_status") == 200
        ):
            cached = Path(root) / entry["file"]
            if not cached.is_file():
                continue
            payload = json.loads(cached.read_text())
            for person in payload.get("people", []):
                person_id = person.get("id")
                if person_id is not None:
                    people_by_id[person_id] = {
                        "person_id": person_id,
                        "birth_date": person.get("birthDate"),
                    }
    return people_by_id


def fetch(client):
    """Fetch configured seasons; the caller owns the cache root."""
    if max(STAT_YEARS) >= 2026:
        raise ValueError("season-2026 requests are prohibited")
    for season in STAT_YEARS:
        for sport in SPORT_IDS:
            for group in ("hitting", "pitching"):
                params = {
                    "stats": "season",
                    "group": group,
                    "season": season,
                    "sportIds": sport,
                    "playerPool": "ALL",
                    "limit": PAGE_SIZE,
                }
                offset = 0
                collected = []
                expected = None
                while True:
                    page_params = {**params, "offset": offset}
                    request_guard("stats", page_params)
                    payload = client.get("stats", **page_params)
                    page_rows = parse_stats(payload) or []
                    collected.extend(page_rows)
                    groups = payload.get("stats") or []
                    totals = [
                        int(g.get("totalSplits", 0) or 0)
                        for g in groups
                        if isinstance(g, dict)
                    ]
                    if totals:
                        expected = max(totals)
                    if (
                        not page_rows
                        or (
                            expected is not None and len(collected) >= expected
                        )
                        or len(page_rows) < PAGE_SIZE
                    ):
                        break
                    offset += len(page_rows)
                record = {
                    "season": season,
                    "sport_id": sport,
                    "group": group,
                    "rows": collected,
                    "expected": expected,
                    "truncated": expected is not None
                    and len(collected) < expected,
                    "coverage_unknown": expected is None,
                }
                path = (
                    client.root
                    / "data"
                    / "stats"
                    / f"{season}_{sport}_{group}.json"
                )
                atomic_json(path, record)
    for year in COHORT_YEARS:
        tx = client.get(
            "transactions", startDate=f"{year}-11-01", endDate=f"{year}-12-31"
        )
        select_cohort(transactions(tx), year)
    for year in range(2021, 2026):
        for month, season in (
            (11, year),
            (12, year),
            (1, year + 1),
            (2, year + 1),
            (3, year + 1),
        ):
            last = calendar.monthrange(season, month)[1]
            client.get(
                "transactions",
                teamId=112,
                startDate=f"{season}-{month:02d}-01",
                endDate=f"{season}-{month:02d}-{last}",
            )
        client.get(
            "transactions",
            teamId=112,
            startDate=f"{year}-11-01",
            endDate=f"{year + 1}-03-31",
        )


def build_cohorts(root):
    root = Path(root)
    # Reuse the successfully cached /people batches recorded in the manifest.
    # Keeping this cache-backed avoids a second request when data artifacts are
    # rebuilt and ensures ages are joined strictly by MLB person ID.
    client = Client(root, offline=True)
    people_by_id = cached_people_by_id(root, client.entries)
    for year in COHORT_YEARS:
        payload = Client(root, offline=True).get(
            "transactions", startDate=f"{year}-11-01", endDate=f"{year}-12-31"
        )
        pool, null_rows = select_cohort(transactions(payload), year)
        all_stats = []
        for season in (year - 1, year):
            for sport in SPORT_IDS:
                for group in ("hitting", "pitching"):
                    path = (
                        root
                        / "data"
                        / "stats"
                        / f"{season}_{sport}_{group}.json"
                    )
                    if path.exists():
                        all_stats.extend(json.loads(path.read_text())["rows"])
        people = [
            people_by_id[row["person_id"]]
            for row in pool
            if row["person_id"] in people_by_id
        ]
        features, reasons = attach_features(pool, people, all_stats, [])
        cov = coverage(pool, features, reasons)
        cov["null_person_transaction_rows"] = null_rows
        result = {
            "year": year,
            "pool": pool,
            "features": features,
            "coverage": cov,
            "null_person_transaction_rows": null_rows,
        }
        atomic_json(root / "data" / "cohorts" / f"{year}.json", result)
    return True


def generate_report(root):
    root = Path(root)
    coverage_data = {}
    stats_coverage = []
    for season in STAT_YEARS:
        for sport in SPORT_IDS:
            for group in ("hitting", "pitching"):
                path = (
                    root / "data" / "stats" / f"{season}_{sport}_{group}.json"
                )
                if not path.exists():
                    stats_coverage.append(
                        {
                            "season": season,
                            "sport_id": sport,
                            "group": group,
                            "status": "UNKNOWN",
                            "reason": "cached stats artifact missing",
                        }
                    )
                    continue
                artifact = json.loads(path.read_text())
                status = (
                    "UNKNOWN"
                    if artifact.get("coverage_unknown")
                    else "TRUNCATED"
                    if artifact.get("truncated")
                    else "COMPLETE"
                )
                stats_coverage.append(
                    {
                        "season": season,
                        "sport_id": sport,
                        "group": group,
                        "status": status,
                        "rows": len(artifact.get("rows", [])),
                        "expected": artifact.get("expected"),
                    }
                )
    for year in COHORT_YEARS:
        path = root / "data" / "cohorts" / f"{year}.json"
        coverage_data[str(year)] = (
            json.loads(path.read_text())["coverage"]
            if path.exists()
            else {"status": "UNKNOWN", "reason": "cohort cache missing"}
        )
    client = Client(root, offline=True)
    cubs = [cubs_signings(client, year) for year in range(2021, 2026)]
    combined = [
        r["minor_contracts"] + r["spring_invitations"] - r["overlap"]
        for r in cubs
    ]
    unknown_age = {}
    for year in COHORT_YEARS:
        cohort_path = root / "data" / "cohorts" / f"{year}.json"
        if cohort_path.exists():
            cohort = json.loads(cohort_path.read_text())
            unknown_age[str(year)] = sum(
                feature.get("age") is None
                for feature in cohort.get("features", [])
            )
    payload = {
        "label": "FACT",
        "cohorts": coverage_data,
        "cubs": cubs,
        "stats_coverage": stats_coverage,
        "k_basis": median_k_basis(combined),
        "age_status": {
            "label": "FACT" if not any(unknown_age.values()) else "UNKNOWN",
            "unknown_by_cohort": unknown_age,
            "reason": (
                "birthDate absent from successful cached /people records"
                if any(unknown_age.values())
                else None
            ),
        },
        "cubs_rules": {
            "minor_contract": MINOR_CONTRACT_PATTERN,
            "invitation": INVITATION_PATTERN,
            "unmatched_signing_like": OTHER_SIGNING_PATTERN,
        },
    }
    atomic_json(root / "research" / "data_summary.json", payload)
    lines = [
        "# Data acquisition report",
        "",
        "FACT: Measured values below are generated from cached API "
        "responses. No outcome labels are included.",
        "",
        "## League-wide statistics acquisition",
        "",
    ]
    for row in stats_coverage:
        if row["status"] == "COMPLETE":
            lines.append(
                f"- FACT: season {row['season']}, sport {row['sport_id']}, "
                f"{row['group']}: {row['rows']} rows; "
                f"expected {row['expected']}."
            )
        else:
            reason = row.get("reason")
            if reason is None:
                reason = (
                    f"{row['status']} with {row.get('rows')} of "
                    f"{row.get('expected')} rows"
                )
            lines.append(
                f"- UNKNOWN: season {row['season']}, "
                f"sport {row['sport_id']}, {row['group']}: "
                f"{reason}."
            )
    lines.extend(["", "## Cohort coverage", ""])
    for year, data in coverage_data.items():
        if "pool_size" not in data:
            lines.append(f"- UNKNOWN: cohort {year}: {data['reason']}.")
        else:
            age_unknown = unknown_age.get(year, 0)
            lines.append(
                f"- FACT: {year}: pool {data['pool_size']}, "
                f"matched {data['matched']}, unmatched "
                f"{data['unmatched']} "
                f"({json.dumps(data['unmatched_reasons'], sort_keys=True)}); "
                f"no MLB appearance in Y {data['no_mlb_in_y']} of "
                f"{data['no_mlb_in_y_known_denominator']} matched with "
                f"season-Y stats ({data['no_mlb_in_y_share']}); age "
                f"unknown for {age_unknown} cohort features."
            )
            if data.get("null_person_transaction_rows"):
                lines.append(
                    f"  UNKNOWN: {data['null_person_transaction_rows']} "
                    "qualifying transaction rows have no person ID and "
                    "are excluded from the deduplicated pool."
                )
    lines.extend(
        [
            "",
            "## Cubs offseason signings",
            "",
            f"FACT: Minor-league contracts match `{MINOR_CONTRACT_PATTERN}`; "
            f"invitations match `{INVITATION_PATTERN}`, case-insensitively. "
            "Combined count is the union. The 5 seasonal counts are the "
            "2021-22 through 2025-26 windows.",
            "INFERENCE: The initial invitation expression was "
            "`\\b(?:non[ -]roster invit\\w*|spring training invit\\w*)`; "
            "observed descriptions also phrased invitations as `invited to "
            "spring training/camp`, so the measured expression was extended "
            "to cover that wording.",
            "",
            "### Observed transaction type groups",
            "",
        ]
    )
    for row in cubs:
        lines.append(
            f"- FACT: {row['year']}-{row['year'] + 1}: "
            + "; ".join(
                f"{g['type_code']}/{g['type_desc']} ({g['row_count']})"
                for g in row["groups"]
            )
        )
    lines.extend(["", "### Counts and attributed examples", ""])
    for row in cubs:
        lines.append(
            f"- FACT: {row['year']}-{row['year'] + 1}: minor "
            f"{row['minor_contracts']}, invitations "
            f"{row['spring_invitations']}, overlap {row['overlap']}, "
            f"combined {row['combined']}, unmatched signing-like "
            f"{row['other_signing_unmatched']}."
        )
        lines.append(
            "  Examples (transaction ID, date, type code, match status): "
            + json.dumps(row["examples"])
        )
        if not row["monthly_union_matches"]:
            lines.append(
                f"  UNKNOWN: monthly query union differed from "
                f"full-window query (monthly-only "
                f"{row['monthly_only_ids']}; full-window-only "
                f"{row['full_window_only_ids']})."
            )
    lines.append(
        f"- FACT: k_basis median combined count: {payload['k_basis']}."
    )
    if payload["age_status"]["label"] == "UNKNOWN":
        lines.append(
            "- UNKNOWN: Some birth dates were absent from successful "
            "cached /people records: "
            + json.dumps(unknown_age, sort_keys=True)
            + "."
        )
    else:
        lines.append(
            "- FACT: Election-date ages were calculated from birthDate "
            "values in cached /people responses joined by person ID."
        )
    (root / "research" / "DATA.md").write_text("\n".join(lines) + "\n")
    return payload


def cubs_signings(client, year):
    """Count candidate signing transaction descriptions using frozen rules."""
    from collections import defaultdict

    union = {}
    monthly = []
    for month in range(11, 13):
        start = f"{year}-{month:02d}-01"
        end_day = 30 if month == 11 else 31
        rows = transactions(
            client.get(
                "transactions",
                teamId=112,
                startDate=start,
                endDate=f"{year}-{month:02d}-{end_day}",
            )
        )
        monthly.extend(rows)
        union.update((row["id"], row) for row in rows if row["id"] is not None)
    # Dec-Jan-Mar offseason window, queried month-by-month.
    next_year = year + 1
    for month, season in ((1, next_year), (2, next_year), (3, next_year)):
        end_day = calendar.monthrange(season, month)[1]
        rows = transactions(
            client.get(
                "transactions",
                teamId=112,
                startDate=f"{season}-{month:02d}-01",
                endDate=f"{season}-{month:02d}-{end_day}",
            )
        )
        monthly.extend(rows)
        union.update((row["id"], row) for row in rows if row["id"] is not None)
    full_rows = transactions(
        client.get(
            "transactions",
            teamId=112,
            startDate=f"{year}-11-01",
            endDate=f"{next_year}-03-31",
        )
    )
    full_ids = {row["id"] for row in full_rows if row["id"] is not None}
    monthly_ids = {row["id"] for row in monthly if row["id"] is not None}
    groups = defaultdict(list)
    for row in union.values():
        groups[(row["code"], row["type_desc"])].append(row)
    minor, invit, examples = [], [], []
    unmatched_examples = []
    for row in union.values():
        desc = row.get("description") or ""
        is_minor = bool(re.search(MINOR_CONTRACT_PATTERN, desc, re.I))
        is_invit = bool(re.search(INVITATION_PATTERN, desc, re.I))
        if is_minor:
            minor.append(row)
        if is_invit:
            invit.append(row)
        if (
            re.search(OTHER_SIGNING_PATTERN, desc, re.I)
            and not (is_minor or is_invit)
            and len(unmatched_examples) < 5
        ):
            unmatched_examples.append(
                {
                    "id": row["id"],
                    "date": row["date"],
                    "type_code": row.get("code"),
                    "match_status": "unmatched_signing_like",
                }
            )
        if (is_minor or is_invit) and len(examples) < 5:
            examples.append(
                {
                    "id": row["id"],
                    "date": row["date"],
                    "type_code": row.get("code"),
                    "match_status": "matched",
                }
            )
    return {
        "year": year,
        "minor_contracts": len(minor),
        "spring_invitations": len(invit),
        "overlap": sum(
            bool(
                re.search(
                    MINOR_CONTRACT_PATTERN, r.get("description") or "", re.I
                )
            )
            and bool(
                re.search(INVITATION_PATTERN, r.get("description") or "", re.I)
            )
            for r in union.values()
        ),
        "other_signing_unmatched": sum(
            bool(
                re.search(
                    OTHER_SIGNING_PATTERN, r.get("description") or "", re.I
                )
                and not re.search(
                    MINOR_CONTRACT_PATTERN + "|" + INVITATION_PATTERN,
                    r.get("description") or "",
                    re.I,
                )
            )
            for r in union.values()
        ),
        "monthly_union_matches": monthly_ids == full_ids,
        "monthly_only_ids": len(monthly_ids - full_ids),
        "full_window_only_ids": len(full_ids - monthly_ids),
        "combined": len(set(r.get("id") for r in minor + invit)),
        "groups": [
            {
                "type_code": key[0],
                "type_desc": key[1],
                "row_count": len(rows),
            }
            for key, rows in sorted(groups.items(), key=lambda x: str(x[0]))
        ],
        "examples": (examples + unmatched_examples)[:5],
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("fetch")
    run.add_argument("--root", type=Path, default=Path.cwd())
    data = sub.add_parser("data")
    data.add_argument("--root", type=Path, default=Path.cwd())
    pre = sub.add_parser("preregister")
    pre.add_argument("--root", type=Path, default=Path.cwd())
    evaluation = sub.add_parser("evaluate")
    evaluation.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    if args.command == "evaluate":
        from .triage_experiment import evaluate
        from .triage_report import render

        root = args.root
        payload = evaluate(root)
        research = root / "research"
        research.mkdir(parents=True, exist_ok=True)
        atomic_json(research / "validation.json", payload)
        report = render(payload)
        target = research / "EXPERIMENT.md"
        temporary = target.with_suffix(".md.tmp")
        temporary.write_text(report)
        temporary.replace(target)
        return 0
    if args.command == "preregister":
        validation = args.root / "research/validation.json"
        if not validation.is_file():
            raise SystemExit("validation.json is required")
        if json.loads(validation.read_text()).get("early_stop"):
            raise SystemExit("validation early-stop prevents preregistration")
        payload = preregistration_payload(args.root)
        atomic_json(args.root / "research/preregistration.json", payload)
        return 0
    if args.command == "data":
        build_cohorts(args.root)
        generate_report(args.root)
        return 0
    fetch(Client(args.root, request_cap=MAX_NEW_REQUESTS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
