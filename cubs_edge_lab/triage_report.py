"""Render the public aggregate experiment report from validation JSON."""

import json


def render(payload):
    lines = ["# MILBFA evaluation", "",
             "FACT: This report is rendered only from `validation.json`. Outcomes use cached league-wide MLB season statistics. No 2025 cohort outcomes were evaluated.",
             "", "FACT: MLBAM data source: MLB Stats API. Short examples and player-level records are omitted; only aggregates are reported.",
             "", "## Base rates", "", "| Cohort | Segment | N | Positive | Positive rate | Any appearance |",
             "|---:|---|---:|---:|---:|---:|"]
    for year, segments in payload["base_rates"].items():
        for segment, row in segments.items():
            lines.append(f"| {year} | {segment} | {row['n']} | {row['positives']} | {row['positive_rate']} | {row['any_appearance']} |")
    if payload["early_stop"]:
        validation = payload["base_rates"][str(payload["config"]["validation_year"])]
        lines.extend(["", "FACT: Evaluation stopped at the preregistered early-stop rule.",
                      "FACT: Validation primary positives: "
                      + str(validation["primary"]["positives"])
                      + "; early-stop minimum: "
                      + str(payload["config"]["early_stop_positive_minimum"])
                      + ".",
                      "", "UNKNOWN: Validation metrics, bootstrap intervals, and comparator selection are null after early stop.",
                      "INFERENCE: The persistence ranking can be nearly degenerate in the primary segment because players in that segment had no MLB appearance in season Y."])
        return "\n".join(lines) + "\n"
    lines.extend(["", "## Validation metrics", "", "FACT: Validation metrics cover the primary segment.",
                  "", "| Ranking | AUROC | Hits @25 | Precision @25 | Hits @50 | Precision @50 | Hits @100 | Precision @100 |",
                  "|---|---:|---:|---:|---:|---:|---:|---:|"])
    metrics = payload["validation"]["rankings"]
    for name, row in metrics.items():
        cells = [row["auroc"]]
        for k in ("25", "50", "100"):
            cells += [row["top_k"][k]["hits"], row["top_k"][k]["precision"]]
        lines.append("| " + name + " | " + " | ".join(map(str, cells)) + " |")
    lines.extend(["", "FACT: Selected L2 strength: " + str(payload["chosen_l2_strength"]) + ".",
                  "FACT: Comparator selected for the later holdout: " + payload["chosen_comparator"] + ".",
                  "", "## Bootstrap: M minus baseline AUROC", "",
                  "FACT: Paired bootstrap intervals use the configured resample count and seed.",
                  "", "| Baseline | Mean difference | 95% interval | Valid resamples |",
                  "|---|---:|---|---:|"])
    for name, row in payload["validation"]["bootstrap_m_minus_baseline"].items():
        lines.append(f"| {name} | {row['mean_difference']} | {json.dumps(row['percentile_95'])} | {row['valid_resamples']} |")
    lines.extend(["", "## Calibration", "", "FACT: M calibration bins for validation primary segment.",
                  "", "| Bin | Count | Mean probability | Outcome rate |", "|---:|---:|---:|---:|"])
    for row in payload["validation"]["calibration"]:
        lines.append(f"| {row['bin']} | {row['count']} | {row['mean_probability']} | {row['outcome_rate']} |")
    lines.extend(["", "## Rolling-origin test", "", "FACT: Each test year trains on all earlier available cohorts; the L2 strength selected on validation is reused.",
                  "", "| Year | N | Positives | Base rate | M AUROC | Hits @50 | Precision @50 |",
                  "|---:|---:|---:|---:|---:|---:|---:|"])
    for year, row in payload["rolling_origin"].items():
        model = row.get("rankings", {}).get("M")
        top = model["top_k"]["50"] if model else {"hits": None, "precision": None}
        auroc = model["auroc"] if model else None
        lines.append(f"| {year} | {row['n']} | {row['positives']} | {row['base_rate']} | {auroc} | {top['hits']} | {top['precision']} |")
    lines.extend(["", "INFERENCE: The comparator is a frozen selection rule for a later holdout comparison; it does not imply a holdout result.",
                  "UNKNOWN: The 2025 cohort remains unevaluated by design."])
    return "\n".join(lines) + "\n"
