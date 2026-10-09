# Feasibility measurements

FACT: Query references are SHA-256 hashes of the query object (endpoint and params), serialized with Python json.dumps and sort_keys=True. Match them to raw_manifest.json metadata.

UNKNOWN: Failed requests: 0.

## MILBFA

FACT: Measured counts by season.

| season | matched_events |
| --- | --- |
| 2018 | 585 |
| 2019 | 631 |
| 2021 | 908 |
| 2022 | 854 |
| 2023 | 833 |
| 2024 | 638 |
| 2025 | 839 |

| season | A | B |
| --- | --- | --- |
| 2018 | mlb: 52; minor: 530; unresolved: 3 | minor: 417; mlb: 133; unresolved: 35 |
| 2019 | minor: 507; mlb: 84; unresolved: 40 | mlb: 164; minor: 415; unresolved: 52 |
| 2021 | mlb: 232; minor: 673; unresolved: 3 | mlb: 348; unresolved: 39; minor: 521 |
| 2022 | minor: 596; mlb: 252; unresolved: 6 | mlb: 344; minor: 467; unresolved: 43 |
| 2023 | mlb: 249; minor: 583; unresolved: 1 | mlb: 308; unresolved: 46; minor: 479 |
| 2024 | mlb: 101; minor: 537 | mlb: 187; minor: 426; unresolved: 25 |
| 2025 | minor: 587; mlb: 251; unresolved: 1 | mlb: 346; unresolved: 30; minor: 463 |

| season | agreement | disagreement | unresolved | minor_only_proxy | confirmed_minor_contract_elections |
| --- | --- | --- | --- | --- | --- |
| 2018 | 458 | 92 | 35 | 412 | UNKNOWN |
| 2019 | 481 | 84 | 66 | 400 | UNKNOWN |
| 2021 | 737 | 131 | 40 | 516 | UNKNOWN |
| 2022 | 683 | 125 | 46 | 453 | UNKNOWN |
| 2023 | 696 | 91 | 46 | 469 | UNKNOWN |
| 2024 | 500 | 113 | 25 | 413 | UNKNOWN |
| 2025 | 685 | 124 | 30 | 451 | UNKNOWN |

INFERENCE: Verdict **PARTIAL**. Proxy counts measure team level and season play, not minor-league contract status. Confirmed minor-league-only election counts remain unknown.

INFERENCE: Method and limitations: Election descriptions contain elected free agency in November and December. A classifies fromTeam/toTeam against season team lists: MLB takes precedence, then minor, else unresolved. B uses hitting/pitching season splits for each queried sport: MLB appearance takes precedence; otherwise minor appearance with all sport queries returned is a minor proxy. Agreement and disagreement exclude unresolved rows. minor_only_proxy counts elections where both methods say minor, not unique players and not confirmed contracts. Missing MLB stats can create false minor proxies; rehab, injured players, team attribution, prior MLB veterans, omitted leagues and incomplete histories prevent reliable contract separation.

FACT: Query references for each season/level are in this candidate’s rows in summary.json (query_refs).

FACT: Short examples (at most five per candidate).

| record | query |
| --- | --- |
| id: 381870; date: 2018\-11\-01; player\_id: 519390; code: DFA; type\_desc: Declared Free Agency; description: C Stephen Vogt elected free agency\.; from\_team: UNKNOWN; to\_team: 158 | endpoint: https://statsapi\.mlb\.com/api/v1/transactions; params: startDate: 2018\-11\-01; endDate: 2018\-12\-31 |
| id: 382446; date: 2018\-11\-01; player\_id: 475857; code: DFA; type\_desc: Declared Free Agency; description: RHP Ryan Cook elected free agency\.; from\_team: UNKNOWN; to\_team: 529 | endpoint: https://statsapi\.mlb\.com/api/v1/transactions; params: startDate: 2018\-11\-01; endDate: 2018\-12\-31 |
| id: 381842; date: 2018\-11\-01; player\_id: 543219; code: DFA; type\_desc: Declared Free Agency; description: LHP Sean Gilmartin elected free agency\.; from\_team: UNKNOWN; to\_team: 568 | endpoint: https://statsapi\.mlb\.com/api/v1/transactions; params: startDate: 2018\-11\-01; endDate: 2018\-12\-31 |
| id: 381879; date: 2018\-11\-01; player\_id: 500207; code: DFA; type\_desc: Declared Free Agency; description: C Jhonatan Solano elected free agency\.; from\_team: UNKNOWN; to\_team: 120 | endpoint: https://statsapi\.mlb\.com/api/v1/transactions; params: startDate: 2018\-11\-01; endDate: 2018\-12\-31 |
| id: 381843; date: 2018\-11\-01; player\_id: 607054; code: DFA; type\_desc: Declared Free Agency; description: 3B Jace Peterson elected free agency\.; from\_team: UNKNOWN; to\_team: 568 | endpoint: https://statsapi\.mlb\.com/api/v1/transactions; params: startDate: 2018\-11\-01; endDate: 2018\-12\-31 |

UNKNOWN: Unmeasured seasons or levels are not zero counts. Missing values are shown as UNKNOWN.

## RULE5

FACT: Measured counts by season.

| season | rows | matched_events | text_matched_events | window_union_matches | identifiers | r5_without_text | dr_with_text | dr_without_text |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2015 | 3852 | 0 | 0 | True | none | 0 | 0 | 0 |
| 2016 | 3708 | 0 | 0 | True | none | 0 | 0 | 0 |
| 2017 | 3351 | 0 | 0 | True | none | 0 | 0 | 0 |
| 2018 | 3619 | 0 | 0 | True | none | 0 | 0 | 0 |
| 2019 | 5015 | 0 | 0 | True | none | 0 | 0 | 0 |
| 2020 | 6269 | 0 | 0 | True | none | 0 | 0 | 0 |
| 2021 | 6097 | 0 | 0 | True | none | 0 | 0 | 0 |
| 2022 | 7365 | 0 | 0 | True | none | 0 | 0 | 10 |
| 2023 | 6125 | 0 | 0 | True | none | 0 | 0 | 92 |
| 2024 | 5895 | 82 | 82 | True | R5; Rule 5 Selection; R5M; Rule 5 Draft Minors | 0 | 0 | 0 |
| 2025 | 6167 | 68 | 68 | True | R5; Rule 5 Selection; R5M; Rule 5 Draft Minors | 0 | 0 | 0 |

INFERENCE: Verdict **PARTIAL**. Description-derived identifiers recover candidates; coverage and draft phase require reconciliation to an independent official selection list.

INFERENCE: Method and limitations: Within each year, identifiers are code/description groups having at least one description containing Rule 5 or Rule V. All rows in those groups are candidates; text_matched_events is the narrower count. Group examples include transaction id, date and real description. Code reuse may create false positives; missing text creates false negatives. The same derivation applies across years, including DR. Monthly ID union equality tests one truncation risk; shared omissions remain possible.

FACT: Query references for each season/level are in this candidate’s rows in summary.json (query_refs).

UNKNOWN: DR rows without Rule 5 text cannot be assigned to Rule 5 on code alone. Seasons with no derived identifier have unknown Rule 5 coverage.

FACT: Short examples (at most five per candidate).

| record | query |
| --- | --- |
| id: 808064; date: 2024\-12\-11; player\_id: 691634; code: R5M; type\_desc: Rule 5 Draft Minors; description: Chicago White Sox purchased contract of RHP Joseph Yabbour from New York Mets in the Rule 5 Draft, AAA Phase\.; from\_team: 507; to\_team: 494 | endpoint: https://statsapi\.mlb\.com/api/v1/transactions; params: startDate: 2024\-11\-01; endDate: 2024\-12\-31 |
| id: 808049; date: 2024\-12\-11; player\_id: 666768; code: R5; type\_desc: Rule 5 Selection; description: Atlanta Braves purchased contract of RHP Anderson Pilar from Miami Marlins in the Rule 5 Draft\.; from\_team: 146; to\_team: 144 | endpoint: https://statsapi\.mlb\.com/api/v1/transactions; params: startDate: 2024\-11\-01; endDate: 2024\-12\-31 |
| id: 808116; date: 2024\-12\-11; player\_id: 691711; code: R5M; type\_desc: Rule 5 Draft Minors; description: St\. Louis Cardinals purchased contract of RHP Jawilme Ramirez from New York Mets in the Rule 5 Draft, AAA Phase\.; from\_team: 453; to\_team: 235 | endpoint: https://statsapi\.mlb\.com/api/v1/transactions; params: startDate: 2024\-11\-01; endDate: 2024\-12\-31 |
| id: 808089; date: 2024\-12\-11; player\_id: 696521; code: R5M; type\_desc: Rule 5 Draft Minors; description: Milwaukee Brewers purchased contract of OF Garrett Spain from Toronto Blue Jays in the Rule 5 Draft, AAA Phase\.; from\_team: 463; to\_team: 556 | endpoint: https://statsapi\.mlb\.com/api/v1/transactions; params: startDate: 2024\-11\-01; endDate: 2024\-12\-31 |
| id: 808070; date: 2024\-12\-11; player\_id: 682620; code: R5M; type\_desc: Rule 5 Draft Minors; description: Toronto Blue Jays purchased contract of RHP Richard Gallardo from Chicago Cubs in the Rule 5 Draft, AAA Phase\.; from\_team: 553; to\_team: 422 | endpoint: https://statsapi\.mlb\.com/api/v1/transactions; params: startDate: 2024\-11\-01; endDate: 2024\-12\-31 |

UNKNOWN: Unmeasured seasons or levels are not zero counts. Missing values are shown as UNKNOWN.

## CALLUP

FACT: Measured counts by season.

| season | sport_id | dated_splits | through_june | first_date | last_date | sample_size | measured |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2018 | 11 | 135 | 80 | 2018\-04\-05 | 2018\-09\-03 | 1 | 1 |
| 2018 | 12 | 136 | 75 | 2018\-04\-05 | 2018\-09\-03 | 1 | 1 |
| 2018 | 13 | 129 | 74 | 2018\-04\-05 | 2018\-09\-03 | 1 | 1 |
| 2018 | 14 | 129 | 74 | 2018\-04\-06 | 2018\-09\-03 | 1 | 1 |
| 2019 | 11 | 130 | 76 | 2019\-04\-04 | 2019\-09\-01 | 1 | 1 |
| 2019 | 12 | 135 | 77 | 2019\-04\-04 | 2019\-09\-02 | 1 | 1 |
| 2019 | 13 | 130 | 75 | 2019\-04\-04 | 2019\-09\-01 | 1 | 1 |
| 2019 | 14 | 131 | 76 | 2019\-04\-04 | 2019\-09\-02 | 1 | 1 |
| 2021 | 11 | 117 | 44 | 2021\-05\-06 | 2021\-10\-03 | 1 | 1 |
| 2021 | 12 | 119 | 50 | 2021\-05\-04 | 2021\-09\-19 | 1 | 1 |
| 2021 | 13 | 120 | 50 | 2021\-05\-04 | 2021\-09\-19 | 1 | 1 |
| 2021 | 14 | 115 | 48 | 2021\-05\-04 | 2021\-09\-19 | 1 | 1 |
| 2022 | 11 | 145 | 72 | 2022\-04\-05 | 2022\-09\-28 | 1 | 1 |
| 2022 | 12 | 123 | 64 | 2022\-04\-08 | 2022\-09\-18 | 1 | 1 |
| 2022 | 13 | 128 | 70 | 2022\-04\-08 | 2022\-09\-10 | 1 | 1 |
| 2022 | 14 | 122 | 66 | 2022\-04\-08 | 2022\-09\-11 | 1 | 1 |
| 2023 | 11 | 138 | 73 | 2023\-03\-31 | 2023\-09\-24 | 1 | 1 |
| 2023 | 12 | 135 | 70 | 2023\-04\-07 | 2023\-09\-17 | 1 | 1 |
| 2023 | 13 | 127 | 70 | 2023\-04\-07 | 2023\-09\-10 | 1 | 1 |
| 2023 | 14 | 115 | 64 | 2023\-04\-06 | 2023\-09\-10 | 1 | 1 |
| 2024 | 11 | 144 | 78 | 2024\-03\-30 | 2024\-09\-22 | 1 | 1 |
| 2024 | 12 | 126 | 67 | 2024\-04\-05 | 2024\-09\-14 | 1 | 1 |
| 2024 | 13 | 126 | 71 | 2024\-04\-05 | 2024\-09\-08 | 1 | 1 |
| 2024 | 14 | 124 | 70 | 2024\-04\-05 | 2024\-09\-08 | 1 | 1 |
| 2025 | 11 | 137 | 71 | 2025\-03\-28 | 2025\-09\-21 | 1 | 1 |
| 2025 | 12 | 136 | 74 | 2025\-04\-04 | 2025\-09\-13 | 1 | 1 |
| 2025 | 13 | 126 | 70 | 2025\-04\-04 | 2025\-09\-07 | 1 | 1 |
| 2025 | 14 | 122 | 69 | 2025\-04\-04 | 2025\-09\-07 | 1 | 1 |

INFERENCE: Verdict **PARTIAL**. The non-random sample is limited to one hitting leader per season and level; population and point-in-time availability remain unverified.

INFERENCE: Method and limitations: Selection takes the first hitting season leaderboard row ordered by plateAppearances descending with limit=1 for each queried season and sport. Ties follow API ordering. This is non-random. Dated splits are filtered to returned season and sport; through_june counts dates on or before June 30 locally. These are split counts, not guaranteed unique games. The small-sample design cannot receive FEASIBLE regardless of observed success.

FACT: Query references for each season/level are in this candidate’s rows in summary.json (query_refs).

FACT: Short examples (at most five per candidate).

| record | query |
| --- | --- |
| player\_id: 658069 | endpoint: https://statsapi\.mlb\.com/api/v1/people/658069/stats; params: stats: gameLog; group: hitting; season: 2018; sportId: 11 |
| player\_id: 625510 | endpoint: https://statsapi\.mlb\.com/api/v1/people/625510/stats; params: stats: gameLog; group: hitting; season: 2018; sportId: 12 |
| player\_id: 663368 | endpoint: https://statsapi\.mlb\.com/api/v1/people/663368/stats; params: stats: gameLog; group: hitting; season: 2018; sportId: 13 |
| player\_id: 676913 | endpoint: https://statsapi\.mlb\.com/api/v1/people/676913/stats; params: stats: gameLog; group: hitting; season: 2018; sportId: 14 |
| player\_id: 641583 | endpoint: https://statsapi\.mlb\.com/api/v1/people/641583/stats; params: stats: gameLog; group: hitting; season: 2019; sportId: 11 |

UNKNOWN: Unmeasured seasons or levels are not zero counts. Missing values are shown as UNKNOWN.

UNKNOWN: Historical publication times and retroactive corrections are not measured. Current API responses do not establish what was available at a past decision date. No population completeness or contract-status guarantee is made. Retrieval UTC and response hashes are in raw_manifest.json; bulk inputs remain in ignored local data/.
