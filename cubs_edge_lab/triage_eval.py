"""Deterministic metrics and the preregistration guard."""

import hashlib
import json
import math
from pathlib import Path
import random

from .triage_config import BOOTSTRAP_RESAMPLES, BOOTSTRAP_SEED
from .triage_config import L2_GRID, TOP_K
from .triage import rank


def auc(labels, scores):
    pairs = sorted(zip(scores, labels))
    positives = sum(bool(label) for label in labels)
    negatives = len(labels) - positives
    if not positives or not negatives:
        return None
    rank_sum = 0.0
    index = 0
    while index < len(pairs):
        end = index + 1
        while end < len(pairs) and pairs[end][0] == pairs[index][0]:
            end += 1
        average_rank = ((index + 1) + end) / 2
        rank_sum += average_rank * sum(bool(x[1]) for x in pairs[index:end])
        index = end
    return (rank_sum - positives * (positives + 1) / 2) / (
        positives * negatives
    )


def calibration(labels, probabilities, bins=10):
    result = []
    for index in range(bins):
        low, high = index / bins, (index + 1) / bins
        selected = [
            (label, prob)
            for label, prob in zip(labels, probabilities)
            if low <= prob < high or index == bins - 1 and prob == 1
        ]
        result.append(
            {
                "bin": index,
                "count": len(selected),
                "mean_probability": (
                    sum(p for _, p in selected) / len(selected)
                    if selected
                    else None
                ),
                "outcome_rate": (
                    sum(bool(y) for y, _ in selected) / len(selected)
                    if selected
                    else None
                ),
            }
        )
    return result


def paired_bootstrap(
    labels,
    model_scores,
    comparator_scores,
    resamples=BOOTSTRAP_RESAMPLES,
    seed=BOOTSTRAP_SEED,
):
    rng = random.Random(seed)
    differences = []
    size = len(labels)
    for _ in range(resamples):
        indices = [rng.randrange(size) for _ in range(size)] if size else []
        y = [labels[i] for i in indices]
        m = [model_scores[i] for i in indices]
        c = [comparator_scores[i] for i in indices]
        a, b = auc(y, m), auc(y, c)
        if a is not None and b is not None:
            differences.append(a - b)
    differences.sort()
    if not differences:
        interval = [None, None]
    else:
        interval = [
            differences[int(0.025 * (len(differences) - 1))],
            differences[int(0.975 * (len(differences) - 1))],
        ]
    return {
        "resamples": resamples,
        "seed": seed,
        "valid_resamples": len(differences),
        "mean_difference": (
            sum(differences) / len(differences) if differences else None
        ),
        "percentile_95": interval,
    }


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def evaluation_files(root):
    root = Path(root)
    return [
        root / "cubs_edge_lab/triage.py",
        root / "cubs_edge_lab/triage_eval.py",
        root / "cubs_edge_lab/triage_config.py",
    ]


def preregistration_payload(root):
    root = Path(root)
    files = evaluation_files(root)
    files.append(root / "research/validation.json")
    hashes = {str(path.relative_to(root)): sha256_file(path) for path in files}
    combined = hashlib.sha256(
        json.dumps(hashes, sort_keys=True).encode()
    ).hexdigest()
    return {"sha256": hashes, "combined_sha256": combined}


def require_preregistered_holdout(root):
    root = Path(root)
    path = root / "research/preregistration.json"
    if not path.is_file():
        raise RuntimeError(
            "2025 holdout is locked: preregistration is missing"
        )
    try:
        recorded = json.loads(path.read_text())
    except (ValueError, OSError) as exc:
        raise RuntimeError(
            "2025 holdout is locked: malformed preregistration"
        ) from exc
    expected = preregistration_payload(root)
    if recorded != expected:
        raise RuntimeError(
            "2025 holdout is locked: preregistration hashes do not match"
        )
    return True


def guard_outcome_build(root, year):
    if year == 2025:
        require_preregistered_holdout(root)
    if year > 2025:
        raise ValueError("season-2026 and later data are prohibited")
    return True


class LogisticModel:
    """L2 logistic model with means and scales learned only at fit time."""

    def __init__(self, strength=1.0, iterations=3000, learning_rate=0.05):
        self.strength = float(strength)
        self.iterations = iterations
        self.learning_rate = learning_rate
        self.means = None
        self.scales = None
        self.weights = None

    def fit(self, rows, labels, features):
        if not rows or len(rows) != len(labels):
            raise ValueError("rows and labels must have equal nonzero length")
        matrix = [
            [float(row.get(key, 0) or 0) for key in features] for row in rows
        ]
        width = len(features)
        self.means = [
            sum(row[j] for row in matrix) / len(matrix) for j in range(width)
        ]
        self.scales = []
        for j in range(width):
            variance = sum(
                (row[j] - self.means[j]) ** 2 for row in matrix
            ) / len(matrix)
            self.scales.append(math.sqrt(variance) or 1.0)
        standardized = [
            [(row[j] - self.means[j]) / self.scales[j] for j in range(width)]
            for row in matrix
        ]
        self.weights = [0.0] * (width + 1)
        for _ in range(self.iterations):
            gradient = [0.0] * (width + 1)
            for values, label in zip(standardized, labels):
                linear = self.weights[0] + sum(
                    w * x for w, x in zip(self.weights[1:], values)
                )
                prediction = 1 / (1 + math.exp(-max(-35, min(35, linear))))
                error = prediction - int(bool(label))
                gradient[0] += error
                for j, value in enumerate(values, 1):
                    gradient[j] += error * value
            for j in range(len(gradient)):
                gradient[j] /= len(rows)
                if j:
                    gradient[j] += self.strength * self.weights[j]
                self.weights[j] -= self.learning_rate * gradient[j]
        return self

    def predict_proba(self, rows, features):
        if self.weights is None:
            raise RuntimeError("model is not fitted")
        result = []
        for row in rows:
            values = [
                (float(row.get(key, 0) or 0) - self.means[j]) / self.scales[j]
                for j, key in enumerate(features)
            ]
            linear = self.weights[0] + sum(
                w * x for w, x in zip(self.weights[1:], values)
            )
            result.append(1 / (1 + math.exp(-max(-35, min(35, linear)))))
        return result


def build_outcomes(root, year, players, stats_by_player):
    """Build season Y+1 outcomes only after checking the holdout lock."""
    from .triage_eval import guard_outcome_build
    from .triage import outcome

    guard_outcome_build(root, year)
    result = {}
    for player_id in players:
        result[player_id] = outcome(stats_by_player.get(player_id, ()), year)
    return result


MODEL_FEATURES = ("mlb_pa_y", "mlb_ip_y", "highest_level", "age",
                  "ops", "bb_pct", "k_pct", "k_bb_pct", "era",
                  "mlb_pa_y1", "mlb_ip_y1")
B2_FEATURES = ("mlb_pa_y", "mlb_ip_y", "highest_level", "age")


def top_metrics(rows, method, ks=TOP_K):
    ordered = sorted(rows, key=lambda row: row.get("rankings", {}).get(
        method, (float("inf"),)) if isinstance(row.get("rankings", {}).get(
            method), (int, float)) else row.get("rankings", {}).get(method, 0))
    labels = [bool(row.get("positive")) for row in ordered]
    return {str(k): {"hits": sum(labels[:k]),
                     "precision": (sum(labels[:k]) / min(k, len(labels))
                                   if rows else None)} for k in ks}


def evaluate_rows(rows, training_rows=(), strength=1.0):
    """Score a held-out cohort with train-only model scaling."""
    if not rows:
        return {"n": 0, "base_rate": None, "rankings": {}}
    labels = [int(bool(row["positive"])) for row in rows]
    training = list(training_rows)
    if training and len({int(bool(r["positive"])) for r in training}) == 2:
        model = LogisticModel(strength=strength).fit(
            training, [int(bool(r["positive"])) for r in training],
            MODEL_FEATURES,
        )
        probabilities = model.predict_proba(rows, MODEL_FEATURES)
    else:
        probabilities = [0.5] * len(rows)
    b2_training = [r for r in training
                   if r.get("no_mlb_appearance_y", False)]
    if (len({int(bool(r["positive"])) for r in b2_training}) == 2):
        b2_model = LogisticModel(strength=1.0).fit(
            b2_training, [int(bool(r["positive"])) for r in b2_training],
            B2_FEATURES,
        )
        b2_probabilities = b2_model.predict_proba(rows, B2_FEATURES)
    else:
        b2_probabilities = [0.5] * len(rows)
    scored = []
    for row, probability, b2_probability in zip(
        rows, probabilities, b2_probabilities
    ):
        copy = dict(row)
        copy["m_probability"] = probability
        copy["b2_probability"] = b2_probability
        scored.append(copy)
    methods = ("B0", "B1", "B2", "P", "M")
    rankings = {}
    for method in methods:
        ordered = rank(scored, method)
        top = {
            str(k): {
                "hits": sum(bool(row["positive"]) for row in ordered[:k]),
                "precision": (sum(bool(row["positive"])
                                  for row in ordered[:k]) /
                              min(k, len(ordered))),
            }
            for k in TOP_K
        }
        # AUC consumes scores aligned to the original row order. Rank-based
        # methods receive their own deterministic ordinal scores.
        ordinal = {row["person_id"]: len(ordered) - i
                   for i, row in enumerate(ordered)}
        if method == "M":
            method_scores = [r["m_probability"] for r in scored]
        elif method == "B2":
            method_scores = [r["b2_probability"] for r in scored]
        elif method == "P":
            method_scores = [float(bool(r.get("met_threshold_y")))
                             for r in scored]
        else:
            method_scores = [ordinal[r["person_id"]] for r in scored]
        rankings[method] = {"top_k": top,
                            "auroc": auc(labels, method_scores)}
    return {"n": len(rows), "positives": sum(labels),
            "base_rate": sum(labels) / len(labels), "rankings": rankings,
            "calibration": calibration(labels, probabilities)}


def choose_strength(training_rows, validation_rows):
    """Choose L2 once by validation primary-segment top-50 hits."""
    validation_rows = [row for row in validation_rows
                       if row.get("no_mlb_appearance_y", False)]
    scores = []
    for strength in L2_GRID:
        result = evaluate_rows(validation_rows, training_rows, strength)
        scores.append((result.get("rankings", {}).get("M", {})
                       .get("top_k", {}).get("50", {}).get("hits", 0),
                       -L2_GRID.index(strength), strength))
    return max(scores)[2]
