"""Exploratory whole-pool evaluation, isolated from preregistered results."""

import argparse
import hashlib
import json
from pathlib import Path

from .probe.client import atomic_json
from .triage_config import L2_GRID, TOP_K
from .triage_eval import MODEL_FEATURES, B2_FEATURES, LogisticModel
from .triage_eval import auc, calibration, choose_comparator, paired_bootstrap
from .triage_experiment import (
    TEST_YEARS,
    TRAIN_YEARS,
    YEARS,
    _metric_rows,
    _round,
    _stats,
)
from .triage import rank

START = "<!-- EXPLORATORY WHOLE POOL START -->"
END = "<!-- EXPLORATORY WHOLE POOL END -->"
PRIMARY_PREFIX_SHA256 = (
    "2a5e2b60432cfb1a8d1586979dd1bb156c4f37be108f1ee31db68ca4f676386e"
)
AUTHORIZATION = (
    "Owner authorization dated 2026-10-09T07:10Z: local-only use of "
    "already-fetched MLB Stats API data; publish aggregates and "
    "short attributed examples only."
)
_MODEL_CACHE = {}


def _fit_cached(training, strength, features):
    # Include feature values so separate fixture/data roots cannot share a
    # stale fit.
    identity = json.dumps(
        [
            {
                "label": bool(row["positive"]),
                "features": [row.get(name) for name in features],
            }
            for row in training
        ],
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    key = (hashlib.sha256(identity.encode()).digest(), strength, features)
    if key not in _MODEL_CACHE:
        if (
            not training
            or len({bool(row["positive"]) for row in training}) < 2
        ):
            _MODEL_CACHE[key] = None
        else:
            _MODEL_CACHE[key] = LogisticModel(strength=strength).fit(
                training, [int(row["positive"]) for row in training], features
            )
    return _MODEL_CACHE[key]


def _rank_eval_cached(rows, training, strength):
    if not rows:
        return {
            "n": 0,
            "positives": 0,
            "base_rate": None,
            "rankings": {},
            "calibration": [],
            "_auc_scores": {},
        }
    model = _fit_cached(training, strength, MODEL_FEATURES)
    probabilities = (
        model.predict_proba(rows, MODEL_FEATURES)
        if model
        else [0.5] * len(rows)
    )
    no_mlb = [row for row in training if row.get("no_mlb_appearance_y")]
    b2_model = _fit_cached(no_mlb, 1.0, B2_FEATURES)
    b2_probabilities = (
        b2_model.predict_proba(rows, B2_FEATURES)
        if b2_model
        else [0.5] * len(rows)
    )
    scored = [
        {**row, "m_probability": p, "b2_probability": b2}
        for row, p, b2 in zip(rows, probabilities, b2_probabilities)
    ]
    labels = [int(row["positive"]) for row in scored]
    metrics, scores_by_method = {}, {}
    for method in ("B0", "B1", "B2", "P", "M"):
        ordered = rank(scored, method)
        ordinal = {
            row["person_id"]: len(ordered) - index
            for index, row in enumerate(ordered)
        }
        scores = (
            [row["m_probability"] for row in scored]
            if method == "M"
            else (
                [float(row.get("met_threshold_y", False)) for row in scored]
                if method == "P"
                else [float(ordinal[row["person_id"]]) for row in scored]
            )
        )
        top = {
            str(k): {
                "hits": sum(bool(row["positive"]) for row in ordered[:k]),
                "precision": sum(bool(row["positive"]) for row in ordered[:k])
                / min(k, len(ordered)),
            }
            for k in TOP_K
        }
        metrics[method] = {"top_k": top, "auroc": auc(labels, scores)}
        scores_by_method[method] = scores
    return {
        "n": len(rows),
        "positives": sum(labels),
        "base_rate": sum(labels) / len(labels),
        "rankings": metrics,
        "calibration": calibration(labels, probabilities),
        "_auc_scores": scores_by_method,
    }


def _deltas(result, rows, seed, resamples):
    labels = [int(row["positive"]) for row in rows]
    scores = result["_auc_scores"]
    return {
        method: paired_bootstrap(
            labels, scores["M"], scores[method], resamples, seed
        )
        for method in ("B0", "B1", "B2", "P")
    }


def evaluate(root, seed=43017, resamples=2000):
    """Read configured cohorts and cached stats; never read 2025 cohort."""
    root = Path(root)
    stats = _stats(root)
    cohorts = {}
    for year in YEARS:
        path = root / "data/cohorts" / f"{year}.json"
        cohort = json.loads(path.read_text())
        cohorts[year] = _metric_rows(root, cohort, stats)

    train = [row for year in TRAIN_YEARS for row in cohorts[year]]
    whole_2024 = cohorts[2024]
    # Grid selection and comparator are both defined on the whole validation
    # pool.
    chosen = max(
        L2_GRID,
        key=lambda strength: (
            _rank_eval_cached(whole_2024, train, strength)["rankings"]["M"][
                "top_k"
            ]["50"]["hits"],
            -L2_GRID.index(strength),
        ),
    )
    validation_whole = _rank_eval_cached(whole_2024, train, chosen)
    comparator = choose_comparator(validation_whole["rankings"])
    populations = ("whole_pool", "pitchers", "hitters")

    def population_rows(year, population):
        if population == "whole_pool":
            return cohorts[year]
        return [
            row
            for row in cohorts[year]
            if (row.get("player_type") == "pitcher")
            == (population == "pitchers")
        ]

    output = {
        "config": {
            "authorization": AUTHORIZATION,
            "cohort_years": list(YEARS),
            "training_years": list(TRAIN_YEARS),
            "rolling_origin_test_years": list(TEST_YEARS),
            "validation_year": 2024,
            "holdout_excluded": 2025,
            "top_k": list(TOP_K),
            "l2_grid": list(L2_GRID),
            "chosen_l2_strength": chosen,
            "bootstrap_resamples": resamples,
            "bootstrap_seed": seed,
            "bootstrap_interval_percentile": 95,
            "comparator_rule": (
                "2024 whole-pool top-50 hits; ties B2, B0, B1, P"
            ),
            "population_assumption": (
                "Whole-pool training for all populations; the 2024-selected "
                "L2 strength is reused for rolling-origin years."
            ),
            "b2_assumption": "B2 trains on no-MLB-in-Y rows only.",
            "source": "MLBAM, MLB Stats API",
        },
        "comparator": comparator,
        "validation": {},
        "rolling_origin": {},
    }
    for year, destination in [(2024, output["validation"])] + [
        (year, output["rolling_origin"].setdefault(str(year), {}))
        for year in TEST_YEARS
    ]:
        if year == 2024:
            training = train
        else:
            training = [
                row
                for earlier in YEARS
                if earlier < year
                for row in cohorts[earlier]
            ]
        for population in populations:
            rows = population_rows(year, population)
            result = _rank_eval_cached(rows, training, chosen)
            result["bootstrap_m_minus_baseline"] = (
                _deltas(result, rows, seed, resamples)
                if rows
                else {
                    method: {
                        "resamples": resamples,
                        "seed": seed,
                        "valid_resamples": 0,
                        "mean_difference": None,
                        "percentile_95": [None, None],
                    }
                    for method in ("B0", "B1", "B2", "P")
                }
            )
            result.pop("_auc_scores", None)
            destination[population] = result
    return _round(output)


def render_section(payload):
    """Render the isolated section using payload values only."""
    config = payload["config"]
    evaluated = ", ".join(map(str, config["cohort_years"]))
    rolling = ", ".join(map(str, config["rolling_origin_test_years"]))
    lines = [
        START,
        "## EXPLORATORY: whole pool",
        "",
        (
            "EXPLORATORY FACT: Cohorts evaluated: "
            + evaluated
            + f"; validation year {config['validation_year']}; "
            + "rolling-origin years "
            + rolling
            + "."
        ),
        (
            "EXPLORATORY FACT: The validation whole-pool comparator was "
            + f"{payload['comparator']}; selected L2 strength was "
            + f"{config['chosen_l2_strength']}."
        ),
        (
            "EXPLORATORY FACT: Source attribution: MLBAM, MLB Stats API. "
            "Only cohort aggregates are reported."
        ),
        (
            "EXPLORATORY FACT: This section supports no usefulness claim "
            "or recommendation."
        ),
        "",
        (
            "EXPLORATORY FACT: Top-k hits, precision, AUROC, calibration, "
            "and paired-bootstrap AUC differences (M minus each baseline) "
            "are reported below."
        ),
    ]

    def cell(value):
        if value is None:
            return "n/a"
        if isinstance(value, (list, tuple)):
            return " to ".join(cell(item) for item in value)
        return str(value)

    entries = [("2024", payload["validation"])] + list(
        payload["rolling_origin"].items()
    )
    for year, year_data in entries:
        for population, result in year_data.items():
            lines.extend(
                [
                    "",
                    (
                        f"EXPLORATORY FACT: {year} {population} ranking "
                        "metrics table:"
                    ),
                    (
                        "| Ranking | N | Positives | Top 25 hits | Top 25 "
                        "precision | Top 50 hits | Top 50 precision | Top "
                        "100 hits | Top 100 precision | AUROC |"
                    ),
                    "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
                ]
            )
            for method, metrics in result.get("rankings", {}).items():
                top = metrics["top_k"]
                values = [
                    method,
                    result["n"],
                    result["positives"],
                    top["25"]["hits"],
                    top["25"]["precision"],
                    top["50"]["hits"],
                    top["50"]["precision"],
                    top["100"]["hits"],
                    top["100"]["precision"],
                    metrics["auroc"],
                ]
                lines.append("| " + " | ".join(map(cell, values)) + " |")
            lines.extend(
                [
                    (
                        f"EXPLORATORY FACT: {year} {population} M "
                        "calibration table (bin, count, mean probability, "
                        "outcome rate):"
                    ),
                    "| Bin | Count | Mean probability | Outcome rate |",
                    "|---:|---:|---:|---:|",
                ]
            )
            for row in result["calibration"]:
                lines.append(
                    "| "
                    + " | ".join(
                        map(
                            cell,
                            (
                                row["bin"],
                                row["count"],
                                row["mean_probability"],
                                row["outcome_rate"],
                            ),
                        )
                    )
                    + " |"
                )
            lines.extend(
                [
                    (
                        f"EXPLORATORY FACT: {year} {population} paired "
                        "bootstrap table, 95% percentile intervals:"
                    ),
                    (
                        "| Comparator | Mean AUROC difference | "
                        "95% interval | Valid resamples |"
                    ),
                    "|---|---:|---|---:|",
                ]
            )
            for method, row in result["bootstrap_m_minus_baseline"].items():
                lines.append(
                    "| "
                    + " | ".join(
                        map(
                            cell,
                            (
                                f"M minus {method}",
                                row["mean_difference"],
                                row["percentile_95"],
                                row["valid_resamples"],
                            ),
                        )
                    )
                    + " |"
                )
    val = payload["validation"]["whole_pool"]
    m_hits = val["rankings"]["M"]["top_k"]["50"]["hits"]
    c_hits = val["rankings"][payload["comparator"]]["top_k"]["50"]["hits"]
    lines.extend(
        [
            "",
            (
                "EXPLORATORY INFERENCE: On the 2024 whole pool, M had "
                f"{m_hits} top-50 hits and {payload['comparator']} had "
                f"{c_hits}."
            ),
            "EXPLORATORY UNKNOWN: The 2025 cohort was not evaluated.",
            (
                "EXPLORATORY UNKNOWN: Whether differences exceed sampling "
                "noise beyond these bootstrap intervals is unknown."
            ),
            (
                "EXPLORATORY UNKNOWN: Stability of the single L2 choice is "
                "unknown."
            ),
            END,
        ]
    )
    return "\n".join(lines) + "\n"


def write_outputs(root, payload):
    root = Path(root)
    research = root / "research"
    report_path = research / "EXPERIMENT.md"
    primary = report_path.read_bytes()
    text = primary.decode()
    if START in text and END in text:
        prefix = text[: text.index(START)]
        repaired = prefix[:-1] if prefix.endswith("\n\n") else prefix
        if (
            hashlib.sha256(repaired.encode()).hexdigest()
            == PRIMARY_PREFIX_SHA256
        ):
            prefix = repaired
    else:
        prefix = text
    section = render_section(payload)
    json_path = research / "exploratory_whole_pool.json"
    atomic_json(json_path, payload)
    temporary = report_path.with_suffix(".md.tmp")
    separator = "" if prefix.endswith("\n") else "\n"
    temporary.write_text(prefix + separator + section)
    temporary.replace(report_path)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--seed", type=int, default=43017)
    parser.add_argument("--resamples", type=int, default=2000)
    args = parser.parse_args(argv)
    try:
        payload = evaluate(args.root, args.seed, args.resamples)
    except (FileNotFoundError, OSError, ValueError, RuntimeError) as error:
        parser.error(f"could not evaluate local inputs: {error}")
    write_outputs(args.root, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
