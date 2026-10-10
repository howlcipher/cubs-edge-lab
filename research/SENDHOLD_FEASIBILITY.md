# Third-base send/hold feasibility

INFERENCE: Study verdict: **PARTIAL**

FACT: Measurements use cached game feeds and public leaderboards.
FACT: Source: [MLB Stats API](https://statsapi.mlb.com/api/v1/) and [Baseball Savant sprint speed](https://baseballsavant.mlb.com/leaderboard/sprint_speed) and [arm strength](https://baseballsavant.mlb.com/leaderboard/arm-strength) CSV leaderboards; retrieved 2026-10-09.

FACT: Per-season counts from the deduplicated cached sample.

| season | sample games | opportunities | scored (any) | advanced later | sent safe | sent out | ended at 3B, no score | out elsewhere | other |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2025 | 50 | 85 | 40 | 26 | 14 | 0 | 44 | 1 | 0 |
| 2026 | 50 | 90 | 33 | 21 | 12 | 0 | 56 | 1 | 0 |

FACT: 'Scored (any)' and 'ended at 3B, no score' are movement views; they are not partitions. A runner who reached third before a later scoring event appears in both views. 'Advanced on a later event' means the send decision is ambiguous. Held means the feed records the runner ending at third. The play-by-play does not establish the coach's sign or the runner's base at the exact batted-ball moment; treat these as candidate opportunities.

## Reconciliation with the controller's recount

FACT: Season 2025: this report (first segment sets the base at contact) 85 opportunities, 40 scored (any), 44 ended at 3B without scoring; diagnostic any-segment rule 88 opportunities, 41 scored (any), 46 ended at 3B without scoring; controller recount target 88 opportunities, 35 scored (any), 47 ended at 3B without scoring.
FACT: Season 2025 segment end sequences, this report: {'2B>3B>score': 6, '3B': 44, '3B>score': 20, 'none': 1, 'score': 14}; any-segment rule: {'2B>3B': 2, '2B>3B>score': 6, '2B>score': 1, '3B': 44, '3B>score': 20, 'none': 1, 'score': 14}.
FACT: Season 2026: this report (first segment sets the base at contact) 90 opportunities, 33 scored (any), 56 ended at 3B without scoring; diagnostic any-segment rule 95 opportunities, 38 scored (any), 56 ended at 3B without scoring; controller recount target 95 opportunities, 35 scored (any), 58 ended at 3B without scoring.
FACT: Season 2026 segment end sequences, this report: {'2B>3B>score': 1, '3B': 56, '3B>score': 20, 'none': 1, 'score': 12}; any-segment rule: {'2B>3B>score': 2, '2B>score': 4, '3B': 56, '3B>score': 20, 'none': 1, 'score': 12}.
INFERENCE: The controller's qualifying totals equal the diagnostic any-segment rule totals, which admit runners whose later segment started on the threshold base. This report identifies 85 (2025) and 90 (2026) qualifying opportunities (175 total) because the spec takes the base from the runner's first segment. Examples of runners excluded under the first-segment rule (at most 5): season 2025 game 778182 runner 691718 single contact bases 1B>2B; season 2025 game 778553 runner 596115 single contact bases 1B>2B; season 2025 game 776474 runner 608070 single contact bases 1B>2B; season 2026 game 824168 runner 702616 single contact bases 1B>2B; season 2026 game 823894 runner 669392 single contact bases 1B>2B>3B.
UNKNOWN: Scored (any) and ended-at-3B counts differ from the controller's recount targets (this report: 2025 40 scored, 44 ended at 3B, 2026 33 scored, 56 ended at 3B; controller targets: 2025 35 scored, 47 ended at 3B, 2026 35 scored, 58 ended at 3B). Whole-movement evaluation classifies each runner across all segments on the play, whereas the controller's recount method for movement views is unverified from the cache; out at home is 0 in all counts.
UNKNOWN: Cases outside the spec: 0 runner segments without a person ID (not counted), and 0 runners who both scored and were out on the same play.

## 2025

FACT: Identification rates: runner ID 100.0%; fielder ID 91.8%; hit type 100.0%; location 100.0%; outs 100.0%; score 100.0%
FACT: Leaderboard ID matches: sprint speed 73/73 (100.0%); arm strength 50/54 (92.6%)
FACT: Outcome rates (safe, advanced later, out at home, held, out elsewhere, other): 16.5%, 30.6%, 0.0%, 51.8%, 1.2%, 0.0%
INFERENCE: League-wide opportunities 4131 (95% interval [3257, 5005]); estimated full-season requests 2433.

## 2026

FACT: Identification rates: runner ID 100.0%; fielder ID 86.7%; hit type 100.0%; location 100.0%; outs 100.0%; score 100.0%
FACT: Leaderboard ID matches: sprint speed 71/72 (98.6%); arm strength 47/52 (90.4%)
FACT: Outcome rates (safe, advanced later, out at home, held, out elsewhere, other): 13.3%, 23.3%, 0.0%, 62.2%, 1.1%, 0.0%
INFERENCE: League-wide opportunities 4374 (95% interval [3157, 5591]); estimated full-season requests 2433.

INFERENCE: Per-game sample mean scaled by the full schedule; the interval uses a normal 95% interval from across-game sample standard error. It does not adjust for schedule-date effects.
INFERENCE: Sample selection uses fixed seed 20261009; schedule SHA-256 0679a9296b7c4773b471a7c5c497173e8ca7191d604f0a1700bd43ae6b85a4c4.
INFERENCE: Estimated requests to retrieve the full two-season schedule and feeds plus four leaderboard CSVs: 4866.
FACT: New network requests used for this sample: 107 of 150; cache hits are free.

UNKNOWN: The feed does not establish coach sign, runner jump, or the counterfactual outcome for held runners.
FACT: Hit location was present on 100.0%, 100.0% of 2025 and 2026 opportunities.
INFERENCE: Verdict reason: The feed supports counts of candidate situations, recorded safe, out, and held outcomes, and person-ID joins to public sprint-speed and arm-strength leaderboards. It does not record the coach's sign, the runner's jump, or what a held runner would have done if sent. Base at contact is inferred from originBase.
