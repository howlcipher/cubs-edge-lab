"""FIT stage of the frozen SENDHOLD design: 2025 rows only, offline.

Writes ``data/sendhold_fit.json`` (the frozen models and thresholds, hashed by
the campaign controller) and the aggregate-only ``research/sendhold_fit.json``.
The 2026 holdout is opened only by ``sendhold_evaluate``.
"""
import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from .client import atomic_json
from .sendhold_model import (
    EARLY_STOP_SENT_OUT, SEED, break_even, choose_covariates, clopper_pearson,
    featurize, fit_model, predict, quantile, state_value, support_threshold)

DESIGN_SHA256 = (
    "a852b921c1c218f6f8bd525b4c1397923b8d12651dfc829b084b60e35b7b0a1a")
FIT_SEASON = 2025
VERSIONS = ("v3", "v2")
SEND_LABELS = ("SENT_SAFE", "SENT_OUT")
ACTION_LABELS = SEND_LABELS + ("HOLD",)
MIN_CELL_N = 10
# Base masks: 1B=1, 2B=2, 3B=4. The batter-runner ends on first after a
# single and on second after a double.
BATTER_MASK = {"single": 1, "double": 2}

MAPPING_NOTES = (
    "Hold state: the runner stops on third and the batter-runner stands on "
    "the base the hit gave him (first after a single, second after a "
    "double), with the pre-play outs. Trailing runners are ignored, as the "
    "design states.",
    "Out-at-home state: the batter-runner on the same base and one more out "
    "than before the play. If that makes three outs the inning is over and "
    "the run expectancy is 0.",
    "Run-scored state: the batter-runner's resulting base-out state with the "
    "pre-play outs; the extra run is the +1 in the break-even formula.",
    "The batter-runner is assumed not to advance on the throw home, so the "
    "same batter base is used in all three states.",
    "p* is computed per hold state, keyed by hit type and pre-play outs "
    "(single|0, single|1, double|0, double|1). Run expectancy is the 2025 "
    "table in research/sendhold_data.json; no outside values are used.",
    "Hit location is the feed's fielder-position zone: 5, 6, 7 left; 1, 2, "
    "8 and unknown center; 3, 4, 9 right. Fixed before any fit.",
    "Missing numeric covariates are replaced by the training mean "
    "(standardized 0). The full set also carries missing and same-season "
    "fallback flags; the reduced set has none of them.",
    "Coefficients are per training standard deviation of each column, from "
    "a logistic regression with a ridge penalty of 1e-4 (intercept not "
    "penalized). Standard errors come from the penalized Hessian.",
    "Events-per-parameter counts the intercept: the full set (13 columns, "
    "14 parameters) needs 140 SENT_OUT runners in 2025; otherwise the "
    "reduced set (speed, zone left/right dummies, outs; 5 parameters) is "
    "used. The same chosen set is used for the propensity model.",
    "The propensity model is fit on 2025 SEND and HOLD runners; the support "
    "threshold is the 2.5th percentile (linear interpolation) of the "
    "propensities of 2025 sends.",
    "The decision chart averages 2025-model P(safe) over 2025 SEND and HOLD "
    "runners per cell; speed terciles use the 2025 tercile cut points; "
    "cells with fewer than 10 runners are marked low_n, not hidden.",
)


def label_for(row, version):
    """Label of a table row under the named version."""
    if version == "v2":
        return row["label"]
    if "label_v3" not in row:
        raise ValueError(
            "opportunity table lacks label_v3; regenerate it with "
            "python3 -m cubs_edge_lab.probe.sendhold_data")
    if version == "v3":
        return row["label_v3"]
    if version == "v3_ambiguous_as_safe":
        label = row["label_v3"]
        return "SENT_SAFE" if label == "AMBIGUOUS" else label
    raise ValueError("unknown label version " + str(version))


def prepare_rows(rows, version, drop_fallback=False):
    """Featurize rows and attach the label ``lab`` for the version."""
    prepared = []
    for row in rows:
        if drop_fallback and (
                row.get("sprint_speed_same_season_fallback")
                or row.get("arm_strength_same_season_fallback")):
            continue
        item = featurize(row)
        item["lab"] = label_for(row, version)
        prepared.append(item)
    return prepared


def load_fit_rows(path):
    """Load the opportunity table and expose only the 2025 rows."""
    rows = json.loads(Path(path).read_text())
    return [row for row in rows if row.get("season") == FIT_SEASON]


def load_expectancy(path):
    """2025 run-expectancy table keyed by (bases mask, outs)."""
    payload = json.loads(Path(path).read_text())
    states = payload["facts"]["run_expectancy_2025"]["states"]
    return {(s["bases_mask"], s["outs"]): s["mean_runs"] for s in states}


def key_for(hit_type, outs):
    return "{}|{}".format(hit_type, int(outs))


def re_states(table):
    """Break-even inputs per hold state from the run-expectancy table."""
    result = {}
    for hit, batter in BATTER_MASK.items():
        for outs in (0, 1):
            hold = state_value(table, batter | 4, outs)
            out = state_value(table, batter, outs + 1)
            scored = state_value(table, batter, outs)
            ready = None not in (hold, out, scored)
            result[key_for(hit, outs)] = {
                "hit_type": hit, "outs": outs, "re_hold": hold,
                "re_out_at_home": out, "re_scored": scored,
                "p_star": break_even(hold, out, scored) if ready else None}
    return result


def p_star(states, row):
    state = states.get(key_for(row.get("hit_type"), row.get("outs") or 0))
    return None if state is None else state["p_star"]


def label_counts(rows):
    counts = Counter(row["lab"] for row in rows)
    return {name: counts[name] for name in (
        "SENT_OUT", "OUT_ELSEWHERE", "SENT_SAFE", "AMBIGUOUS", "HOLD",
        "OTHER")}


def fit_pipeline(rows, columns=None):
    """Fit all 2025-side models from labelled, featurized rows.

    ``columns`` overrides the events-per-parameter choice (the bootstrap
    keeps the full-sample choice fixed). Returns a descriptive-only record
    without models when SENT_OUT is below the early-stop threshold.
    """
    counts = label_counts(rows)
    sent_out = counts["SENT_OUT"]
    sends = [row for row in rows if row["lab"] in SEND_LABELS]
    holds = [row for row in rows if row["lab"] == "HOLD"]
    pipeline = {"label_counts": counts, "sent_out": sent_out}
    if sends:
        pipeline["out_at_home"] = {
            "sends": len(sends), "sent_out": sent_out,
            "rate": sent_out / len(sends),
            "interval_95": clopper_pearson(sent_out, len(sends))}
    if sent_out < EARLY_STOP_SENT_OUT:
        pipeline["mode"] = "DESCRIPTIVE ONLY"
        return pipeline
    choice = choose_covariates(sent_out)
    if columns is not None:
        choice = {**choice, "columns": list(columns)}
    safe = [row["lab"] == "SENT_SAFE" for row in sends]
    outs_rates = {}
    for outs in sorted({int(row["outs"] or 0) for row in sends}):
        group = [s for row, s in zip(sends, safe)
                 if int(row["outs"] or 0) == outs]
        outs_rates[str(outs)] = sum(group) / len(group)
    success = fit_model(sends, choice["columns"],
                        lambda row: row["lab"] == "SENT_SAFE")
    propensity = fit_model(sends + holds, choice["columns"],
                           lambda row: row["lab"] in SEND_LABELS)
    send_scores = [predict(propensity, row) for row in sends]
    threshold = support_threshold(send_scores)
    hold_scores = [predict(propensity, row) for row in holds]
    pipeline.update({
        "mode": "MODEL", "covariate_choice": choice,
        "send_success_model": success, "propensity_model": propensity,
        "support_threshold": threshold,
        "constant_rate": sum(safe) / len(safe), "outs_rates": outs_rates,
        "holds_below_support_share_2025": (
            sum(score < threshold for score in hold_scores) / len(holds)
            if holds else None)})
    return pipeline


def baseline_outs(pipeline, row):
    return pipeline["outs_rates"].get(
        str(int(row.get("outs") or 0)), pipeline["constant_rate"])


def decision_chart(pipeline, rows, states):
    """Descriptive 2025-model P(safe) by zone, hit type, outs and speed."""
    action = [row for row in rows if row["lab"] in ACTION_LABELS]
    speeds = [row["sprint_speed"] for row in action
              if row["sprint_speed"] is not None]
    cuts = [quantile(speeds, 1 / 3), quantile(speeds, 2 / 3)] if speeds else []

    def tercile(row):
        speed = row["sprint_speed"]
        if speed is None or not cuts:
            return "unknown"
        return "low" if speed <= cuts[0] else (
            "mid" if speed <= cuts[1] else "high")

    cells = defaultdict(list)
    for row in action:
        cells[(row["zone_group"], row["hit_type"], int(row["outs"] or 0),
               tercile(row))].append(row)
    chart = []
    for key in sorted(cells):
        members = cells[key]
        sent = [row for row in members if row["lab"] in SEND_LABELS]
        chart.append({
            "zone_group": key[0], "hit_type": key[1], "outs": key[2],
            "speed_tercile": key[3], "n": len(members), "n_sent": len(sent),
            "mean_p_safe": sum(predict(pipeline["send_success_model"], row)
                               for row in members) / len(members),
            "observed_send_success": (
                sum(row["lab"] == "SENT_SAFE" for row in sent) / len(sent)
                if sent else None),
            "p_star": p_star(states, members[0]),
            "low_n": len(members) < MIN_CELL_N})
    return {"speed_tercile_cuts": cuts, "min_cell_n": MIN_CELL_N,
            "cells": chart}


def fit_version(raw_rows, version, states):
    rows = prepare_rows(raw_rows, version)
    pipeline = fit_pipeline(rows)
    pipeline["label_version"] = version
    pipeline["primary"] = version == "v3"
    if pipeline["mode"] == "MODEL":
        pipeline["decision_chart"] = decision_chart(pipeline, rows, states)
    return pipeline


def build_fit(rows, table):
    """Pure computation of the fit from 2025 rows and the RE table."""
    states = re_states(table)
    return {
        "design_sha256": DESIGN_SHA256, "fit_season": FIT_SEASON,
        "seed": SEED, "primary_label_version": "v3",
        "re_states": states, "state_mapping": list(MAPPING_NOTES),
        "versions": {version: fit_version(rows, version, states)
                     for version in VERSIONS}}


def run_fit(root):
    root = Path(root)
    rows = load_fit_rows(root / "data/sendhold_opportunity_table.json")
    table = load_expectancy(root / "research/sendhold_data.json")
    output = build_fit(rows, table)
    atomic_json(root / "data/sendhold_fit.json", output)
    published = dict(output)
    primary = output["versions"]["v3"]
    published["facts"] = [
        "FACT: Fit used {} 2025 opportunity rows (design sha256 {}); rows "
        "of other seasons are discarded at load and no 2026 value is "
        "used.".format(len(rows), DESIGN_SHA256),
        "FACT: 2025 SENT_OUT count {}; mode {}.".format(
            primary["sent_out"], primary["mode"]),
    ]
    published["unknown"] = [
        "UNKNOWN: Whether held runners would have been safe if sent; the "
        "feed does not record the coach's sign, jump, or counterfactual."]
    atomic_json(root / "research/sendhold_fit.json", published)
    digest = hashlib.sha256(
        (root / "data/sendhold_fit.json").read_bytes()).hexdigest()
    print(digest)
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    run_fit(args.root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
