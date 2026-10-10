# SENDHOLD experiment (2026 holdout)

FACT: Frozen design v3, sha256 a852b921c1c218f6f8bd525b4c1397923b8d12651dfc829b084b60e35b7b0a1a; the 2025 models were frozen before this file was produced.
FACT: The v3 label definition is primary; the pre-registered v2 definition is reported as a separate analysis.
INFERENCE: Primary verdict **NEGATIVE** (v3 labels). Pre-registered v2 definition verdict **NEGATIVE**.
INFERENCE: Any positive estimate is upper-bound-style: sends are selected and the counterfactual for holds is extrapolated.

## Analyses

### v3_primary

FACT: Labels v3; fallback rows dropped: false; 2025 SENT_OUT 67; rows 2025/2026 4331/4340; mode MODEL.
FACT: Covariate set reduced (2025 SENT_OUT 67 against 140 required for the full set); support threshold 0.2529.
FACT: 2026 sends 1927, holds 2329; Brier model 0.0354, constant 0.0355, outs-only 0.0355; difference to constant -0.0001 (interval [-0.0003, 0.0005]), to outs-only -0.0001 (interval [-0.0003, 0.0003]).
FACT: Holds below the propensity support threshold: 199 of 2329 (share 0.0854); assessed holds 2130; flagged holds 1533.
FACT: Bootstrap 1000 resamples (1000 usable), seed 20261010.

| Criterion | Value | 95% interval | Passed |
|---|---:|---|---|
| Brier difference to constant | -0.0001 | [-0.0003, 0.0005] | false |
| Calibration slope | 0.8420 | [-0.2065, 1.7621] | true |
| Runs left (2026) | 326.6254 | [292.0959, 359.6092] | true |
| Negative control (realized flagged-send success) | 0.9567 | [0.9559, 0.9748] | true |

FACT: Cubs opportunities 2025 157 and 2026 159; flagged holds 2025 54 (in-sample), 2026 62; runs left 2025 11.6591, 2026 13.4059. Descriptive only, no significance claim.
INFERENCE: Verdict **NEGATIVE**.

### v2_preregistered

FACT: Labels v2; fallback rows dropped: false; 2025 SENT_OUT 67; rows 2025/2026 4331/4340; mode MODEL.
FACT: Covariate set reduced (2025 SENT_OUT 67 against 140 required for the full set); support threshold 0.0992.
FACT: 2026 sends 683, holds 2329; Brier model 0.0916, constant 0.0932, outs-only 0.0931; difference to constant -0.0015 (interval [-0.0035, 0.0018]), to outs-only -0.0014 (interval [-0.0033, 0.0013]).
FACT: Holds below the propensity support threshold: 155 of 2329 (share 0.0666); assessed holds 2174; flagged holds 1087.
FACT: Bootstrap 1000 resamples (1000 usable), seed 20261010.

| Criterion | Value | 95% interval | Passed |
|---|---:|---|---|
| Brier difference to constant | -0.0015 | [-0.0035, 0.0018] | false |
| Calibration slope | 1.2501 | [0.0310, 2.0256] | true |
| Runs left (2026) | 155.8200 | [101.5401, 217.4303] | true |
| Negative control (realized flagged-send success) | 0.8891 | [0.8732, 0.9243] | true |

FACT: Cubs opportunities 2025 157 and 2026 159; flagged holds 2025 39 (in-sample), 2026 48; runs left 2025 5.8723, 2026 6.4483. Descriptive only, no significance claim.
INFERENCE: Verdict **NEGATIVE**.

### v3_ambiguous_as_safe

FACT: Labels v3_ambiguous_as_safe; fallback rows dropped: false; 2025 SENT_OUT 67; rows 2025/2026 4331/4340; mode MODEL.
FACT: Covariate set reduced (2025 SENT_OUT 67 against 140 required for the full set); support threshold 0.2583.
FACT: 2026 sends 1986, holds 2329; Brier model 0.0344, constant 0.0345, outs-only 0.0345; difference to constant -0.0001 (interval [-0.0003, 0.0004]), to outs-only -0.0001 (interval [-0.0003, 0.0003]).
FACT: Holds below the propensity support threshold: 180 of 2329 (share 0.0773); assessed holds 2149; flagged holds 1566.
FACT: Bootstrap 1000 resamples (1000 usable), seed 20261010.

| Criterion | Value | 95% interval | Passed |
|---|---:|---|---|
| Brier difference to constant | -0.0001 | [-0.0003, 0.0004] | false |
| Calibration slope | 0.8932 | [-0.2085, 1.8096] | true |
| Runs left (2026) | 332.1030 | [297.0813, 363.0121] | true |
| Negative control (realized flagged-send success) | 0.9581 | [0.9574, 0.9755] | true |

FACT: Cubs opportunities 2025 157 and 2026 159; flagged holds 2025 54 (in-sample), 2026 63; runs left 2025 11.7564, 2026 13.5993. Descriptive only, no significance claim.
INFERENCE: Verdict **NEGATIVE**.

### v3_fallback_dropped

FACT: Labels v3; fallback rows dropped: true; 2025 SENT_OUT 53; rows 2025/2026 3359/3187; mode MODEL.
FACT: Covariate set reduced (2025 SENT_OUT 53 against 140 required for the full set); support threshold 0.2376.
FACT: 2026 sends 1375, holds 1751; Brier model 0.0404, constant 0.0404, outs-only 0.0406; difference to constant -0.0000 (interval [-0.0004, 0.0008]), to outs-only -0.0002 (interval [-0.0005, 0.0004]).
FACT: Holds below the propensity support threshold: 150 of 1751 (share 0.0857); assessed holds 1601; flagged holds 1064.
FACT: Bootstrap 1000 resamples (1000 usable), seed 20261010.

| Criterion | Value | 95% interval | Passed |
|---|---:|---|---|
| Brier difference to constant | -0.0000 | [-0.0004, 0.0008] | false |
| Calibration slope | 0.7545 | [-0.7623, 2.0723] | true |
| Runs left (2026) | 236.8910 | [211.7756, 265.0870] | true |
| Negative control (realized flagged-send success) | 0.9482 | [0.9542, 0.9765] | false |

FACT: Cubs opportunities 2025 157 and 2026 159; flagged holds 2025 37 (in-sample), 2026 50; runs left 2025 7.9492, 2026 11.2647. Descriptive only, no significance claim.
INFERENCE: Verdict **NEGATIVE**.

## Examples

FACT: flagged hold, game 822679, double with 1 out(s) before the play, P(safe) 0.9684 against p* 0.8086.
FACT: flagged hold, game 822680, single with 1 out(s) before the play, P(safe) 0.9650 against p* 0.7591.
FACT: flagged hold, game 822681, double with 1 out(s) before the play, P(safe) 0.9488 against p* 0.8086.
FACT: flagged hold, game 822682, single with 1 out(s) before the play, P(safe) 0.9659 against p* 0.7591.
FACT: flagged hold, game 822686, double with 1 out(s) before the play, P(safe) 0.9306 against p* 0.8086.

UNKNOWN: Whether held runners would have been safe if sent; the feed does not record the coach's sign, the runner's jump, or the counterfactual.
UNKNOWN: Trailing runners and later events are ignored in the run-value accounting.
INFERENCE: Mode of the primary analysis is MODEL.
