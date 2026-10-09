"""Offline cohort outcome construction and preregistered evaluation."""

import json
from pathlib import Path

from .triage import rank
from .triage_config import BOOTSTRAP_RESAMPLES, BOOTSTRAP_SEED
from .triage_config import L2_GRID, TOP_K
from .triage_eval import (
    B2_FEATURES,
    MODEL_FEATURES,
    LogisticModel,
    auc,
    calibration,
    paired_bootstrap,
    choose_comparator,
)
from .triage_eval import build_outcomes

YEARS = (2018, 2019, 2021, 2022, 2023, 2024)
TRAIN_YEARS = YEARS[:5]
TEST_YEARS = (2021, 2022, 2023)


def _stats(root):
    result = {}
    for path in sorted((Path(root) / "data/stats").glob("*_1_*.json")):
        artifact = json.loads(path.read_text())
        season = int(artifact["season"])
        if season >= 2026 or season != int(path.name.split("_")[0]):
            raise ValueError("invalid or prohibited stats season")
        if artifact.get("truncated") or artifact.get("coverage_unknown"):
            raise RuntimeError(
                "stats artifact has incomplete coverage: " + path.name
            )
        result.setdefault(season, [])
        result[season].extend(artifact.get("rows", []))
    return result


def _metric_rows(root, cohort, stats_by_year):
    year = int(cohort["year"])
    following = stats_by_year.get(year + 1)
    if following is None:
        raise RuntimeError(
            "missing league-wide MLB outcome season " + str(year + 1)
        )
    by_player = {}
    for row in following:
        by_player.setdefault(row.get("person_id"), []).append(row)
    player_ids = [source["person_id"] for source in cohort["features"]]
    outcomes = build_outcomes(root, year, player_ids, by_player)
    result = []
    for source in cohort["features"]:
        label = outcomes[source["person_id"]]["positive"]
        appearance = outcomes[source["person_id"]]["any_appearance"]
        result.append(
            {
                **source,
                "positive": label,
                "any_appearance": appearance,
                "no_mlb_appearance_y": bool(source.get("no_mlb_appearance_y")),
                # P is defined from season Y itself. The shortened
                # season adjustment applies only to outcomes in 2020
                # for the 2019 cohort, not to full-season 2019 stats.
                "met_threshold_y": (
                    float(source.get("mlb_pa_y", 0) or 0) >= 50
                    or float(source.get("mlb_ip_y", 0) or 0) >= 20
                ),
            }
        )
    return result


def _ip(value):
    text = str(value or "0.0")
    whole, _, outs = text.partition(".")
    return int(whole or 0) + int(outs or 0) / 3


def _fit(rows, strength, features):
    if not rows or len({bool(r["positive"]) for r in rows}) < 2:
        return None
    model = LogisticModel(strength=strength).fit(
        rows, [int(r["positive"]) for r in rows], features
    )
    return model


def _rank_eval(rows, training, strength):
    if not rows:
        return {"n": 0, "positives": 0, "base_rate": None, "rankings": {}}
    model = _fit(training, strength, MODEL_FEATURES)
    probabilities = (
        model.predict_proba(rows, MODEL_FEATURES)
        if model
        else [0.5] * len(rows)
    )
    b2_training = [r for r in training if r.get("no_mlb_appearance_y")]
    b2_model = _fit(b2_training, 1.0, B2_FEATURES)
    b2_probabilities = (
        b2_model.predict_proba(rows, B2_FEATURES)
        if b2_model
        else [0.5] * len(rows)
    )
    scored = [
        {**r, "m_probability": p, "b2_probability": b2}
        for r, p, b2 in zip(rows, probabilities, b2_probabilities)
    ]
    metrics = {}
    auc_scores = {}
    labels = [int(r["positive"]) for r in scored]
    for method in ("B0", "B1", "B2", "P", "M"):
        ordered = rank(scored, method)
        ordinal = {
            r["person_id"]: len(ordered) - i for i, r in enumerate(ordered)
        }
        top = {
            str(k): {
                "hits": sum(bool(r["positive"]) for r in ordered[:k]),
                "precision": sum(bool(r["positive"]) for r in ordered[:k])
                / min(k, len(ordered)),
            }
            for k in TOP_K
        }
        scores = (
            [r["m_probability"] for r in scored]
            if method == "M"
            else [float(r.get("met_threshold_y", False)) for r in scored]
            if method == "P"
            else [float(ordinal[r["person_id"]]) for r in scored]
        )
        metrics[method] = {"top_k": top, "auroc": auc(labels, scores)}
        auc_scores[method] = scores
    return {
        "n": len(rows),
        "positives": sum(labels),
        "base_rate": sum(labels) / len(labels),
        "rankings": metrics,
        "calibration": calibration(labels, probabilities),
        "_auc_scores": auc_scores,
    }


def _segment_rows(rows):
    primary = [r for r in rows if r["no_mlb_appearance_y"]]
    return {
        "primary": primary,
        "pitchers": [r for r in primary if r.get("player_type") == "pitcher"],
        "hitters": [r for r in primary if r.get("player_type") != "pitcher"],
        "whole_pool": rows,
    }


def _round(value):
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, dict):
        return {key: _round(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_round(item) for item in value]
    return value


def _bootstrap_deltas(labels, auc_scores):
    model_scores = auc_scores["M"]
    return {
        method: paired_bootstrap(labels, model_scores, auc_scores[method])
        for method in ("B0", "B1", "B2", "P")
    }


def evaluate(root):
    root = Path(root)
    stats = _stats(root)
    cohorts, base_rates = {}, {}
    for year in YEARS:
        path = root / "data/cohorts" / f"{year}.json"
        cohort = json.loads(path.read_text())
        rows = _metric_rows(root, cohort, stats)
        cohorts[year] = rows
        base_rates[str(year)] = {}
        for segment, selected in _segment_rows(rows).items():
            base_rates[str(year)][segment] = {
                "n": len(selected),
                "positives": sum(r["positive"] for r in selected),
                "positive_rate": sum(r["positive"] for r in selected)
                / len(selected)
                if selected
                else None,
                "any_appearance": sum(r["any_appearance"] for r in selected),
            }
    train = [
        r for y in TRAIN_YEARS for r in _segment_rows(cohorts[y])["primary"]
    ]
    val = _segment_rows(cohorts[2024])["primary"]
    chosen = None
    if sum(r["positive"] for r in val) >= 30:
        choices = []
        for strength in L2_GRID:
            scores = _rank_eval(val, train, strength)
            choices.append(
                (
                    scores["rankings"]["M"]["top_k"]["50"]["hits"],
                    -L2_GRID.index(strength),
                    strength,
                )
            )
        chosen = max(choices)[2]
    early = chosen is None
    output = {
        "config": {
            "cohort_years": list(YEARS),
            "training_years": list(TRAIN_YEARS),
            "validation_year": 2024,
            "rolling_origin_test_years": list(TEST_YEARS),
            "holdout_excluded": 2025,
            "early_stop_positive_minimum": 30,
            "top_k": list(TOP_K),
            "bootstrap_resamples": BOOTSTRAP_RESAMPLES,
            "bootstrap_seed": BOOTSTRAP_SEED,
            "l2_grid": list(L2_GRID),
            "thresholds": {"pa": 50, "ip": 20, "2019_scale": "60/162"},
            "features": list(MODEL_FEATURES),
        },
        "base_rates": base_rates,
        "chosen_l2_strength": chosen,
        "early_stop": early,
        "early_stop_reason": "validation primary positives below 30"
        if early
        else None,
        "validation": None,
        "rolling_origin": None,
        "chosen_comparator": None,
    }
    if not early:
        validation = _rank_eval(val, train, chosen)
        comparator = choose_comparator(validation["rankings"])
        labels = [int(r["positive"]) for r in val]
        validation["bootstrap_m_minus_baseline"] = _bootstrap_deltas(
            labels, validation["_auc_scores"]
        )
        del validation["_auc_scores"]
        validation["comparator"] = comparator
        rolling = {}
        for year in TEST_YEARS:
            prior = [
                r
                for y in YEARS
                if y < year
                for r in _segment_rows(cohorts[y])["primary"]
            ]
            rolling_result = _rank_eval(
                _segment_rows(cohorts[year])["primary"], prior, chosen
            )
            del rolling_result["_auc_scores"]
            rolling[str(year)] = rolling_result
        output["validation"], output["rolling_origin"] = validation, rolling
        output["chosen_comparator"] = comparator
    return _round(output)
