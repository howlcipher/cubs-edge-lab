# MILBFA evaluation

FACT: This report is rendered only from `validation.json`. Outcomes use cached league-wide MLB season statistics. No 2025 cohort outcomes were evaluated.

FACT: MLBAM data source: MLB Stats API. Short examples and player-level records are omitted; only aggregates are reported.

## Base rates

| Cohort | Segment | N | Positive | Positive rate | Any appearance |
|---:|---|---:|---:|---:|---:|
| 2018 | primary | 452 | 20 | 0.044248 | 48 |
| 2018 | pitchers | 206 | 7 | 0.033981 | 25 |
| 2018 | hitters | 246 | 13 | 0.052846 | 23 |
| 2018 | whole_pool | 584 | 57 | 0.097603 | 109 |
| 2019 | primary | 465 | 12 | 0.025806 | 27 |
| 2019 | pitchers | 231 | 9 | 0.038961 | 18 |
| 2019 | hitters | 234 | 3 | 0.012821 | 9 |
| 2019 | whole_pool | 629 | 68 | 0.108108 | 106 |
| 2021 | primary | 555 | 14 | 0.025225 | 57 |
| 2021 | pitchers | 299 | 8 | 0.026756 | 34 |
| 2021 | hitters | 256 | 6 | 0.023438 | 23 |
| 2021 | whole_pool | 901 | 174 | 0.193119 | 257 |
| 2022 | primary | 509 | 12 | 0.023576 | 40 |
| 2022 | pitchers | 275 | 7 | 0.025455 | 27 |
| 2022 | hitters | 234 | 5 | 0.021368 | 13 |
| 2022 | whole_pool | 852 | 177 | 0.207746 | 255 |
| 2023 | primary | 523 | 22 | 0.042065 | 51 |
| 2023 | pitchers | 307 | 15 | 0.04886 | 31 |
| 2023 | hitters | 216 | 7 | 0.032407 | 20 |
| 2023 | whole_pool | 825 | 171 | 0.207273 | 237 |
| 2024 | primary | 451 | 23 | 0.050998 | 54 |
| 2024 | pitchers | 249 | 15 | 0.060241 | 30 |
| 2024 | hitters | 202 | 8 | 0.039604 | 24 |
| 2024 | whole_pool | 636 | 91 | 0.143082 | 154 |

FACT: Evaluation stopped at the preregistered early-stop rule.
FACT: Validation primary positives: 23; early-stop minimum: 30.

UNKNOWN: Validation metrics, bootstrap intervals, and comparator selection are null after early stop.
INFERENCE: The persistence ranking can be nearly degenerate in the primary segment because players in that segment had no MLB appearance in season Y.
