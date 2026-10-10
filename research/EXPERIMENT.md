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
<!-- EXPLORATORY WHOLE POOL START -->
## EXPLORATORY: whole pool

EXPLORATORY FACT: Cohorts evaluated: 2018, 2019, 2021, 2022, 2023, 2024; validation year 2024; rolling-origin years 2021, 2022, 2023.
EXPLORATORY FACT: The validation whole-pool comparator was B0; selected L2 strength was 0.01.
EXPLORATORY FACT: Source attribution: MLBAM, MLB Stats API. Only cohort aggregates are reported.
EXPLORATORY FACT: This section supports no usefulness claim or recommendation.

EXPLORATORY FACT: Top-k hits, precision, AUROC, calibration, and paired-bootstrap AUC differences (M minus each baseline) are reported below.

EXPLORATORY FACT: 2024 whole_pool ranking metrics table:
| Ranking | N | Positives | Top 25 hits | Top 25 precision | Top 50 hits | Top 50 precision | Top 100 hits | Top 100 precision | AUROC |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| B0 | 636 | 91 | 19 | 0.76 | 32 | 0.64 | 50 | 0.5 | 0.83948 |
| B1 | 636 | 91 | 20 | 0.8 | 24 | 0.48 | 46 | 0.46 | 0.818893 |
| B2 | 636 | 91 | 11 | 0.44 | 20 | 0.4 | 35 | 0.35 | 0.726888 |
| P | 636 | 91 | 16 | 0.64 | 25 | 0.5 | 51 | 0.51 | 0.737998 |
| M | 636 | 91 | 20 | 0.8 | 38 | 0.76 | 53 | 0.53 | 0.823047 |
EXPLORATORY FACT: 2024 whole_pool M calibration table (bin, count, mean probability, outcome rate):
| Bin | Count | Mean probability | Outcome rate |
|---:|---:|---:|---:|
| 0 | 455 | 0.04087 | 0.059341 |
| 1 | 69 | 0.145787 | 0.144928 |
| 2 | 32 | 0.247141 | 0.1875 |
| 3 | 19 | 0.335369 | 0.157895 |
| 4 | 11 | 0.456715 | 0.636364 |
| 5 | 12 | 0.540594 | 0.75 |
| 6 | 11 | 0.645478 | 0.636364 |
| 7 | 9 | 0.750645 | 0.666667 |
| 8 | 10 | 0.845504 | 0.8 |
| 9 | 8 | 0.941143 | 1.0 |
EXPLORATORY FACT: 2024 whole_pool paired bootstrap table, 95% percentile intervals:
| Comparator | Mean AUROC difference | 95% interval | Valid resamples |
|---|---:|---|---:|
| M minus B0 | -0.016329 | -0.048764 to 0.014118 | 2000 |
| M minus B1 | 0.004523 | -0.025169 to 0.034079 | 2000 |
| M minus B2 | 0.096418 | 0.061617 to 0.133022 | 2000 |
| M minus P | 0.085272 | 0.047619 to 0.123688 | 2000 |

EXPLORATORY FACT: 2024 pitchers ranking metrics table:
| Ranking | N | Positives | Top 25 hits | Top 25 precision | Top 50 hits | Top 50 precision | Top 100 hits | Top 100 precision | AUROC |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| B0 | 372 | 57 | 19 | 0.76 | 26 | 0.52 | 39 | 0.39 | 0.815483 |
| B1 | 372 | 57 | 13 | 0.52 | 23 | 0.46 | 32 | 0.32 | 0.797271 |
| B2 | 372 | 57 | 10 | 0.4 | 16 | 0.32 | 31 | 0.31 | 0.72988 |
| P | 372 | 57 | 15 | 0.6 | 28 | 0.56 | 33 | 0.33 | 0.711612 |
| M | 372 | 57 | 21 | 0.84 | 28 | 0.56 | 38 | 0.38 | 0.825453 |
EXPLORATORY FACT: 2024 pitchers M calibration table (bin, count, mean probability, outcome rate):
| Bin | Count | Mean probability | Outcome rate |
|---:|---:|---:|---:|
| 0 | 257 | 0.040118 | 0.070039 |
| 1 | 42 | 0.153731 | 0.142857 |
| 2 | 26 | 0.247661 | 0.192308 |
| 3 | 15 | 0.3329 | 0.066667 |
| 4 | 6 | 0.444335 | 0.833333 |
| 5 | 8 | 0.529427 | 0.875 |
| 6 | 8 | 0.645114 | 0.75 |
| 7 | 2 | 0.751426 | 0.5 |
| 8 | 3 | 0.863427 | 1.0 |
| 9 | 5 | 0.942893 | 1.0 |
EXPLORATORY FACT: 2024 pitchers paired bootstrap table, 95% percentile intervals:
| Comparator | Mean AUROC difference | 95% interval | Valid resamples |
|---|---:|---|---:|
| M minus B0 | 0.010257 | -0.030324 to 0.049568 | 2000 |
| M minus B1 | 0.028577 | -0.003008 to 0.060373 | 2000 |
| M minus B2 | 0.095391 | 0.04497 to 0.143987 | 2000 |
| M minus P | 0.114094 | 0.068537 to 0.159736 | 2000 |

EXPLORATORY FACT: 2024 hitters ranking metrics table:
| Ranking | N | Positives | Top 25 hits | Top 25 precision | Top 50 hits | Top 50 precision | Top 100 hits | Top 100 precision | AUROC |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| B0 | 264 | 34 | 17 | 0.68 | 24 | 0.48 | 28 | 0.28 | 0.876598 |
| B1 | 264 | 34 | 20 | 0.8 | 24 | 0.48 | 29 | 0.29 | 0.888747 |
| B2 | 264 | 34 | 8 | 0.32 | 13 | 0.26 | 22 | 0.22 | 0.714962 |
| P | 264 | 34 | 12 | 0.48 | 22 | 0.44 | 24 | 0.24 | 0.780051 |
| M | 264 | 34 | 16 | 0.64 | 25 | 0.5 | 26 | 0.26 | 0.818798 |
EXPLORATORY FACT: 2024 hitters M calibration table (bin, count, mean probability, outcome rate):
| Bin | Count | Mean probability | Outcome rate |
|---:|---:|---:|---:|
| 0 | 198 | 0.041847 | 0.045455 |
| 1 | 27 | 0.133429 | 0.148148 |
| 2 | 6 | 0.244892 | 0.166667 |
| 3 | 4 | 0.344626 | 0.5 |
| 4 | 5 | 0.471572 | 0.4 |
| 5 | 4 | 0.562928 | 0.5 |
| 6 | 3 | 0.646451 | 0.333333 |
| 7 | 7 | 0.750422 | 0.714286 |
| 8 | 7 | 0.837823 | 0.714286 |
| 9 | 3 | 0.938225 | 1.0 |
EXPLORATORY FACT: 2024 hitters paired bootstrap table, 95% percentile intervals:
| Comparator | Mean AUROC difference | 95% interval | Valid resamples |
|---|---:|---|---:|
| M minus B0 | -0.058187 | -0.114416 to -0.014062 | 2000 |
| M minus B1 | -0.070099 | -0.120751 to -0.027494 | 2000 |
| M minus B2 | 0.102789 | 0.046726 to 0.161152 | 2000 |
| M minus P | 0.03885 | -0.019222 to 0.100012 | 2000 |

EXPLORATORY FACT: 2021 whole_pool ranking metrics table:
| Ranking | N | Positives | Top 25 hits | Top 25 precision | Top 50 hits | Top 50 precision | Top 100 hits | Top 100 precision | AUROC |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| B0 | 901 | 174 | 24 | 0.96 | 41 | 0.82 | 73 | 0.73 | 0.898757 |
| B1 | 901 | 174 | 21 | 0.84 | 39 | 0.78 | 56 | 0.56 | 0.876132 |
| B2 | 901 | 174 | 10 | 0.4 | 21 | 0.42 | 45 | 0.45 | 0.836519 |
| P | 901 | 174 | 15 | 0.6 | 28 | 0.56 | 61 | 0.61 | 0.834776 |
| M | 901 | 174 | 22 | 0.88 | 43 | 0.86 | 80 | 0.8 | 0.913516 |
EXPLORATORY FACT: 2021 whole_pool M calibration table (bin, count, mean probability, outcome rate):
| Bin | Count | Mean probability | Outcome rate |
|---:|---:|---:|---:|
| 0 | 614 | 0.042197 | 0.032573 |
| 1 | 94 | 0.144571 | 0.297872 |
| 2 | 77 | 0.244042 | 0.506494 |
| 3 | 33 | 0.337769 | 0.636364 |
| 4 | 23 | 0.446494 | 0.652174 |
| 5 | 21 | 0.550468 | 0.857143 |
| 6 | 15 | 0.642879 | 0.733333 |
| 7 | 19 | 0.746817 | 0.947368 |
| 8 | 5 | 0.844676 | 0.8 |
| 9 | 0 | n/a | n/a |
EXPLORATORY FACT: 2021 whole_pool paired bootstrap table, 95% percentile intervals:
| Comparator | Mean AUROC difference | 95% interval | Valid resamples |
|---|---:|---|---:|
| M minus B0 | 0.014655 | -0.001056 to 0.031501 | 2000 |
| M minus B1 | 0.037162 | 0.017282 to 0.057749 | 2000 |
| M minus B2 | 0.07692 | 0.059154 to 0.096678 | 2000 |
| M minus P | 0.07899 | 0.056478 to 0.102335 | 2000 |

EXPLORATORY FACT: 2021 pitchers ranking metrics table:
| Ranking | N | Positives | Top 25 hits | Top 25 precision | Top 50 hits | Top 50 precision | Top 100 hits | Top 100 precision | AUROC |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| B0 | 520 | 107 | 18 | 0.72 | 34 | 0.68 | 67 | 0.67 | 0.887013 |
| B1 | 520 | 107 | 16 | 0.64 | 35 | 0.7 | 63 | 0.63 | 0.88208 |
| B2 | 520 | 107 | 9 | 0.36 | 22 | 0.44 | 48 | 0.48 | 0.839628 |
| P | 520 | 107 | 12 | 0.48 | 28 | 0.56 | 63 | 0.63 | 0.816252 |
| M | 520 | 107 | 21 | 0.84 | 39 | 0.78 | 67 | 0.67 | 0.904981 |
EXPLORATORY FACT: 2021 pitchers M calibration table (bin, count, mean probability, outcome rate):
| Bin | Count | Mean probability | Outcome rate |
|---:|---:|---:|---:|
| 0 | 329 | 0.041616 | 0.030395 |
| 1 | 62 | 0.146004 | 0.290323 |
| 2 | 65 | 0.246004 | 0.507692 |
| 3 | 25 | 0.333821 | 0.68 |
| 4 | 12 | 0.441653 | 0.583333 |
| 5 | 9 | 0.548748 | 0.888889 |
| 6 | 8 | 0.643142 | 0.625 |
| 7 | 8 | 0.73976 | 0.875 |
| 8 | 2 | 0.867107 | 1.0 |
| 9 | 0 | n/a | n/a |
EXPLORATORY FACT: 2021 pitchers paired bootstrap table, 95% percentile intervals:
| Comparator | Mean AUROC difference | 95% interval | Valid resamples |
|---|---:|---|---:|
| M minus B0 | 0.0179 | 0.000326 to 0.036138 | 2000 |
| M minus B1 | 0.022765 | 0.000756 to 0.045701 | 2000 |
| M minus B2 | 0.064989 | 0.039171 to 0.091485 | 2000 |
| M minus P | 0.088499 | 0.056995 to 0.120442 | 2000 |

EXPLORATORY FACT: 2021 hitters ranking metrics table:
| Ranking | N | Positives | Top 25 hits | Top 25 precision | Top 50 hits | Top 50 precision | Top 100 hits | Top 100 precision | AUROC |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| B0 | 381 | 67 | 23 | 0.92 | 39 | 0.78 | 58 | 0.58 | 0.922759 |
| B1 | 381 | 67 | 21 | 0.84 | 39 | 0.78 | 56 | 0.56 | 0.909259 |
| B2 | 381 | 67 | 8 | 0.32 | 25 | 0.5 | 45 | 0.45 | 0.828358 |
| P | 381 | 67 | 16 | 0.64 | 33 | 0.66 | 56 | 0.56 | 0.861085 |
| M | 381 | 67 | 22 | 0.88 | 41 | 0.82 | 57 | 0.57 | 0.921475 |
EXPLORATORY FACT: 2021 hitters M calibration table (bin, count, mean probability, outcome rate):
| Bin | Count | Mean probability | Outcome rate |
|---:|---:|---:|---:|
| 0 | 285 | 0.042868 | 0.035088 |
| 1 | 32 | 0.141794 | 0.3125 |
| 2 | 12 | 0.233413 | 0.5 |
| 3 | 8 | 0.350107 | 0.5 |
| 4 | 11 | 0.451775 | 0.727273 |
| 5 | 12 | 0.551758 | 0.833333 |
| 6 | 7 | 0.642579 | 0.857143 |
| 7 | 11 | 0.751949 | 1.0 |
| 8 | 3 | 0.829722 | 0.666667 |
| 9 | 0 | n/a | n/a |
EXPLORATORY FACT: 2021 hitters paired bootstrap table, 95% percentile intervals:
| Comparator | Mean AUROC difference | 95% interval | Valid resamples |
|---|---:|---|---:|
| M minus B0 | -0.000781 | -0.031134 to 0.034007 | 2000 |
| M minus B1 | 0.012367 | -0.018698 to 0.048389 | 2000 |
| M minus B2 | 0.092887 | 0.063342 to 0.123078 | 2000 |
| M minus P | 0.060078 | 0.028626 to 0.09327 | 2000 |

EXPLORATORY FACT: 2022 whole_pool ranking metrics table:
| Ranking | N | Positives | Top 25 hits | Top 25 precision | Top 50 hits | Top 50 precision | Top 100 hits | Top 100 precision | AUROC |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| B0 | 852 | 177 | 24 | 0.96 | 44 | 0.88 | 80 | 0.8 | 0.906976 |
| B1 | 852 | 177 | 21 | 0.84 | 42 | 0.84 | 65 | 0.65 | 0.890061 |
| B2 | 852 | 177 | 15 | 0.6 | 32 | 0.64 | 57 | 0.57 | 0.852354 |
| P | 852 | 177 | 19 | 0.76 | 32 | 0.64 | 66 | 0.66 | 0.839975 |
| M | 852 | 177 | 24 | 0.96 | 48 | 0.96 | 90 | 0.9 | 0.935618 |
EXPLORATORY FACT: 2022 whole_pool M calibration table (bin, count, mean probability, outcome rate):
| Bin | Count | Mean probability | Outcome rate |
|---:|---:|---:|---:|
| 0 | 518 | 0.038989 | 0.025097 |
| 1 | 84 | 0.142901 | 0.095238 |
| 2 | 52 | 0.239753 | 0.346154 |
| 3 | 36 | 0.34794 | 0.472222 |
| 4 | 28 | 0.452957 | 0.392857 |
| 5 | 24 | 0.54664 | 0.541667 |
| 6 | 21 | 0.642109 | 0.809524 |
| 7 | 18 | 0.748132 | 0.833333 |
| 8 | 25 | 0.853196 | 0.84 |
| 9 | 46 | 0.951437 | 0.956522 |
EXPLORATORY FACT: 2022 whole_pool paired bootstrap table, 95% percentile intervals:
| Comparator | Mean AUROC difference | 95% interval | Valid resamples |
|---|---:|---|---:|
| M minus B0 | 0.028416 | 0.014744 to 0.04312 | 2000 |
| M minus B1 | 0.045318 | 0.027167 to 0.064311 | 2000 |
| M minus B2 | 0.083082 | 0.059666 to 0.105756 | 2000 |
| M minus P | 0.095377 | 0.074903 to 0.11722 | 2000 |

EXPLORATORY FACT: 2022 pitchers ranking metrics table:
| Ranking | N | Positives | Top 25 hits | Top 25 precision | Top 50 hits | Top 50 precision | Top 100 hits | Top 100 precision | AUROC |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| B0 | 483 | 99 | 20 | 0.8 | 38 | 0.76 | 67 | 0.67 | 0.891546 |
| B1 | 483 | 99 | 16 | 0.64 | 32 | 0.64 | 62 | 0.62 | 0.887284 |
| B2 | 483 | 99 | 14 | 0.56 | 25 | 0.5 | 57 | 0.57 | 0.8493 |
| P | 483 | 99 | 17 | 0.68 | 30 | 0.6 | 62 | 0.62 | 0.819721 |
| M | 483 | 99 | 24 | 0.96 | 43 | 0.86 | 69 | 0.69 | 0.925032 |
EXPLORATORY FACT: 2022 pitchers M calibration table (bin, count, mean probability, outcome rate):
| Bin | Count | Mean probability | Outcome rate |
|---:|---:|---:|---:|
| 0 | 285 | 0.036434 | 0.031579 |
| 1 | 50 | 0.1507 | 0.08 |
| 2 | 36 | 0.240637 | 0.305556 |
| 3 | 25 | 0.354669 | 0.52 |
| 4 | 18 | 0.445813 | 0.388889 |
| 5 | 19 | 0.547153 | 0.631579 |
| 6 | 15 | 0.643511 | 0.8 |
| 7 | 7 | 0.75026 | 0.714286 |
| 8 | 12 | 0.84119 | 0.833333 |
| 9 | 16 | 0.941854 | 1.0 |
EXPLORATORY FACT: 2022 pitchers paired bootstrap table, 95% percentile intervals:
| Comparator | Mean AUROC difference | 95% interval | Valid resamples |
|---|---:|---|---:|
| M minus B0 | 0.033372 | 0.014987 to 0.052826 | 2000 |
| M minus B1 | 0.037367 | 0.015184 to 0.06028 | 2000 |
| M minus B2 | 0.07584 | 0.04563 to 0.106583 | 2000 |
| M minus P | 0.105302 | 0.076978 to 0.136087 | 2000 |

EXPLORATORY FACT: 2022 hitters ranking metrics table:
| Ranking | N | Positives | Top 25 hits | Top 25 precision | Top 50 hits | Top 50 precision | Top 100 hits | Top 100 precision | AUROC |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| B0 | 369 | 78 | 24 | 0.96 | 45 | 0.9 | 66 | 0.66 | 0.934488 |
| B1 | 369 | 78 | 21 | 0.84 | 42 | 0.84 | 65 | 0.65 | 0.933606 |
| B2 | 369 | 78 | 18 | 0.72 | 29 | 0.58 | 52 | 0.52 | 0.859503 |
| P | 369 | 78 | 18 | 0.72 | 37 | 0.74 | 66 | 0.66 | 0.865913 |
| M | 369 | 78 | 24 | 0.96 | 46 | 0.92 | 69 | 0.69 | 0.949775 |
EXPLORATORY FACT: 2022 hitters M calibration table (bin, count, mean probability, outcome rate):
| Bin | Count | Mean probability | Outcome rate |
|---:|---:|---:|---:|
| 0 | 233 | 0.042115 | 0.017167 |
| 1 | 34 | 0.131433 | 0.117647 |
| 2 | 16 | 0.237764 | 0.4375 |
| 3 | 11 | 0.332647 | 0.363636 |
| 4 | 10 | 0.465816 | 0.4 |
| 5 | 5 | 0.544689 | 0.2 |
| 6 | 6 | 0.638604 | 0.833333 |
| 7 | 11 | 0.746778 | 0.909091 |
| 8 | 13 | 0.864279 | 0.846154 |
| 9 | 30 | 0.956549 | 0.933333 |
EXPLORATORY FACT: 2022 hitters paired bootstrap table, 95% percentile intervals:
| Comparator | Mean AUROC difference | 95% interval | Valid resamples |
|---|---:|---|---:|
| M minus B0 | 0.015082 | -0.003928 to 0.041501 | 2000 |
| M minus B1 | 0.016532 | -0.009323 to 0.0471 | 2000 |
| M minus B2 | 0.090728 | 0.059006 to 0.125326 | 2000 |
| M minus P | 0.083151 | 0.053283 to 0.114141 | 2000 |

EXPLORATORY FACT: 2023 whole_pool ranking metrics table:
| Ranking | N | Positives | Top 25 hits | Top 25 precision | Top 50 hits | Top 50 precision | Top 100 hits | Top 100 precision | AUROC |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| B0 | 825 | 171 | 25 | 1.0 | 43 | 0.86 | 72 | 0.72 | 0.882415 |
| B1 | 825 | 171 | 21 | 0.84 | 36 | 0.72 | 53 | 0.53 | 0.857682 |
| B2 | 825 | 171 | 12 | 0.48 | 25 | 0.5 | 46 | 0.46 | 0.80201 |
| P | 825 | 171 | 14 | 0.56 | 31 | 0.62 | 63 | 0.63 | 0.817426 |
| M | 825 | 171 | 22 | 0.88 | 41 | 0.82 | 76 | 0.76 | 0.887896 |
EXPLORATORY FACT: 2023 whole_pool M calibration table (bin, count, mean probability, outcome rate):
| Bin | Count | Mean probability | Outcome rate |
|---:|---:|---:|---:|
| 0 | 533 | 0.036739 | 0.046904 |
| 1 | 61 | 0.145631 | 0.163934 |
| 2 | 47 | 0.246872 | 0.319149 |
| 3 | 21 | 0.348158 | 0.428571 |
| 4 | 20 | 0.449462 | 0.35 |
| 5 | 36 | 0.552576 | 0.666667 |
| 6 | 18 | 0.662061 | 0.722222 |
| 7 | 26 | 0.764165 | 0.653846 |
| 8 | 26 | 0.859173 | 0.730769 |
| 9 | 37 | 0.947607 | 0.864865 |
EXPLORATORY FACT: 2023 whole_pool paired bootstrap table, 95% percentile intervals:
| Comparator | Mean AUROC difference | 95% interval | Valid resamples |
|---|---:|---|---:|
| M minus B0 | 0.005719 | -0.01556 to 0.027606 | 2000 |
| M minus B1 | 0.03063 | 0.008709 to 0.054806 | 2000 |
| M minus B2 | 0.085828 | 0.059602 to 0.112266 | 2000 |
| M minus P | 0.070411 | 0.047449 to 0.092627 | 2000 |

EXPLORATORY FACT: 2023 pitchers ranking metrics table:
| Ranking | N | Positives | Top 25 hits | Top 25 precision | Top 50 hits | Top 50 precision | Top 100 hits | Top 100 precision | AUROC |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| B0 | 509 | 113 | 19 | 0.76 | 41 | 0.82 | 68 | 0.68 | 0.871659 |
| B1 | 509 | 113 | 13 | 0.52 | 32 | 0.64 | 61 | 0.61 | 0.853312 |
| B2 | 509 | 113 | 14 | 0.56 | 25 | 0.5 | 52 | 0.52 | 0.802539 |
| P | 509 | 113 | 17 | 0.68 | 31 | 0.62 | 64 | 0.64 | 0.805388 |
| M | 509 | 113 | 19 | 0.76 | 37 | 0.74 | 68 | 0.68 | 0.878341 |
EXPLORATORY FACT: 2023 pitchers M calibration table (bin, count, mean probability, outcome rate):
| Bin | Count | Mean probability | Outcome rate |
|---:|---:|---:|---:|
| 0 | 323 | 0.03282 | 0.052632 |
| 1 | 35 | 0.15351 | 0.257143 |
| 2 | 37 | 0.24995 | 0.351351 |
| 3 | 16 | 0.35347 | 0.4375 |
| 4 | 15 | 0.44474 | 0.4 |
| 5 | 29 | 0.546807 | 0.689655 |
| 6 | 13 | 0.656483 | 0.769231 |
| 7 | 14 | 0.763608 | 0.785714 |
| 8 | 12 | 0.86538 | 0.666667 |
| 9 | 15 | 0.953932 | 0.8 |
EXPLORATORY FACT: 2023 pitchers paired bootstrap table, 95% percentile intervals:
| Comparator | Mean AUROC difference | 95% interval | Valid resamples |
|---|---:|---|---:|
| M minus B0 | 0.006498 | -0.016246 to 0.029648 | 2000 |
| M minus B1 | 0.025225 | 0.003637 to 0.047946 | 2000 |
| M minus B2 | 0.075891 | 0.042356 to 0.107261 | 2000 |
| M minus P | 0.072626 | 0.043449 to 0.104231 | 2000 |

EXPLORATORY FACT: 2023 hitters ranking metrics table:
| Ranking | N | Positives | Top 25 hits | Top 25 precision | Top 50 hits | Top 50 precision | Top 100 hits | Top 100 precision | AUROC |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| B0 | 316 | 58 | 25 | 1.0 | 41 | 0.82 | 51 | 0.51 | 0.920476 |
| B1 | 316 | 58 | 21 | 0.84 | 36 | 0.72 | 51 | 0.51 | 0.90417 |
| B2 | 316 | 58 | 14 | 0.56 | 22 | 0.44 | 41 | 0.41 | 0.799051 |
| P | 316 | 58 | 13 | 0.52 | 30 | 0.6 | 47 | 0.47 | 0.841219 |
| M | 316 | 58 | 21 | 0.84 | 39 | 0.78 | 50 | 0.5 | 0.909316 |
EXPLORATORY FACT: 2023 hitters M calibration table (bin, count, mean probability, outcome rate):
| Bin | Count | Mean probability | Outcome rate |
|---:|---:|---:|---:|
| 0 | 210 | 0.042768 | 0.038095 |
| 1 | 26 | 0.135025 | 0.038462 |
| 2 | 10 | 0.235481 | 0.2 |
| 3 | 5 | 0.331159 | 0.4 |
| 4 | 5 | 0.463628 | 0.2 |
| 5 | 7 | 0.576476 | 0.571429 |
| 6 | 5 | 0.676563 | 0.6 |
| 7 | 12 | 0.764815 | 0.5 |
| 8 | 14 | 0.853852 | 0.785714 |
| 9 | 22 | 0.943294 | 0.909091 |
EXPLORATORY FACT: 2023 hitters paired bootstrap table, 95% percentile intervals:
| Comparator | Mean AUROC difference | 95% interval | Valid resamples |
|---|---:|---|---:|
| M minus B0 | -0.012756 | -0.056 to 0.037359 | 2000 |
| M minus B1 | 0.003718 | -0.042905 to 0.055556 | 2000 |
| M minus B2 | 0.110258 | 0.075117 to 0.150679 | 2000 |
| M minus P | 0.067583 | 0.036995 to 0.101099 | 2000 |

EXPLORATORY INFERENCE: On the 2024 whole pool, M had 38 top-50 hits and B0 had 32.
EXPLORATORY UNKNOWN: The 2025 cohort was not evaluated.
EXPLORATORY UNKNOWN: Whether differences exceed sampling noise beyond these bootstrap intervals is unknown.
EXPLORATORY UNKNOWN: Stability of the single L2 choice is unknown.
<!-- EXPLORATORY WHOLE POOL END -->

## Cubs case (descriptive)

FACT: Dated 2026-10-09; source: MLBAM, MLB Stats API; cached local responses; Cubs team ID 112.
FACT: Cohorts: 2021, 2022, 2023, 2024; outcome thresholds: at least 50 MLB PA or 20 MLB IP in the following season, any club.
FACT: A qualifying Cubs transaction matches the recorded minor-contract or spring-invitation rules and falls within the player's election-date-through-March-31 window, inclusive; joins use person_id only.

FACT: Counts and shares by cohort are:
| Evidence | Cohort | Outcome season | Cubs signed | Signed, positive | No MLB in Y signed | No MLB in Y signed, positive | League no-MLB-in-Y positives | Cubs share of those positives |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| FACT | 2021 | 2022 | 14 | 3 | 6 | 1 | 14 | 0.071429 |
| FACT | 2022 | 2023 | 12 | 1 | 3 | 0 | 12 | 0.000000 |
| FACT | 2023 | 2024 | 10 | 6 | 3 | 1 | 22 | 0.045455 |
| FACT | 2024 | 2025 | 8 | 0 | 4 | 0 | 23 | 0.000000 |

FACT: The method was not tested (pre-registered early stop).
INFERENCE: This case illustrates the size of the opportunity only; not a recommendation.
UNKNOWN: Availability, contract terms, and competing offers are unknown.
FACT: Examples below are limited to five and identify people by person ID with source dates.
FACT: Cohort 2021, person ID 643410: election 2021-11-07, Cubs transaction 2021-12-15, outcome season 2022.
FACT: Cohort 2023, person ID 681799: election 2023-11-17, Cubs transaction 2023-12-02, outcome season 2024.
