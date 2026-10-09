# AirPulse: Operations

Version 1.1, 2026-10-07. How the system runs, what it does when something goes wrong, and how to recover and reproduce. State when this document was written: the schedule is defined and rehearsed and the repository is released for publication; the Data page of the site shows whether scheduled runs are on record.

## 1. The production run

One command is the whole run:

```
python scripts/production_run.py                 # fetch what is due, issue what is due, validate, write the registry
python scripts/production_run.py --offline       # no network: rebuild from the files held, issue anything not yet issued
python scripts/production_run.py --force bls     # treat a group as due (fuel, bls, aviation, press; several allowed)
python scripts/production_run.py --plan          # print what is due and stop
```

Its steps, in order:

1. **Prepare.** Build the benchmark store and the evaluation from the frozen snapshot if absent; check that the operational files are present.
2. **Decide what is due** (section 3).
3. **Ingest.** For each due source: fetch, validate, replace the held file or leave it, record the attempt.
4. **Rebuild** the as-of store from the current files.
5. **Issue** the forecast of every month that is due and not yet on the ledger; **record outcomes** of months whose values are now published.
6. **Air-traffic layer**, as its own process.
7. **Gate.** Record chains intact; declarations consistent; production policy consistent; official forecaster singled out by the rule.
8. **Registry and run record.** One entry is appended to `operations/production_runs.jsonl`.

Exit codes:

| Code | Meaning | What follows |
|---|---|---|
| 0 | Completed; every production source healthy | Commit, export, build, gates |
| 2 | Completed; a source failed, is degraded or stale | The same; the site shows the state; the last job of the workflow fails so that the owner is notified |
| 1 | The gate failed | Nothing is committed, exported, built or uploaded. The previously published site stays |

## 2. The scheduled run

In the hosted repository one workflow (`.github/workflows/production.yml`) starts the run:

| Schedule (UTC) | Purpose |
|---|---|
| Daily, 07:11 | Whatever is due; flight lists |
| Monday, 08:23 | The weekly fuel release |
| The 23rd, 09:31 | After the release window of the index; requires the outlook of the newest month due |
| By hand | Any time; a group can be forced |

Runs never overlap: the workflow has one concurrency group and does not cancel a run in progress.

The build job, each step conditional on all before it:

```
production run -> report -> engine tests -> record chains verified -> commit operations/ -> export
   -> application tests -> build -> pre-upload checks -> licence gate -> upload (only if the gate is open)
```

Then `deploy` (only if the licence gate is open), `licence` (fails while a confirmation is open) and `health` (fails when a source is not healthy).

## 3. When a source is asked

A scheduler may start a run every day; a run does not fetch everything every day. A source is due when:

- it has never been fetched; or
- its check interval has passed since the last attempt; or
- its newest data are older than the interval at which the publisher normally adds data, and the last attempt is at least 20 hours old (so the monthly index is asked daily only from the day its next release is expected until it arrives); or
- its last attempt failed (one retry per run).

## 4. Scenarios

### 4.1 The source is available and has new data

The adapter retrieves it, validates it, replaces the current file and its checksum, keeps the raw answer with its date, and records UPDATED. The store is rebuilt. If the new data are a release of the index, the forecast of the next month is issued once per series and forecaster, and outcomes of earlier forecasts that the release settles are recorded.

### 4.2 The source is available and has nothing new

The record says UNCHANGED. No file is written, no forecast is issued. A run on unchanged sources changes nothing but the clock-derived fields of the registry.

### 4.3 The source is late

Nothing is wrong yet. The registry shows the age of the newest data. The source is asked again on each daily run from the day new data are expected. When the age exceeds the limit declared for the source, its state becomes STALE and the site says so. For the index this has a direct consequence: **no forecast is issued for the next month until the release it depends on has been published and retrieved.** The site continues to show the last issued outlook with its date.

### 4.4 The source fails

Timeout, refusal, server error or rate limit. The adapter makes at most three requests per address with fixed pauses and does not retry a client error. The attempt is recorded as FAILED with the reason. The data held are untouched. Other sources and layers proceed. The run ends with code 2. State: DEGRADED while the held data are within their age limit, then STALE or FAILED. The source is retried on the next run.

### 4.5 The source returns invalid data

An empty, truncated, malformed or implausible answer (a release dated after the fetch, a table without the expected rows, a merge that would alter a stored column, a file the engine's parser rejects). Treated exactly as a failure: recorded with the reason; the current file and its checksum are not replaced; nothing downstream sees the candidate. The rejected answer is not stored as current data.

### 4.6 A forecast cannot be safely issued

Three cases, each ending without a forecast and without a substitute:

- The release that fixes the issuance date is not on record (4.3, 4.4, 4.5).
- The rule for the official forecaster does not single one out (the two criteria disagree, or a stored decision names another): the gate fails with exit code 1.
- The month would be issued on the day its own outcome is published. The engine gives such a month no issuance date. This happened once in the record (January 2026).

The system never fills a gap with an estimate, and never issues a forecast for a month twice.

### 4.7 A licence status is unresolved

A production source with a status other than CLEARED does not stop the run: data are fetched, forecasts issued, the site built and checked. The licence gate then closes: the upload step and the deploy job are skipped and the `licence` job fails with a message naming the sources. No source is in that state at present: the two fuel sources were cleared by the owner's decision of 2026-10-08, without a confirmation of the publisher (`docs/DATA_AND_LICENSING.md`, section 2.2).

To open the gate after the publisher has answered: record the answer in `config/production_sources.yaml` of the research repository (status CLEARED, with date and text as evidence), rebuild the hosted repository, verify it, push.

### 4.8 A record has been altered

If any entry of the ingestion log, the forecast ledger or the outcomes does not match its hash chain, the gate fails. Nothing is committed or published. Recovery is from version control (section 6).

## 5. Export, build and checks

- **Export** (`npm run export` in the application): written to a staging folder, validated against the contract, published together. A violation publishes nothing.
- **Build** (`npm run build`): static files under the base path of the repository, with `404.html` for deep links.
- **Pre-upload checks** (`python scripts/deployment_checks.py all --base <path>`): the repository, the exported data and the built site are searched for secrets, development addresses, restricted paths, the retired access path, fields of removed features, files above the size limit and broken deep links.
- **Licence gate** (`python scripts/deployment_checks.py licence`): exit 0 only if every production source is CLEARED.

## 6. Recovery

| Situation | Action |
|---|---|
| A source failed for some days | None. It is retried each run; the data held remain valid until their age limit |
| A publisher changed its page and the adapter rejects it | Fix the adapter in the research repository, with a test built from the new answer; rebuild the hosted repository |
| The gate failed on a broken chain | Inspect the last commit of `operations/`; restore the files from the previous commit; run again. Never edit a record by hand |
| A run was interrupted | Run again. An interrupted fetch leaves the held file as it was; a forecast is keyed and cannot be issued twice |
| The derived store is missing or corrupt | Delete `data/*.sqlite`; the next run rebuilds it |
| The site shows old data although runs succeed | Check the run summary for the licence job and the upload step; a closed licence gate builds without publishing |
| Everything generated is lost | `python scripts/zero_to_site.py <empty folder>` in the research repository shows the path from the committed files to the built site |

## 7. Monitoring

There is no monitoring service. The system reports through:

- the result of the workflow run (a failed `health` or `licence` job notifies the owner through the provider's ordinary notifications);
- the run summary written by the workflow;
- `operations/sources.yaml`, the generated registry, and `operations/status.json`;
- the Data page of the site, which shows the same state to everyone.

## 8. Reproducibility

```
python -m src.cli build-db                         # store from the frozen snapshot
python -m src.cli backtest                         # walk-forward evaluation; writes evaluation/forecast_ledger.csv
python scripts/check_benchmark_ledger.py --strict  # the ledger equals the pinned record (same platform)
python scripts/check_benchmark_ledger.py           # on another platform: numerically equivalent within justified tolerances
python scripts/build_bls_vintages.py build         # the index history from the kept release tables, offline
python -m src.cli replay --series IC1312 --forecaster BL-SEA --month 2021-09    # one past forecast recomputed and compared with the ledger
```

Dependencies are pinned (`requirements.txt`, the application's lock file). The evaluation takes about two minutes.

## 9. Clean-clone verification

Before the hosted repository is pushed, and after any change to it:

1. In the research repository, commit everything. Run the engine tests, the validators and the final audit.
2. Run the clean-clone check on Linux (`scripts/clean_runner_check.sh`): the workflows on a fresh clone in a new environment.
3. Assemble the hosted repository into a new folder (`scripts/build_public_repo.py`). The builder refuses uncommitted changes and stops on any finding.
4. Rehearse it (`scripts/verify_public_repo.py`) and repeat the engine part on Linux (`scripts/public_repo_linux_check.sh`).
5. Only then follow `docs/HOSTING_STEP_BY_STEP.md`.

Evidence of each step is written to `evaluation/` and checked by the final audit against the commits it was obtained on: evidence older than the code it covers fails the audit.

## 10. What the operator must not do

- Edit a generated file, a ledger or a record by hand.
- Change `src/config.py` or a pre-registered protocol without a change record written first.
- Remove the licence gate or a check to obtain a green run.
- Push the research repository to a public remote: it contains data that may not be redistributed. Only the assembled hosted repository is for publication.
