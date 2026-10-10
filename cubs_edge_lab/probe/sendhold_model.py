"""Small deterministic modeling primitives for the SENDHOLD study.

Everything here is pure Python and has no knowledge of seasons: callers decide
which rows may be used. Covariates are those of the frozen design (v3).
"""
import math
import random

SEED = 20261010
EVENTS_PER_PARAMETER = 10
EARLY_STOP_SENT_OUT = 30
FLAG_MARGIN = 0.05

# Full covariate set; every column is numeric after encoding. Zone is encoded
# as left/right dummies against a center-field reference.
FULL_COLUMNS = (
    "sprint_speed", "speed_fallback", "arm_strength", "arm_fallback",
    "arm_missing", "hit_double", "coord_x", "coord_y", "zone_left",
    "zone_right", "outs", "inning", "score_difference")
# Reduced set fixed by the design: speed, zone grouped left/center/right, outs.
REDUCED_COLUMNS = ("sprint_speed", "zone_left", "zone_right", "outs")

# Hit location is the fielder position code of the feed. Simplest defensible
# grouping: 7 and the left-side infield (5, 6) are left; 8 and the battery
# (1, 2) are center; 9 and the right-side infield (3, 4) are right. Unknown or
# missing zones are center. The mapping is fixed before any fit.
ZONE_GROUPS = {"1": "center", "2": "center", "3": "right", "4": "right",
               "5": "left", "6": "left", "7": "left", "8": "center",
               "9": "right"}


def sigmoid(value):
    value = max(-35.0, min(35.0, value))
    return 1.0 / (1.0 + math.exp(-value))


def logit(p, eps=1e-6):
    p = min(1.0 - eps, max(eps, p))
    return math.log(p / (1.0 - p))


def zone_group(zone):
    if zone is None:
        return "center"
    return ZONE_GROUPS.get(str(zone).strip(), "center")


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def featurize(row):
    """Return a copy of ``row`` with the numeric model features added."""
    result = dict(row)
    coordinates = row.get("hit_coordinates") or {}
    group = zone_group(row.get("hit_zone"))
    arm = _number(row.get("arm_strength"))
    result.update({
        "sprint_speed": _number(row.get("sprint_speed")),
        "speed_fallback": float(bool(
            row.get("sprint_speed_same_season_fallback"))),
        "arm_strength": arm,
        "arm_fallback": float(bool(
            row.get("arm_strength_same_season_fallback"))),
        "arm_missing": float(arm is None),
        "hit_double": float(row.get("hit_type") == "double"),
        "coord_x": _number(coordinates.get("coordX")),
        "coord_y": _number(coordinates.get("coordY")),
        "zone_left": float(group == "left"),
        "zone_right": float(group == "right"),
        "outs": _number(row.get("outs")),
        "inning": _number(row.get("inning")),
        "score_difference": _number(
            row.get("score_difference_batting_view")),
        "zone_group": group,
    })
    return result


def quantile(values, q):
    """Linear-interpolation quantile (the usual type 7 definition)."""
    if not values:
        raise ValueError("quantile requires values")
    ordered = sorted(values)
    index = q * (len(ordered) - 1)
    low = int(math.floor(index))
    high = min(len(ordered) - 1, low + 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (index - low)


def _solve_many(matrix, columns):
    """Solve ``matrix * x = column`` for each right-hand column."""
    size = len(matrix)
    augmented = [list(matrix[i]) + [column[i] for column in columns]
                 for i in range(size)]
    for col in range(size):
        pivot = max(range(col, size), key=lambda r: abs(augmented[r][col]))
        if abs(augmented[pivot][col]) < 1e-12:
            augmented[pivot][col] += 1e-8
        augmented[col], augmented[pivot] = augmented[pivot], augmented[col]
        divisor = augmented[col][col]
        augmented[col] = [value / divisor for value in augmented[col]]
        for r in range(size):
            if r != col:
                scale = augmented[r][col]
                if scale:
                    augmented[r] = [a - scale * b for a, b in
                                    zip(augmented[r], augmented[col])]
    return [[augmented[i][size + k] for i in range(size)]
            for k in range(len(columns))]


def _newton_terms(matrix, target, beta, ridge):
    width = len(beta)
    gradient = [0.0] * width
    hessian = [[0.0] * width for _ in range(width)]
    for x, y in zip(matrix, target):
        p = sigmoid(sum(a * b for a, b in zip(x, beta)))
        weight = max(1e-9, p * (1.0 - p))
        residual = y - p
        for i in range(width):
            xi = x[i]
            gradient[i] += xi * residual
            scaled = weight * xi
            row = hessian[i]
            for j in range(i, width):
                row[j] += scaled * x[j]
    for i in range(width):
        for j in range(i):
            hessian[i][j] = hessian[j][i]
    for i in range(1, width):
        gradient[i] -= ridge * beta[i]
        hessian[i][i] += ridge
    return gradient, hessian


def fit_logistic_matrix(matrix, target, iterations=60, ridge=1e-4):
    """Ridge-stabilized logistic regression by Newton steps.

    Column 0 must be the intercept; it is not penalized. Returns the
    coefficients, standard errors from the final penalized Hessian, and a
    convergence flag. A ridge term keeps near-separation finite.
    """
    if not matrix:
        raise ValueError("cannot fit logistic model without rows")
    if len({bool(y) for y in target}) < 2:
        raise ValueError("logistic fit needs both outcome classes")
    beta = [0.0] * len(matrix[0])
    converged = False
    for _ in range(iterations):
        gradient, hessian = _newton_terms(matrix, target, beta, ridge)
        step = _solve_many(hessian, [gradient])[0]
        largest = max(abs(value) for value in step)
        if largest > 5.0:
            step = [value * 5.0 / largest for value in step]
        beta = [a + b for a, b in zip(beta, step)]
        if max(abs(value) for value in step) < 1e-8:
            converged = True
            break
    _, hessian = _newton_terms(matrix, target, beta, ridge)
    size = len(beta)
    inverse = _solve_many(
        hessian, [[float(i == k) for i in range(size)] for k in range(size)])
    errors = [math.sqrt(max(0.0, inverse[i][i])) for i in range(size)]
    return {"coefficients": beta, "standard_errors": errors,
            "converged": converged}


def fit_model(rows, columns, target):
    """Fit a logistic model on featurized rows with standardized columns.

    ``target(row)`` returns the outcome. Missing values are replaced by the
    training mean (a standardized 0). Coefficients are therefore per training
    standard deviation of each column.
    """
    columns = list(columns)
    center, scale = {}, {}
    for name in columns:
        present = [row[name] for row in rows if row.get(name) is not None]
        mean = sum(present) / len(present) if present else 0.0
        spread = (math.sqrt(sum((v - mean) ** 2 for v in present)
                            / len(present)) if present else 0.0)
        center[name] = mean
        scale[name] = spread if spread > 1e-12 else 1.0
    model = {"columns": columns, "center": center, "scale": scale}
    matrix = [encode(model, row) for row in rows]
    outcomes = [float(bool(target(row))) for row in rows]
    fit = fit_logistic_matrix(matrix, outcomes)
    model.update(fit)
    model["n"] = len(rows)
    model["events"] = int(sum(outcomes))
    return model


def encode(model, row):
    values = [1.0]
    for name in model["columns"]:
        value = row.get(name)
        if value is None:
            values.append(0.0)
        else:
            values.append((value - model["center"][name])
                          / model["scale"][name])
    return values


def predict(model, row):
    return sigmoid(sum(a * b for a, b in
                       zip(encode(model, row), model["coefficients"])))


def choose_covariates(sent_out, full=FULL_COLUMNS, reduced=REDUCED_COLUMNS,
                      events_per_parameter=EVENTS_PER_PARAMETER):
    """Events-per-parameter rule: full set only with enough SENT_OUT runners.

    Parameters count the intercept. The full set is used when SENT_OUT is at
    least ``events_per_parameter`` times its parameter count.
    """
    parameters = len(full) + 1
    required = events_per_parameter * parameters
    use_full = sent_out >= required
    return {"name": "full" if use_full else "reduced",
            "columns": list(full if use_full else reduced),
            "sent_out": sent_out, "events_per_parameter": events_per_parameter,
            "full_parameters": parameters, "required_sent_out": required,
            "reduced_parameters": len(reduced) + 1}


def support_threshold(send_propensities):
    """2.5th percentile of the sends' propensity."""
    if not send_propensities:
        raise ValueError("send propensities are required")
    return quantile(send_propensities, 0.025)


def break_even(re_hold, re_out, re_scored):
    """p* = (RE[hold] - RE[out]) / (RE[scored] + 1 - RE[out])."""
    denominator = re_scored + 1.0 - re_out
    if denominator <= 0:
        raise ValueError("break-even denominator must be positive")
    return (re_hold - re_out) / denominator


def state_value(table, mask, outs):
    """Run expectancy of a base-out state; three outs end the inning (0)."""
    if outs >= 3:
        return 0.0
    return table.get((mask, outs))


def brier(predictions, outcomes):
    return (sum((p - y) ** 2 for p, y in zip(predictions, outcomes))
            / len(outcomes))


def calibration_slope(predictions, outcomes):
    """Slope of a logistic regression of the outcome on logit(prediction)."""
    if len({bool(y) for y in outcomes}) < 2:
        return None
    matrix = [[1.0, logit(p)] for p in predictions]
    return fit_logistic_matrix(matrix, [float(y) for y in outcomes],
                               ridge=0.0)["coefficients"][1]


def game_bootstrap(statistic, *group_sets, resamples=1000, seed=SEED):
    """Resample whole games independently within each group set.

    Each group set maps a game id to its rows. ``statistic`` is called once
    per resample with one row list per group set and may refit models. The
    result is the list of statistic values in resample order.
    """
    keysets = [sorted(groups) for groups in group_sets]
    if not all(keysets):
        raise ValueError("bootstrap requires games")
    rng = random.Random(seed)
    results = []
    for _ in range(resamples):
        samples = []
        for groups, keys in zip(group_sets, keysets):
            drawn = [rng.choice(keys) for _ in keys]
            samples.append([row for key in drawn for row in groups[key]])
        results.append(statistic(*samples))
    return results


def percentile_interval(values, level=0.95):
    values = [v for v in values if v is not None]
    if not values:
        return None
    tail = (1.0 - level) / 2.0
    return {"lower": quantile(values, tail),
            "upper": quantile(values, 1 - tail), "n": len(values)}


def _binomial_cdf(k, n, p):
    if k < 0:
        return 0.0
    if k >= n:
        return 1.0
    log_p, log_q = math.log(p), math.log(1.0 - p)
    total = 0.0
    for i in range(k + 1):
        total += math.exp(
            math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1)
            + i * log_p + (n - i) * log_q)
    return min(1.0, total)


def clopper_pearson(successes, trials, alpha=0.05):
    """Exact two-sided binomial interval (bisection on the binomial CDF)."""
    if trials <= 0:
        return None
    lower, upper = 0.0, 1.0
    if successes > 0:
        low, high = 0.0, 1.0
        for _ in range(60):
            mid = (low + high) / 2
            if 1.0 - _binomial_cdf(successes - 1, trials, mid) < alpha / 2:
                low = mid
            else:
                high = mid
        lower = (low + high) / 2
    if successes < trials:
        low, high = 0.0, 1.0
        for _ in range(60):
            mid = (low + high) / 2
            if _binomial_cdf(successes, trials, mid) > alpha / 2:
                low = mid
            else:
                high = mid
        upper = (low + high) / 2
    return {"lower": lower, "upper": upper}
