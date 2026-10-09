"""Readable Markdown from the compact publication summary."""

import re


METHODS = {
    "MILBFA": (
        "Election descriptions contain elected free agency in November "
        "and December. A classifies fromTeam/toTeam against season team "
        "lists: MLB takes precedence, then minor, else unresolved. B "
        "uses hitting/pitching season splits for each queried sport: "
        "MLB appearance takes precedence; otherwise minor appearance "
        "with all sport queries returned is a minor proxy. Agreement "
        "and disagreement exclude unresolved rows. minor_only_proxy "
        "counts elections where both methods say minor, not unique "
        "players and not confirmed contracts. Missing MLB stats can "
        "create false minor proxies; rehab, injured players, team "
        "attribution, prior MLB veterans, omitted leagues and incomplete "
        "histories prevent reliable contract separation."
    ),
    "RULE5": (
        "Within each year, identifiers are code/description groups "
        "having at least one description containing Rule 5 or Rule V. "
        "All rows in those groups are candidates; text_matched_events "
        "is the narrower count. Group examples include transaction id, "
        "date and real description. Code reuse may create false "
        "positives; "
        "missing text creates false negatives. The same derivation "
        "applies across years, including DR. Monthly ID union equality "
        "tests one truncation risk; shared omissions remain possible."
    ),
    "CALLUP": (
        "Selection takes the first hitting season leaderboard row "
        "ordered by plateAppearances descending with limit=1 for each "
        "queried season and sport. Ties follow API ordering. This is "
        "non-random. Dated splits are filtered to returned season and "
        "sport; through_june counts dates on or before June 30 locally. "
        "These are split counts, not guaranteed unique games. The "
        "small-sample design cannot receive FEASIBLE regardless of "
        "observed success."
    ),
}


def md_escape(value):
    """Keep untrusted values on one line and escape Markdown punctuation."""
    if value is None:
        return "UNKNOWN"
    text = " ".join(str(value).splitlines())
    text = text.replace("\\", "\\\\")
    return re.sub(r"([`*_{}\[\]()<>#+.!|~&=\-–—])", r"\\\1", text)


def cell(value):
    if isinstance(value, dict):
        return "; ".join(
            md_escape(k) + ": " + cell(v) for k, v in value.items()
        )
    if isinstance(value, list):
        return "; ".join(cell(v) for v in value) or "none"
    return md_escape(value)


def table(rows, fields):
    return [
        "| " + " | ".join(fields) + " |",
        "| " + " | ".join("---" for _ in fields) + " |",
    ] + [
        "| " + " | ".join(cell(row.get(k)) for k in fields) + " |"
        for row in rows
    ]


def render(summary):
    if summary is None:
        return (
            "UNKNOWN: The live probe was not run. No measured counts "
            "or assessments are available.\n"
        )
    lines = [
        "# Feasibility measurements",
        "",
        "FACT: Query references are SHA-256 hashes of the query object "
        "(endpoint and params), serialized with Python json.dumps "
        "and sort_keys=True. Match them to raw_manifest.json metadata.",
        "",
        "UNKNOWN: Failed requests: " + str(summary["failure_count"]) + ".",
        "",
    ]
    for candidate, study in summary["candidates"].items():
        lines += [
            "## " + candidate,
            "",
            "FACT: Measured counts by season.",
            "",
        ]
        rows = study["rows"]
        if rows:
            if candidate == "MILBFA":
                counts = [
                    {"season": row["season"], **row["counts"]} for row in rows
                ]
                fields = [k for k in counts[0] if k not in ("A", "B")]
                lines += table(rows, ["season", "matched_events"]) + [""]
                lines += table(counts, ["season", "A", "B"]) + [""]
                lines += table(counts, fields) + [""]
            else:
                fields = [k for k in rows[0] if k != "query_refs"]
                lines += table(rows, fields) + [""]
        else:
            lines += ["UNKNOWN: No measured cells.", ""]
        lines += [
            "INFERENCE: Verdict **"
            + study["verdict"]
            + "**. "
            + study["reason"],
            "",
            "INFERENCE: Method and limitations: " + METHODS[candidate],
            "",
            "FACT: Query references for each season/level are in "
            "this candidate’s rows in summary.json (query_refs).",
            "",
        ]
        if candidate == "RULE5":
            lines += [
                "UNKNOWN: DR rows without Rule 5 text cannot be "
                "assigned to Rule 5 on code alone. Seasons with no "
                "derived identifier have unknown Rule 5 coverage.",
                "",
            ]
        if study["examples"]:
            lines += ["FACT: Short examples (at most five per candidate).", ""]
            lines += table(study["examples"], ["record", "query"]) + [""]
        lines += [
            "UNKNOWN: Unmeasured seasons or levels are not zero counts. "
            "Missing values are shown as UNKNOWN.",
            "",
        ]
    lines += [
        "UNKNOWN: Historical publication times and retroactive "
        "corrections are not measured. Current API responses do not "
        "establish what was available at a past decision date. No "
        "population completeness or contract-status guarantee is made. "
        "Retrieval UTC and response hashes are in raw_manifest.json; "
        "bulk inputs remain in ignored local data/.",
        "",
    ]
    return "\n".join(lines)
