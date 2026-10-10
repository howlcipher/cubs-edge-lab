# cubs-edge-lab

Public-data baseball decision-support experiments for the Chicago Cubs, built and reviewed through the Howl ecosystem (HowlPlane).

Status: research phase. No product claims yet. Every result in this repository must state its data source, retrieval time, and the information available at decision time.

Data policy: only lawfully accessible public data (for example the public MLB Stats API) or clearly labeled synthetic fixtures. No private club, medical, contract, or proprietary tracking data. Raw downloads are cached locally under `data/raw/` and are not committed; their checksums are.

## Feasibility probe

Use Python 3.12 or newer. Install the runtime dependency, then run:

```bash
python3 -m pip install -r requirements.txt
python3 -m cubs_edge_lab.probe
```

Data attribution: MLB Advanced Media, L.P. (MLBAM), via the public MLB Stats
API. Its [usage terms](https://gdx.mlb.com/components/copyright.txt) state:
"Only individual, non-commercial, non-bulk use of the Materials is permitted."
The cached responses' copyright fields link to these terms. The repository's
code license does not cover MLBAM data. Public accessibility does not grant
permission to redistribute bulk responses; they must not be committed.

Run the probe above only for individual use consistent with those terms.
It re-creates `data/raw/` (raw responses), `data/evidence.json` (normalized
parser inputs), and `data/observations.json` (per-record measurements).
All of `data/` is ignored because those files contain bulk response content or
per-record data. Rate limiting is an operational precaution, not permission
for bulk use or redistribution.

The committed research files are exactly:

* `research/raw_manifest.json`: endpoint, parameters, retrieval time, SHA-256,
  byte size, cache filename, and HTTP status metadata, with no response bodies.
* `research/summary.json`: aggregate measured counts, unchanged verdicts and
  reasons, query references, and at most five short examples per candidate.
* `research/FEASIBILITY.md`: readable Markdown generated from that summary.

Requests are sequential, spaced at least half a second apart, with an
identifying User Agent. Existing checksum-verified cache entries are reused.
For a fresh measurement without overwriting the accepted study, use a new root:

```bash
python3 -m cubs_edge_lab.probe --root /tmp/cubs-probe-fresh
```

An empty transaction list is a measured zero. Failed requests and malformed
responses produce recorded failures and a nonzero exit status. Missing stats
are not proof of no play. Failed HTTP responses are cached too; preserve and
remove the affected cache file before retrying that query. The manifest retains
previous attempts, so a retry may add another entry for a query. The accepted
study's provenance test requires exactly one successful entry per query.

After the live run, regenerate from checksum-verified local cache without any
network access (use the same `--root` if the live run used a separate root):

```bash
python3 -m cubs_edge_lab.probe --replay
```

Replay writes local evidence and observations, the summary, and the report
deterministically. It leaves the raw manifest unchanged. Missing, altered, or
failed cached responses produce a nonzero exit and an UNKNOWN failure count in
the report. Failure details stay local. Replay requires `data/raw/`; the cache
is not distributed with this repository.

For an explicitly unassessed report in a separate output directory:

```bash
python3 -m cubs_edge_lab.probe --offline --root /tmp/cubs-probe-offline
```

`--offline` writes null observations and summary and an unassessed report,
without fetching data. It is distinct from `--replay`; the modes are mutually
exclusive. Fetched content is untrusted data and is never executed. API text is
escaped in Markdown cells, while the report's headings and tables remain native
Markdown.

### Study definitions and limits

* MILBFA examines November–December election descriptions in 2018, 2019, and
  2021–2025. Method A uses season team levels. Method B queries each player's
  election-season hitting/pitching splits separately for sports 1, 11, 12, 13,
  14, and 16, in batches of at most 100 players. The report gives each method's
  categories, agreement, disagreement, unresolved events, and the intersection
  of minor-only proxies. These proxies cannot confirm minor-league contracts;
  prior MLB experience, rehab, missing stats, omitted leagues, and team
  attribution can misclassify players. The verdict is capped at PARTIAL.
* RULE5 examines November–December 2015–2025. It derives identifiers separately
  each year from code/description groups containing Rule 5 or Rule V text,
  reports both candidate-group and text-match counts, and records real examples.
  DR rows without Rule 5 text remain unclassified. A monthly transaction-ID union
  comparison checks one truncation risk, but cannot establish complete coverage.
* CALLUP retains one non-random hitting leader per season and level for the seven
  MILBFA years and sports 11–14. The leaderboard requests plate appearances in
  descending order; ties follow API ordering. The report states every measured
  cell's sample size, dated split count, June 30 cutoff count, and date range.
  Any dated-log success yields at most PARTIAL; all measured zeros yield NOT
  FEASIBLE, and no measured log counts yield NOT ASSESSED. This deliberately
  uses the small-sample downgrade rather than claiming population feasibility.

All three studies remain subject to unknown historical publication times and
retroactive API corrections. The generated report labels measured statements
FACT with queries, interpretations INFERENCE with measurement references, and
unmeasured claims UNKNOWN.

### Verification and test impact

Run the offline suite and Python style checks:

```bash
python3 -m pytest -q
python3 -m flake8 cubs_edge_lab tests
```

`pytest` and `flake8` are development tools, not runtime dependencies. Install
them if needed with `python3 -m pip install pytest flake8`.
The suite denies network connections and never rewrites research artifacts.
With both local JSON files present, it re-derives observations from recorded
inputs, checks the query set and manifest provenance, and byte-compares
observations, summary, and report. In a clean clone, data-dependent checks skip
with an explicit reason and the re-creation command. Always-running checks
verify canonical summary bytes, exact report generation from the committed
summary, publication limits, manifest schema, ignored data paths, synthetic
counts, Markdown injection defenses, CLI modes, and failure handling.

Without the raw cache, manifest hashes cannot independently authenticate the
normalized inputs against the original response bytes. External population
completeness and historical contract truth also have no test oracle here;
those remain research limitations. Synthetic fixtures only exercise tests and
never populate the research report.

This probe is research only. It does not implement a candidate product.

### Third-base send/hold feasibility study

After `python3 -m pip install -r requirements.txt`, the feasibility sample can
be fetched with `python3 -m cubs_edge_lab.probe.sendhold`, and its aggregate
report regenerated with `python3 -m cubs_edge_lab.probe.sendhold --analyze`.
For the authorized full retrieval, run
`python3 -m cubs_edge_lab.probe.sendhold retrieve --max-requests 200` in
chunks. After each run, inspect `data/sendhold_retrieve_status.json`; stop
when it reports `"complete": true`. If the command exits with the ceiling
error before the status is complete, read the `count` in
`data/sendhold_request_ledger.json` and set `N` to the smaller of 200 and
`4900 - count`, then run
`python3 -m cubs_edge_lab.probe.sendhold retrieve --max-requests N`. This
smaller final chunk is necessary because a requested chunk larger than the
remaining budget is rejected before making requests. If status still reports
work remaining after the budget reaches 4,900, stop; the ceiling prevents
further retrieval. Each invocation sends no more than its requested number
of new requests. Requests are sequential and limited to 2 per second; the
full run is estimated to take about 41 minutes. A persisted ceiling of
4,900 new requests applies across invocations, including the 107 feasibility
requests already recorded. Cache hits do not count. The command retrieves
2025 and 2026 regular-season schedules and game play-by-play, plus the public
sprint-speed and outfielder arm-strength leaderboards for 2024, 2025 and 2026.

Raw response cache files stay under ignored `data/raw/`. Retrieval metadata is
written to `data/sendhold_manifest.json`, the shared request count to
`data/sendhold_request_ledger.json`, progress to
`data/sendhold_retrieve_status.json`, and failed or skipped requests with
their HTTP status (or `exception`) to `data/sendhold_failures.json`. These
files contain no published raw response content. Failed requests are not
retried automatically; inspect the failure log and seek renewed authorization
before removing that request's failure record and cached response to retry it.
Raw responses are never committed. Data use is local-only, non-commercial research under the
owner's 2026-10-10 authorization: "Two seasons, 2025-2026": "Approve ~4,900
requests. More power, and lets 2026 be a holdout for the model fit on 2025."
Only aggregates and at most 5 short examples may be published.

To build the frozen-design opportunity table and data-only report from the
completed local cache, run `python3 -m cubs_edge_lab.probe.sendhold_data
--root .`. The command is offline, writes the row-level table only under
ignored `data/`, and regenerates `research/sendhold_data.json` and
`research/SENDHOLD_DATA.md` with aggregate counts only.

## November free-agent triage

The triage implementation lives in `cubs_edge_lab/triage.py`,
`cubs_edge_lab/triage_eval.py`, `cubs_edge_lab/triage_config.py`, and
`cubs_edge_lab/triage_cli.py`. `python3 -m cubs_edge_lab.triage_cli fetch`
uses the existing sequential, checksum-verified probe client and writes raw
responses only below ignored `data/`; each newly fetched response is
recorded in `research/raw_manifest.json`. The owner authorized this local-only,
non-commercial research acquisition on 2026-10-09, based on their reading of
MLBAM's terms; no response content is published. Run `fetch` before
`python3 -m cubs_edge_lab.triage_cli data`. Statistics are limited to
2017–2025; Cubs transactions for offseasons 2021–2025 extend through March
2026, as these are transaction records rather than 2026 statistics. The data
command writes ignored ID-joined cohort tables and aggregate-only
`research/data_summary.json` and `research/DATA.md`.

The separately labeled exploratory whole-pool analysis can be regenerated offline
from already-fetched local data with `python3 -m cubs_edge_lab.exploratory_whole_pool --root .`.
It writes aggregate-only `research/exploratory_whole_pool.json` and an exploratory
section in `research/EXPERIMENT.md`; its scope follows the owner's 2026-10-09
authorization for local-only use of cached MLB Stats API data and excludes the
2025 holdout. Re-running `python3 -m cubs_edge_lab.triage_cli evaluate` rewrites
`EXPERIMENT.md` from the primary result and therefore removes that section; run
the exploratory command again afterward.

`python3 -m cubs_edge_lab.triage_cli evaluate` builds outcomes for cohorts 2018–2024 from cached league-wide MLB statistics and writes aggregate-only `research/validation.json` plus its JSON-derived `research/EXPERIMENT.md`; it is offline and never evaluates the 2025 holdout. Run `evaluate` before `preregister`. After a complete, non-early-stop validation, `python3 -m cubs_edge_lab.triage_cli preregister` hashes every `cubs_edge_lab/triage*.py` file and `research/validation.json`. Editing, adding, or deleting any triage module invalidates preregistration. Preregistration refuses missing validation or an early stop. The 2025 outcome builder refuses to run unless every hash matches; the 2025 holdout remains unevaluated.

The cohort selector joins transaction person IDs to season split IDs only.
Feature and outcome helpers enforce season and holdout boundaries; missing
source measurements are not silently converted into measured results. This
data-acquisition stage produces cohort tables and aggregate coverage reports.
The primary evaluation has been run and is documented in
`research/validation.json` and `research/EXPERIMENT.md`; the 2025 holdout has
not been evaluated and no holdout result is produced. Existing response
contents remain local and are not included in the repository.
