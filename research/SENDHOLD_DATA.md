# SENDHOLD data report

Only frozen-design data counts and coverage are reported.

## Retrieval and labels

### 2025

FACT: Games retrieved/scheduled: 2430/2430; requests used (shared retrieval ledger): 4868.
FACT: Label counts, v3 definition (primary): SENT_OUT 67, OUT_ELSEWHERE 31, SENT_SAFE 1773, AMBIGUOUS 75, HOLD 2385, OTHER 0.
FACT: Label counts, v2 definition (pre-registered, secondary): SENT_OUT 67, OUT_ELSEWHERE 31, SENT_SAFE 555, AMBIGUOUS 1293, HOLD 2385, OTHER 0.
FACT: Covariate coverage: {"arm_same_season_fallback_rate_among_outfielders": 0.14375326711970726, "outfielder_share": 0.8833987531747864, "prior_season_arm_match_rate_among_outfielders": 0.8311552535284893, "prior_season_sprint_match_rate": 0.887093050103902, "sprint_same_season_fallback_rate": 0.11267605633802817}.

### 2026

FACT: Games retrieved/scheduled: 2430/2430; requests used (shared retrieval ledger): 4868.
FACT: Label counts, v3 definition (primary): SENT_OUT 71, OUT_ELSEWHERE 24, SENT_SAFE 1856, AMBIGUOUS 59, HOLD 2329, OTHER 1.
FACT: Label counts, v2 definition (pre-registered, secondary): SENT_OUT 71, OUT_ELSEWHERE 24, SENT_SAFE 612, AMBIGUOUS 1303, HOLD 2329, OTHER 1.
FACT: Covariate coverage: {"arm_same_season_fallback_rate_among_outfielders": 0.18863518422418266, "outfielder_share": 0.8880184331797235, "prior_season_arm_match_rate_among_outfielders": 0.7799688635184224, "prior_season_sprint_match_rate": 0.8788018433179724, "sprint_same_season_fallback_rate": 0.1195852534562212}.

## 2025 run expectancy

FACT: A half-inning is complete when cumulative outs reach 3. Half-innings that never reach 3 outs are excluded; this rule excludes walk-offs and incomplete or suspended halves. Excluded: 225; complete: 42995.
| Outs | Bases mask (1B=1, 2B=2, 3B=4) | Count | Mean runs remaining |
|---:|---:|---:|---:|
| 0 | 0 | 44639 | 0.4926 |
| 0 | 1 | 10749 | 0.8828 |
| 0 | 2 | 2583 | 1.1370 |
| 0 | 3 | 2702 | 1.5873 |
| 0 | 4 | 272 | 1.2537 |
| 0 | 5 | 892 | 1.8274 |
| 0 | 6 | 527 | 1.9981 |
| 0 | 7 | 726 | 2.4683 |
| 1 | 0 | 32356 | 0.2625 |
| 1 | 1 | 13242 | 0.5118 |
| 1 | 2 | 4160 | 0.6531 |
| 1 | 3 | 4775 | 0.9552 |
| 1 | 4 | 1270 | 0.8803 |
| 1 | 5 | 2024 | 1.2011 |
| 1 | 6 | 1231 | 1.3956 |
| 1 | 7 | 1608 | 1.5721 |
| 2 | 0 | 25678 | 0.1022 |
| 2 | 1 | 13641 | 0.2223 |
| 2 | 2 | 5311 | 0.3080 |
| 2 | 3 | 5738 | 0.4702 |
| 2 | 4 | 2222 | 0.3362 |
| 2 | 5 | 2917 | 0.4676 |
| 2 | 6 | 1332 | 0.6021 |
| 2 | 7 | 1989 | 0.7642 |

FACT: Early-stop condition: SENT_OUT count in 2025 is 67 (threshold: fewer than 30); condition met: false.

INFERENCE: None; no model was fit and no outcome analysis was performed.
UNKNOWN: No additional claims are made beyond cached values and stated counting rules.
