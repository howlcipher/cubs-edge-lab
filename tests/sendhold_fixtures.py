"""Synthetic SENDHOLD fixtures. Every value here is invented for tests."""
import json
import math
from pathlib import Path

# Low-discrepancy fractional parts make fixtures deterministic and give
# outcome rates very close to their probabilities without random draws.
STEPS = {"speed": 0.6180339887498949, "outcome": 0.41421356237309515,
         "send": 0.7320508075688772, "zone": 0.14159265358979312,
         "outs": 0.2360679774997898}
OFFSETS = {"speed": 0.0, "outcome": 0.2, "send": 0.5, "zone": 0.3,
           "outs": 0.0}

# Made-up run-expectancy table; masks use 1B=1, 2B=2, 3B=4.
RE_TABLE = {(1, 0): 0.9, (1, 1): 0.55, (1, 2): 0.25,
            (2, 0): 1.1, (2, 1): 0.7, (2, 2): 0.35,
            (5, 0): 1.5, (5, 1): 0.95, (6, 0): 1.7, (6, 1): 1.2}
# Break-even values for RE_TABLE, computed by hand:
#   single|0 (1.5 - 0.55) / (0.9 + 1 - 0.55) = 0.95 / 1.35
#   single|1 (0.95 - 0.25) / (0.55 + 1 - 0.25) = 0.70 / 1.30
#   double|0 (1.7 - 0.7) / (1.1 + 1 - 0.7) = 1.00 / 1.40
#   double|1 (1.2 - 0.35) / (0.7 + 1 - 0.35) = 0.85 / 1.35
HAND_P_STAR = {"single|0": 0.95 / 1.35, "single|1": 0.70 / 1.30,
               "double|0": 1.00 / 1.40, "double|1": 0.85 / 1.35}
# Hold states so costly that no hold can ever be worth a send.
RE_TABLE_NO_FLAGS = {**RE_TABLE, (5, 0): 3.0, (5, 1): 3.0, (6, 0): 3.0,
                     (6, 1): 3.0}


def frac(index, name):
    return (index * STEPS[name] + OFFSETS[name]) % 1.0


def sigmoid(value):
    return 1.0 / (1.0 + math.exp(-value))


def make_rows(season, count, slope, send_rate=0.45):
    """Synthetic opportunity rows; success depends on speed with ``slope``."""
    rows = []
    for index in range(count):
        speed = 25.0 + 4.0 * frac(index, "speed")
        probability = sigmoid(slope * (speed - 27.0) + 0.4)
        zone = ("7", "8", "9")[min(2, int(frac(index, "zone") * 3))]
        sent = frac(index, "send") < send_rate
        safe = frac(index, "outcome") < probability
        label = ("SENT_SAFE" if safe else "SENT_OUT") if sent else "HOLD"
        label_v3 = label
        if label == "SENT_SAFE" and index % 7 == 0:
            # The v2 rule excluded these; v3 keeps them as sends.
            label = "AMBIGUOUS"
        if label == "SENT_SAFE" and index % 11 == 0:
            label, label_v3 = "AMBIGUOUS", "AMBIGUOUS"
        rows.append({
            "season": season, "game_id": season * 1000 + index // 3,
            "runner_id": 100 + index, "label": label, "label_v3": label_v3,
            "base_at_contact": "2B",
            "sprint_speed": speed,
            "sprint_speed_same_season_fallback": index % 9 == 0,
            "arm_strength": 85.0 if index % 4 else None,
            "arm_strength_same_season_fallback": False,
            "fielder_outfielder": bool(index % 4),
            "hit_type": "single" if index % 2 == 0 else "double",
            "hit_coordinates": {"coordX": 100.0 + index % 50,
                                "coordY": 80.0 + index % 30},
            "hit_zone": zone,
            "outs": 0 if frac(index, "outs") < 0.5 else 1,
            "inning": 1 + index % 9,
            "score_difference_batting_view": index % 5 - 2,
            "batting_team_id": 112 if index % 5 == 0 else 117})
    return rows


def data_report(table, seasons=None):
    """Shape of research/sendhold_data.json that the fit reads."""
    states = [{"outs": outs, "bases_mask": mask, "count": 10,
               "mean_runs": table.get((mask, outs))}
              for outs in range(3) for mask in range(8)]
    return {"facts": {"run_expectancy_2025": {"states": states},
                      "seasons": seasons or {}},
            "inference": [], "unknown": []}


def write_root(root, rows, table=None, report_seasons=None):
    """Write the table and data report a fit or evaluation reads."""
    root = Path(root)
    (root / "data").mkdir(parents=True, exist_ok=True)
    (root / "research").mkdir(parents=True, exist_ok=True)
    (root / "data/sendhold_opportunity_table.json").write_text(
        json.dumps(rows) + "\n")
    (root / "research/sendhold_data.json").write_text(
        json.dumps(data_report(table or RE_TABLE, report_seasons)) + "\n")
