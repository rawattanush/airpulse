# AirPulse: Verification and Validation

Version 1.1, 2026-10-07. This document states what was checked, with which result, and what each kind of check does and does not establish. The machine-written record of the results, with the commits they were obtained on, is `evaluation/licence_repair/verification.json` in the research repository; a hosted repository names the commits it was built from in `PUBLIC_REPOSITORY.json`.

## 1. Summary of results

| Check | Result |
|---|---|
| Engine tests | 244 tests: 243 passed, 1 skipped by design, 0 failed |
| Validators | 10 of 10 pass |
| Final audit | 137 of 137 checks pass |
| Application tests | 47 of 47 pass |
| Production build of the application | Completed |
| Clean clone on Linux | Passed: 4 workflows, 13 of 13 checks |
| Run from nothing to the built site | Passed: 3 phases |
| Rehearsal of the hosted repository | Passed: 5 phases on Windows; both workflows on Linux |
| Deterministic rerun | The pinned ledger, byte for byte, on two reruns |
| Engine on the earlier inputs | The earlier ledger, byte for byte |
| Restricted-source scan of the hosted repository and built site | 0 findings |
| Private-data scan of the hosted repository and built site | 0 findings |

No check was removed, skipped or loosened to obtain these results. Section 6 lists the defects that the checks found and how each was resolved.

## 2. Terms

*Verification* asks whether the system was built as specified. *Validation* asks whether what it produces is right for its purpose. Most of what follows is verification. The validation of the forecast itself is the walk-forward evaluation (section 4.1), and its honest summary is that the official forecaster is modestly better than the other baselines on a short record.

## 3. Verification

### 3.1 Engine tests (244)

Run with `python -m pytest tests`. About twenty-three minutes.

| Group | File | Tests | Subject |
|---|---|---|---|
| Data layer | `test_phase1_data.py` | 9 | Loading, checksums, as-of queries, release calendar, labels |
| Forecasting | `test_phase2_6_forecasting.py` | 18 | Baselines, models, features, walk-forward, ledger, replay, determinism, cross-platform comparison |
| Operational pipeline | `test_ops_pipeline.py` | 12 | Adapters, retries, idempotence, issuance, outcomes, health |
| Production pipeline | `test_production.py` | 33 | Registry, due sources, failure isolation, selection, run record, workflows |
| Public product | `test_public_product.py` | 8 | Licence classes, feature gate, regeneration |
| Deployment | `test_deployment.py` | 14 | Workflow order and stops, credentials, allow-list, pre-upload checks |
| News-adjusted outlook | `test_news_outlook.py` | 5 | Press reading keeps no headline; a failed reading changes nothing; the model never alters the official outlook; owner's decision required |
| Licence repair | `test_licence_repair.py` | 11 | Release reconstruction, no later value in a column, licence status and gate, absence of the retired path |
| Replay and dashboard | `test_dashboard_replay.py` | 7 | Replay shows only what was published |
| Research record | seven files of the event layer, `test_v2_expansion.py`, `test_v3_global.py`, `test_v4_aviation.py`, `test_derivatives.py` | 127 | Research results; not requirements of the product |

The one skipped test applies only inside a hosted repository; five test files are shipped there and run in its workflow (the tests that apply there pass; those needing research files are skipped by design).

**What the tests prove.** That each unit behaves as specified on the cases written for it, including failure cases: a corrupt answer, a timeout, a broken record chain, a source switched off. Tests of adapters run against recorded answers with a fixed clock, so they are repeatable.

**What they do not prove.** That the cases are complete. That a publisher's page will keep its present form. That the code is free of defects on inputs nobody wrote a case for. A passing suite did not prevent the defects of section 6 from being found by other means.

### 3.2 Application tests (47)

`npm test` in the application: seven files covering the data contract, the derived values shown on pages, the scenario arithmetic, the absence of removed features and of typed figures.

**Prove:** that the exported files have the shape the pages expect and that the functions that derive displayed values are correct on their cases. **Do not prove:** that pages look right. There is no automated test of rendering, layout, accessibility or behaviour in a real browser.

### 3.3 Validators (10)

Scripts that check consistency between artefacts: every file is registered; sources and data samples match their inventory and checksums; requirements, traceability and phases are consistent; the leakage condition holds for every forecast on the ledger; documents state no metric that no experiment recorded; the report can be built.

**Prove:** that the records agree with each other. **Do not prove:** that what they agree on is true of the world.

### 3.4 Final audit (137 checks)

`python scripts/final_audit.py` recomputes claims from primary material rather than reading them from a summary: every feature recomputed after removing later data; every reported metric recomputed from the ledger; the comparability of the forecasters; the consistency of the documents; and, section by section, the evidence of each later pass (production pipeline, public product, hosting, licence repair). Eighteen sections, A to Z in part.

**Proves:** that the stated results follow from the stored data by the stated method, on the day it was run. **Does not prove:** that the method is the best one, or that the evaluation generalises to future months.

### 3.5 Production build

`npm run build` completes and writes the application shell for deep links. **Proves** that the application compiles and bundles. **Does not prove** that it behaves correctly; that is the rehearsal's job (3.8).

### 3.6 Clean clone on Linux

A fresh clone of the committed state, in a new environment installed from the package index, with the four workflows of the research repository executed step by step by a local stand-in for the hosting provider's runner, against the real sources.

**Proves:** that the repository is complete (nothing needed is uncommitted or machine-specific), that the pinned dependencies install, that the pipeline works on the operating system of the hosted runner, and that the benchmark ledger rebuilt there is numerically equivalent to the record. **Does not prove:** anything about the provider's scheduler, its token and permissions, its runner image, or its network path to the sources. It is a local run, not a run on the provider.

### 3.7 From nothing to the built site

On fresh clones with every generated file deleted: a run with the network builds the stores, fetches, validates, issues forecasts, exports, tests and builds (phase A); a second run changes nothing (B); a run with every source unreachable completes, invents nothing and still builds a site that names the sources as not healthy (C).

**Proves:** that no step depends on state left over from development, that the run is idempotent, and that total loss of the network is survived. **Does not prove:** behaviour under partial or malformed answers beyond the cases of the unit tests.

### 3.8 Rehearsal of the hosted repository

The repository that would be pushed is assembled and its own two workflow files are executed on fresh clones, with a bare copy standing in for the remote: checks on a change (A); a production run with real sources, the site then served by a static server that behaves like the host, with every route reloaded (B); a second run on what the first pushed (C); a run with the sources down (D); a run after one character of the ledger was altered (E). The engine part is repeated on Linux.

**Proves:** that the hosted repository is self-sufficient; that the order and the stops of the workflow hold; that the site works under a sub-path and on a reload; that a broken record stops publication; and that the licence gate decides the upload: with a source pending the upload step and the deploy job are skipped (rehearsed before the owner's decision of 2026-10-08), and with every source cleared the gate is open. **Does not prove:** that the provider's own actions (checkout, set-up of Python and Node, Pages configuration, upload, deployment) behave as expected. Those run only on the provider and are listed in the evidence as not run locally.

### 3.9 Deterministic reruns

The evaluation was rerun twice, once from a rebuilt store. Both ledgers have the pinned SHA-256. Separately, the engine was run on the inputs held before the licence repair and reproduced the earlier ledger byte for byte.

The experiment register (`evaluation/experiments.csv`) carries the date of the run, so a rerun on a later day differs from the committed register in that column only; the ledger check restores it.

**Proves:** that the evaluation is a function of its inputs on this platform, and that the licence repair did not change the method. **Does not prove:** identical bytes on another platform; there the comparison is numerical, within tolerances justified by measurement.

### 3.10 Scans of what would be published

Every committed file of the hosted repository (compressed files read as their content) and every file of the built site was searched for the retired access path (addresses, file names, identifiers, series codes, names) and for private material (e-mail addresses, home folders, keys, tokens).

Result: no finding. Reviewed and judged not private: the public contact address of the Energy Information Administration inside its own spreadsheets, and placeholder paths in one test.

**Proves:** the absence of the patterns searched for. **Does not prove:** the absence of anything the patterns do not describe, and it is not a legal review. One fact the scan reports and does not change: the single commit of the assembled repository carries the name and e-mail address of the git configuration of the machine that built it. The hosting guide explains how to replace them before a push.

### 3.11 Documentation

- **Specification PDF.** `docs/SRS.pdf` is built from `docs/SRS.md` by `scripts/build_srs.py`. The build fails if a heading, figure or table cannot be found in the printed text, if page numbers move between its two passes, or if a diagram label would print below 7.5 points. After the build every page was rendered to an image and read: cover, contents, lists, each figure and table, page numbers, captions.
- **User guide.** Every route of the application was opened in the production build of the site, served the way the static host serves it, and `docs/USER_GUIDE.md` was written from what the pages showed. The scenario calculator was exercised with typed values.
- **Consistency.** The documents were compared with each other, with the production policy and with the site on the target, the classes, the horizon, the official forecaster, the sources and their status, the retired access path, the scope and the counts of this section.

**Proves:** that the documents describe the system that was inspected. **Does not prove:** that they will stay true after a change; they are maintained by hand, except the requirement tables and the traceability matrix, which were generated from one data set.

## 4. Validation of the forecast

### 4.1 Walk-forward evaluation

Every month from January 2016 is forecast using only what had been published by its issuance date and scored on its final value. On the validated series the official forecaster (the seasonal baseline) is right in 67 of 122 months, against 58 for the majority baseline, 57 for persistence, 62 for the logistic model and 61 for the boosted trees.

**What this supports.** That, among the forecasters tried, a calendar rule is the best available benchmark for this index, and that the two models did not add to it.

**What it does not support.** A claim of skill beyond a small margin; a claim about any other index, lane or rate; a claim about the future. The sample is 122 months and no significance is claimed. The record is retrospective; prospective forecasts have been issued for one month and none has an outcome yet.

### 4.2 Leakage

Three independent checks: features recomputed after physically removing later observations are unchanged; for every forecast, the latest information time of its features does not exceed its issuance time; forecasts recomputed in a replay equal the ledger. These establish that the evaluation did not use later information through the paths examined.

### 4.3 The reconstruction of releases

The rebuilt index history was compared once with the history held before: 298,686 of 298,774 cells equal. The 88 differences are in the one month per release whose value is inferred, by 0.1 or 0.2 index points. The official forecaster does not read that month; its forecasts are unchanged in every month both ledgers hold.

## 5. What has not been verified

- A run on the hosting provider. None has taken place.
- The site in a range of browsers and devices; accessibility against a standard.
- Behaviour over months of unattended operation.
- The readings of the publishers' terms by a lawyer.
- Whether the Energy Information Administration's spot prices may be redistributed. It was not asked; the owner publishes them on his own decision (`docs/DATA_AND_LICENSING.md`, section 2.2).

## 6. Defects found by verification in the last pass

Stated because a list of passing checks says nothing about how much they can find.

| Found by | Defect | Resolution |
|---|---|---|
| Rerun of the tolerance study | The cross-platform check counted rows above a list of levels that lacked the newly tightened tolerance | Level added |
| Full test run | Two tests held constants of the earlier ledger | The tests read the record |
| Reading the generated report against the comparison data | The report said no outcome of the official forecaster differed; two rows differ in their first-published outcome | The report states it |
| Independent scan of the assembled repository | The builder applied the search for the retired path only after the folder was marked as hosted, so not while assembling it; one application test carried the service's name inside its own detection pattern | Builder corrected; pattern written in pieces; audit extended to the application's files |
| Rehearsal of the hosted repository | One hosted test required result files that the licence repair had removed from that repository | The test states both cases exactly; the selection rule is unchanged |

The last two were found only by executing the thing that would be published. That is the argument for the rehearsal.

## 7. Reproducing the verification

```
python -m pytest tests                           # engine tests
python claude/harness/run_all.py                 # validators
python scripts/final_audit.py                    # final audit
python -m src.cli build-db && python -m src.cli backtest && python scripts/check_benchmark_ledger.py --strict
cd ../airpulse-web && npm test && npm run build  # application
bash scripts/clean_runner_check.sh <repo> <work folder> <evidence file>        # clean clone (Linux)
python scripts/zero_to_site.py <empty folder>                                  # from nothing
python scripts/build_public_repo.py <new folder> && python scripts/verify_public_repo.py <that folder> <empty folder>
```

These commands exist in the research repository. The hosted repository contains the engine tests that apply to it, the ledger check and the pre-upload checks, and runs them in its workflow.
