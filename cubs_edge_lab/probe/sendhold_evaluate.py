"""EVALUATE stage of the frozen SENDHOLD design: opens the 2026 holdout.

Run only after the hash of ``data/sendhold_fit.json`` is recorded. This stage
never fits on 2026 rows: the frozen 2025 models score 2026, and the game
bootstrap refits the 2025-side models inside every resample. Output is
aggregate-only with at most five short examples.
"""
import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from .client import atomic_json
from .sendhold import md_escape
from .sendhold_fit import (
    DESIGN_SHA256, SEND_LABELS, baseline_outs, fit_pipeline, key_for,
    label_for, p_star, prepare_rows)
from .sendhold_model import (
    FLAG_MARGIN, SEED, brier, calibration_slope, clopper_pearson,
    game_bootstrap, percentile_interval, predict)

HOLDOUT_SEASON = 2026
FIT_SEASON = 2025
CUBS_TEAM_ID = 112
SLOPE_RANGE = (0.7, 1.3)
MAX_EXAMPLES = 5
FROZEN_TOLERANCE = 1e-6
# (analysis name, label version, drop same-season fallback rows)
SPECS = (
    ("v3_primary", "v3", False),
    ("v2_preregistered", "v2", False),
    ("v3_ambiguous_as_safe", "v3_ambiguous_as_safe", False),
    ("v3_fallback_dropped", "v3", True),
)
FROZEN_VERSION = {"v3_primary": "v3", "v2_preregistered": "v2"}
INTERVAL_KEYS = (
    "brier_diff_constant", "brier_diff_outs", "calibration_slope",
    "flagged_send_mean_predicted", "holds_dropped_share", "flagged_holds",
    "runs_left", "cubs_flagged_holds", "cubs_runs_left")


def score(pipeline, rows, states, team_id=CUBS_TEAM_ID, examples=0):
    """Score labelled featurized rows with a fitted pipeline."""
    model = pipeline["send_success_model"]
    propensity = pipeline["propensity_model"]
    threshold = pipeline["support_threshold"]
    sends = [row for row in rows if row["lab"] in SEND_LABELS]
    holds = [row for row in rows if row["lab"] == "HOLD"]
    result = {"n_sends": len(sends), "n_holds": len(holds)}
    if sends:
        predictions = [predict(model, row) for row in sends]
        outcomes = [float(row["lab"] == "SENT_SAFE") for row in sends]
        b_model = brier(predictions, outcomes)
        b_const = brier([pipeline["constant_rate"]] * len(sends), outcomes)
        b_outs = brier([baseline_outs(pipeline, row) for row in sends],
                       outcomes)
        flagged = [(p, y) for row, p, y in zip(sends, predictions, outcomes)
                   if p_star(states, row) is not None
                   and p >= p_star(states, row) + FLAG_MARGIN]
        result.update({
            "brier_model": b_model, "brier_constant": b_const,
            "brier_outs": b_outs,
            "brier_diff_constant": b_model - b_const,
            "brier_diff_outs": b_model - b_outs,
            "calibration_slope": calibration_slope(predictions, outcomes),
            "flagged_sends": len(flagged),
            "flagged_send_mean_predicted": (
                sum(p for p, _ in flagged) / len(flagged)
                if flagged else None),
            "flagged_send_realized": (
                sum(y for _, y in flagged) / len(flagged)
                if flagged else None)})
    supported = flagged_holds = cubs_flagged = 0
    runs_left = cubs_runs = 0.0
    shown = []
    for row in holds:
        if predict(propensity, row) < threshold:
            continue
        supported += 1
        state = states.get(key_for(row.get("hit_type"), row.get("outs") or 0))
        if state is None or state["p_star"] is None:
            continue
        p = predict(model, row)
        if p < state["p_star"] + FLAG_MARGIN:
            continue
        gain = (p * (state["re_scored"] + 1.0)
                + (1.0 - p) * state["re_out_at_home"] - state["re_hold"])
        flagged_holds += 1
        runs_left += gain
        if row.get("batting_team_id") == team_id:
            cubs_flagged += 1
            cubs_runs += gain
        if len(shown) < examples:
            shown.append({"game_id": row.get("game_id"),
                          "hit_type": row.get("hit_type"),
                          "outs": int(row.get("outs") or 0),
                          "p_safe": p, "p_star": state["p_star"]})
    result.update({
        "holds_supported": supported,
        "holds_dropped_share": ((len(holds) - supported) / len(holds)
                                if holds else None),
        "flagged_holds": flagged_holds, "runs_left": runs_left,
        "cubs_flagged_holds": cubs_flagged, "cubs_runs_left": cubs_runs})
    if examples:
        result["examples"] = shown
    return result


def by_game(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[row["game_id"]].append(row)
    return groups


def bootstrap_scores(fit_rows, eval_rows, states, columns, resamples, seed):
    """Refit the 2025-side models in each resample; score a 2026 resample."""
    def statistic(fit_sample, eval_sample):
        try:
            pipeline = fit_pipeline(fit_sample, columns=columns)
        except ValueError:
            return None
        if pipeline["mode"] != "MODEL":
            return None
        return score(pipeline, eval_sample, states)

    runs = game_bootstrap(statistic, by_game(fit_rows), by_game(eval_rows),
                          resamples=resamples, seed=seed)
    usable = [run for run in runs if run is not None]
    intervals = {key: percentile_interval(
        [run.get(key) for run in usable]) for key in INTERVAL_KEYS}
    return {"resamples": resamples, "usable_resamples": len(usable),
            "seed": seed, "intervals_95": intervals}


def criteria(point, boot):
    """Each pre-registered criterion, separately, with its inputs."""
    intervals = boot["intervals_95"]
    brier_interval = intervals["brier_diff_constant"]
    slope = point.get("calibration_slope")
    runs_interval = intervals["runs_left"]
    control_interval = intervals["flagged_send_mean_predicted"]
    realized = point.get("flagged_send_realized")
    brier_pass = bool(brier_interval and brier_interval["upper"] < 0)
    slope_pass = (slope is not None
                  and SLOPE_RANGE[0] <= slope <= SLOPE_RANGE[1])
    runs_pass = bool(runs_interval and runs_interval["lower"] > 0)
    control_pass = bool(control_interval and realized is not None
                        and control_interval["lower"] <= realized
                        <= control_interval["upper"])
    return {
        "brier_beats_constant": {
            "passed": brier_pass, "difference": point.get(
                "brier_diff_constant"), "interval_95": brier_interval,
            "rule": "interval of (model - constant) excludes zero below"},
        "calibration_slope": {
            "passed": slope_pass, "slope": slope,
            "interval_95": intervals["calibration_slope"],
            "rule": "slope within [0.7, 1.3]"},
        "runs_left_excludes_zero": {
            "passed": runs_pass, "estimate": point.get("runs_left"),
            "interval_95": runs_interval,
            "rule": "95% bootstrap interval of runs left above zero"},
        "negative_control": {
            "passed": control_pass, "realized_success": realized,
            "mean_predicted": point.get("flagged_send_mean_predicted"),
            "interval_95": control_interval,
            "flagged_sends": point.get("flagged_sends", 0),
            "rule": "realized success inside the interval of mean "
                    "predicted P(safe) for flagged sends"}}


def verdict_for(checks, mode):
    """DESCRIPTIVE ONLY, NEGATIVE, POSITIVE or INCONCLUSIVE."""
    if mode != "MODEL":
        return "DESCRIPTIVE ONLY"
    validity = (checks["brier_beats_constant"]["passed"]
                and checks["calibration_slope"]["passed"])
    if not validity:
        return "NEGATIVE"
    if (checks["runs_left_excludes_zero"]["passed"]
            and checks["negative_control"]["passed"]):
        return "POSITIVE"
    return "INCONCLUSIVE"


def descriptive(raw_rows, version):
    """Counts and out-at-home rate with an exact interval for one season."""
    counts = Counter(label_for(row, version) for row in raw_rows)
    out = counts["SENT_OUT"]
    sends = out + counts["SENT_SAFE"]
    return {"label_counts": dict(sorted(counts.items())), "sends": sends,
            "out_at_home_rate": out / sends if sends else None,
            "out_at_home_interval_95": clopper_pearson(out, sends)}


def cubs_counts(raw_rows, version):
    cubs = [row for row in raw_rows
            if row.get("batting_team_id") == CUBS_TEAM_ID]
    return {"opportunities": len(cubs),
            "label_counts": dict(sorted(Counter(
                label_for(row, version) for row in cubs).items()))}


def check_frozen(name, pipeline, frozen):
    """The refit must reproduce the frozen fit, or the inputs changed."""
    version = FROZEN_VERSION.get(name)
    if version is None:
        return
    reference = frozen["versions"][version]
    if reference["mode"] != pipeline["mode"]:
        raise RuntimeError("frozen fit mode differs for " + name)
    if pipeline["mode"] != "MODEL":
        return
    for key in ("send_success_model", "propensity_model"):
        for a, b in zip(reference[key]["coefficients"],
                        pipeline[key]["coefficients"]):
            if abs(a - b) > FROZEN_TOLERANCE:
                raise RuntimeError(
                    "frozen fit does not reproduce for " + name)


def analyze(name, version, drop_fallback, fit_raw, eval_raw, frozen,
            resamples, seed, examples=0):
    states = frozen["re_states"]
    fit_rows = prepare_rows(fit_raw, version, drop_fallback)
    eval_rows = prepare_rows(eval_raw, version, drop_fallback)
    pipeline = fit_pipeline(fit_rows)
    check_frozen(name, pipeline, frozen)
    result = {"label_version": version, "drop_fallback_rows": drop_fallback,
              "mode": pipeline["mode"], "sent_out_2025": pipeline["sent_out"],
              "rows_2025": len(fit_rows), "rows_2026": len(eval_rows),
              "label_counts_2025": pipeline["label_counts"]}
    if pipeline["mode"] != "MODEL":
        result["verdict"] = "DESCRIPTIVE ONLY"
        result["descriptive_2025"] = descriptive(fit_raw, version)
        result["descriptive_2026"] = descriptive(eval_raw, version)
        return result
    point = score(pipeline, eval_rows, states, examples=examples)
    in_sample = score(pipeline, fit_rows, states)
    boot = bootstrap_scores(fit_rows, eval_rows, states,
                            pipeline["covariate_choice"]["columns"],
                            resamples, seed)
    checks = criteria(point, boot)
    examples_found = point.pop("examples", [])
    result.update({
        "covariate_choice": pipeline["covariate_choice"],
        "support_threshold": pipeline["support_threshold"],
        "point_2026": point, "bootstrap": boot, "criteria": checks,
        "verdict": verdict_for(checks, pipeline["mode"]),
        "cubs": {
            "2025": {**cubs_counts(fit_raw, version), "in_sample": True,
                     "flagged_holds": in_sample["cubs_flagged_holds"],
                     "runs_left": in_sample["cubs_runs_left"]},
            "2026": {**cubs_counts(eval_raw, version),
                     "flagged_holds": point["cubs_flagged_holds"],
                     "runs_left": point["cubs_runs_left"],
                     "flagged_holds_interval_95": boot["intervals_95"][
                         "cubs_flagged_holds"],
                     "runs_left_interval_95": boot["intervals_95"][
                         "cubs_runs_left"]}},
        "examples": examples_found})
    return result


def evaluate_rows(fit_raw, eval_raw, frozen, resamples=1000, seed=SEED):
    """Pure computation of every analysis from 2025 and 2026 raw rows."""
    analyses = {}
    for name, version, drop in SPECS:
        analyses[name] = analyze(
            name, version, drop, fit_raw, eval_raw, frozen, resamples, seed,
            examples=MAX_EXAMPLES if name == "v3_primary" else 0)
    primary = analyses["v3_primary"]
    examples = primary.pop("examples", [])
    for analysis in analyses.values():
        analysis.pop("examples", None)
    return {
        "design_sha256": DESIGN_SHA256, "holdout_season": HOLDOUT_SEASON,
        "primary_label_version": "v3", "seed": seed, "resamples": resamples,
        "verdict": primary["verdict"],
        "verdict_v2_preregistered_definition": analyses[
            "v2_preregistered"]["verdict"],
        "analyses": analyses, "examples": examples[:MAX_EXAMPLES]}


def fmt(value, digits=4):
    if value is None:
        return "NA"
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, float):
        return format(value, "." + str(digits) + "f")
    return str(value)


def fmt_interval(interval):
    if not interval:
        return "NA"
    return "[{}, {}]".format(fmt(interval["lower"]), fmt(interval["upper"]))


def render_analysis(name, analysis):
    lines = ["### " + md_escape(name), ""]
    lines.append(
        "FACT: Labels {}; fallback rows dropped: {}; 2025 SENT_OUT {}; "
        "rows 2025/2026 {}/{}; mode {}.".format(
            analysis["label_version"],
            fmt(analysis["drop_fallback_rows"]), analysis["sent_out_2025"],
            analysis["rows_2025"], analysis["rows_2026"], analysis["mode"]))
    if analysis["mode"] != "MODEL":
        for season in ("2025", "2026"):
            item = analysis["descriptive_" + season]
            lines.append(
                "FACT: {} out-at-home rate {} of {} sends, exact 95% "
                "interval {}.".format(
                    season, fmt(item["out_at_home_rate"]), item["sends"],
                    fmt_interval(item["out_at_home_interval_95"])))
        lines += ["INFERENCE: Verdict **" + analysis["verdict"] + "**.", ""]
        return lines
    point = analysis["point_2026"]
    lines += [
        "FACT: Covariate set {} (2025 SENT_OUT {} against {} required for "
        "the full set); support threshold {}.".format(
            analysis["covariate_choice"]["name"], analysis["sent_out_2025"],
            analysis["covariate_choice"]["required_sent_out"],
            fmt(analysis["support_threshold"])),
        "FACT: 2026 sends {}, holds {}; Brier model {}, constant {}, "
        "outs-only {}; difference to constant {} (interval {}), to "
        "outs-only {} (interval {}).".format(
            point["n_sends"], point["n_holds"], fmt(point["brier_model"]),
            fmt(point["brier_constant"]), fmt(point["brier_outs"]),
            fmt(point["brier_diff_constant"]),
            fmt_interval(analysis["bootstrap"]["intervals_95"][
                "brier_diff_constant"]),
            fmt(point["brier_diff_outs"]),
            fmt_interval(analysis["bootstrap"]["intervals_95"][
                "brier_diff_outs"])),
        "FACT: Holds below the propensity support threshold: {} of {} "
        "(share {}); assessed holds {}; flagged holds {}.".format(
            point["n_holds"] - point["holds_supported"], point["n_holds"],
            fmt(point["holds_dropped_share"]), point["holds_supported"],
            point["flagged_holds"]),
        "FACT: Bootstrap {} resamples ({} usable), seed {}.".format(
            analysis["bootstrap"]["resamples"],
            analysis["bootstrap"]["usable_resamples"],
            analysis["bootstrap"]["seed"]),
        "",
        "| Criterion | Value | 95% interval | Passed |",
        "|---|---:|---|---|"]
    checks = analysis["criteria"]
    rows = (
        ("Brier difference to constant", "brier_beats_constant",
         checks["brier_beats_constant"]["difference"]),
        ("Calibration slope", "calibration_slope",
         checks["calibration_slope"]["slope"]),
        ("Runs left (2026)", "runs_left_excludes_zero",
         checks["runs_left_excludes_zero"]["estimate"]),
        ("Negative control (realized flagged-send success)",
         "negative_control", checks["negative_control"]["realized_success"]))
    for label, key, value in rows:
        lines.append("| {} | {} | {} | {} |".format(
            label, fmt(value), fmt_interval(checks[key]["interval_95"]),
            fmt(checks[key]["passed"])))
    cubs = analysis["cubs"]
    lines += [
        "",
        "FACT: Cubs opportunities 2025 {} and 2026 {}; flagged holds 2025 "
        "{} (in-sample), 2026 {}; runs left 2025 {}, 2026 {}. Descriptive "
        "only, no significance claim.".format(
            cubs["2025"]["opportunities"], cubs["2026"]["opportunities"],
            cubs["2025"]["flagged_holds"], cubs["2026"]["flagged_holds"],
            fmt(cubs["2025"]["runs_left"]), fmt(cubs["2026"]["runs_left"])),
        "INFERENCE: Verdict **" + analysis["verdict"] + "**.", ""]
    return lines


def render(report):
    primary = report["analyses"]["v3_primary"]
    lines = [
        "# SENDHOLD experiment (2026 holdout)",
        "",
        "FACT: Frozen design v3, sha256 " + report["design_sha256"]
        + "; the 2025 models were frozen before this file was produced.",
        "FACT: The v3 label definition is primary; the pre-registered v2 "
        "definition is reported as a separate analysis.",
        "INFERENCE: Primary verdict **" + report["verdict"] + "** (v3 "
        "labels). Pre-registered v2 definition verdict **"
        + report["verdict_v2_preregistered_definition"] + "**.",
        "INFERENCE: Any positive estimate is upper-bound-style: sends are "
        "selected and the counterfactual for holds is extrapolated.",
        "",
        "## Analyses",
        ""]
    for name, analysis in report["analyses"].items():
        lines += render_analysis(name, analysis)
    lines += ["## Examples", ""]
    if report["examples"]:
        for item in report["examples"]:
            lines.append(
                "FACT: flagged hold, game {}, {} with {} out(s) before "
                "the play, P(safe) {} against p* {}.".format(
                    md_escape(item["game_id"]), md_escape(item["hit_type"]),
                    item["outs"], fmt(item["p_safe"]),
                    fmt(item["p_star"])))
    else:
        lines.append("FACT: No flagged-hold examples.")
    lines += [
        "",
        "UNKNOWN: Whether held runners would have been safe if sent; the "
        "feed does not record the coach's sign, the runner's jump, or the "
        "counterfactual.",
        "UNKNOWN: Trailing runners and later events are ignored in the "
        "run-value accounting.",
        "INFERENCE: Mode of the primary analysis is "
        + md_escape(primary["mode"]) + ".",
        ""]
    return "\n".join(lines)


def run_evaluate(root, resamples=1000, seed=SEED):
    root = Path(root)
    fit_path = root / "data/sendhold_fit.json"
    if not fit_path.exists():
        raise FileNotFoundError(
            "data/sendhold_fit.json is missing; run sendhold_fit first")
    frozen = json.loads(fit_path.read_text())
    if frozen.get("design_sha256") != DESIGN_SHA256:
        raise RuntimeError("frozen fit does not match the design hash")
    rows = json.loads(
        (root / "data/sendhold_opportunity_table.json").read_text())
    fit_raw = [row for row in rows if row.get("season") == FIT_SEASON]
    eval_raw = [row for row in rows if row.get("season") == HOLDOUT_SEASON]
    if not eval_raw:
        raise RuntimeError("no 2026 rows in the opportunity table")
    report = evaluate_rows(fit_raw, eval_raw, frozen, resamples, seed)
    report["fit_sha256"] = hashlib.sha256(fit_path.read_bytes()).hexdigest()
    atomic_json(root / "research/sendhold_experiment.json", report)
    (root / "research/SENDHOLD_EXPERIMENT.md").write_text(render(report))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--resamples", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args(argv)
    try:
        run_evaluate(args.root, args.resamples, args.seed)
    except FileNotFoundError as error:
        parser.exit(2, "{}\n".format(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
