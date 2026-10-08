# AirPulse: System Design

Version 1.1, 2026-10-07. Companion to the specification (`docs/SRS.md`). This document explains how the system is built and, above all, why. Diagrams referred to by number are those of the specification; their sources are in `docs/diagrams/`.

## 1. Design goals and the forces behind them

Four properties drove every decision. They are listed with the constraint that produced each.

| Goal | Why it is needed here |
|---|---|
| **Point-in-time correctness.** A forecast must be reproducible from what was published at its date | The target is revised three times after first publication. A model evaluated on final values looks better than it could have been in use |
| **Reproducibility without infrastructure.** Every stored result regenerates from files in the repository | The project has no server, no budget and one maintainer. Whatever cannot be rebuilt by a command will eventually be wrong |
| **Fail closed.** Bad input changes nothing; a failed check publishes nothing | The run is unattended. Nobody is watching when a publisher changes a page |
| **Say only what the records support.** Status, freshness, licence state and the choice of forecaster are derived, not typed | A site that claims more than its pipeline did is the failure mode this kind of product is known for |

## 2. Architectural style

The system is a **batch pipeline with a static presentation tier**. A scheduled job runs the pipeline end to end, commits its state to the repository and builds a static site. There is no running service.

The alternatives were considered and rejected for stated reasons:

- *A web service with a database.* It would need hosting, credentials and monitoring, and would add nothing: the data change at most daily, and every page can be computed in advance.
- *A notebook-driven analysis.* It cannot be run unattended, and its results cannot be tied to the state of its inputs.
- *A data-warehouse layout with incremental models.* The data volume is a few megabytes. A store that is rebuilt from files on every run is simpler and cannot drift from its inputs.

The consequence of the chosen style is that **the repository is the database of record**. Operational state (current files, ledgers, run records) is committed by the workflow. The SQLite store is derived and never committed.

## 3. Module decomposition

Figure 5 of the specification shows the packages. The decomposition follows the direction of data, and dependencies point one way only.

| Layer | Packages | Responsibility | May depend on |
|---|---|---|---|
| Configuration | `config/*.yaml`, `src/config.py` | Declarations of sources; production policy; frozen constants of the method | nothing |
| Validated engine | `src/ingestion`, `src/database`, `src/preprocessing`, `src/validation`, `src/features`, `src/forecasting`, `src/evaluation`, `src/api` | From files to store, labels, features, forecasts and the evaluation | configuration; earlier packages of this list |
| Operational pipeline | `src/ops`, `scripts/production_run.py`, `src/aviation` (collector, operations) | Retrieval, validation, operational copies, issuance, outcomes, selection | engine, observability |
| Observability | `src/observability` | Append-only records, registry of sources, policy checks | configuration |
| Publication | `airpulse-web/scripts`, `airpulse-web/src`, `scripts/deployment_checks.py` | Export under a contract, the site, the checks before upload | the records and files written by the layers above, never their code paths |
| Research only | `src/news`, `src/v2`, `src/v3`, `src/aviation/experiment.py`, `src/dashboard` | Experiments. `src/v2`, `src/v3` and the experiment commands are not in the hosted repository; `src/news` and `src/dashboard` are present in the hosted repository as code the pipeline imports, with the event layer's sources switched off | engine (read only) |

### 3.1 Separation of concerns

Three separations carry most of the design.

1. **Evaluation and operation are separate programs over the same engine.** The evaluation (`src/api/backtest.py`) reads the frozen benchmark snapshot and writes `evaluation/`. The operational pipeline (`src/ops`) reads operational copies and writes `operations/`. A test asserts that an operational run never writes to the benchmark. The same forecasting code serves both, so an operational forecast equals what the evaluation gives on the same inputs.
2. **The publication layer reads artefacts, not objects.** The export is a separate program in the application's repository. It reads the ledger, the registry and the policy as files. A change inside the engine cannot alter the site unless it alters a file, and files are checked against a contract.
3. **The air-traffic layer is isolated.** It is started only as its own process and has its own records. It cannot affect a forecast, by construction and by test.

### 3.2 Cohesion and coupling

Each engine package has one reason to change: `preprocessing` changes if the label rule changes, `features` if a feature definition changes, `forecasting` if a forecaster changes. The constants they share are in `src/config.py`, which is frozen: changing it requires a change record written first.

Coupling between layers is through data contracts (section 4), not through shared classes. The cost is some duplication of field names between the exporter and the application; the benefit is that either side can be tested alone against recorded files.

A rule enforced by a validator (`validate_phase_boundaries.py`): no package imports a package of a later layer.

## 4. Data contracts

| Contract | Between | Form | Enforced by |
|---|---|---|---|
| Current file and sidecar | adapter and engine | The publisher's data in a fixed layout, with `<file>.meta.json` holding source, address, retrieval time and SHA-256 | Loader refuses a file that differs from its sidecar |
| Vintage matrix | adapter and engine | CSV: one row per month, one column per release, named `<series>_<YYYYMMDD>` | The engine's own parser must accept a merged file before it replaces the held one; stored columns must be unchanged |
| Operational records | pipeline and everything downstream | JSON lines; each entry has `seq`, `prev`, `hash` | `records.verify`; the production gate |
| Source declaration | maintainer and pipeline | `config/sources.yaml`: identifier, address, intervals, staleness limits | Registry check on every run |
| Production policy | maintainer and publication | `config/production_sources.yaml`: licence class, licence status, rights, features and their sources | `policy.check`; refuses unknown or restricted classes |
| Export | exporter and application | `public/data/*.json` with a version and a content hash | Staged write; contract tests of the application; refusal of fields of removed features |

**Engineering decision: hash-chained JSON lines instead of a database for operational records.** The records must be diffable in version control, appendable by a workflow without a migration, and verifiable by a short function. A chain of SHA-256 hashes gives tamper evidence that a table does not.

## 5. Interfaces

The system has no network interface of its own. Its interfaces are:

- **Command line.** `python -m src.cli build-db | backtest | replay | report-metrics` for the engine; `python scripts/production_run.py [--offline] [--force <group>] [--plan]` for a run; `python scripts/deployment_checks.py repo | data | bundle | all | licence | size` for the checks; `npm run export | test | build` in the application.
- **Outbound HTTP.** GET requests to the publishers' pages and files, and one POST form to the Bureau's public data interface. Every request carries a client name with a contact reference; requests are bounded in number and spaced by fixed pauses.
- **Files.** Everything else. The exported JSON is the only interface the browser sees.

## 6. The source adapter pattern

Every source is read by an adapter with one signature: it receives the declaration of the source and the location of the file held, and returns exactly one record. Whatever happens (new data, no new data, a refusal by the publisher, a parse failure) the result is a record with one of a small set of outcomes: UPDATED, UNCHANGED, FAILED and variants of partial success.

```
adapter(source_id, declaration, current_dir, raw_dir, get, now) -> ingestion record
```

`get` and `now` are parameters. Tests replace them with recorded answers and a fixed clock, so every adapter is tested without the network, including its failure paths.

The registry maps a source kind to its adapter. Adding a source means writing one adapter and one declaration; nothing else in the pipeline changes.

**Why adapters own validation.** An adapter knows what a valid answer from its publisher looks like. The adapter for the Bureau's releases, for example, checks that the release table has the expected rows, that no release is dated after the fetch, and that merging the new column leaves every stored column byte-identical. A generic validation stage could not know these things.

### 6.1 Reconstruction of releases

The Bureau publishes each month's values in a news release and keeps the releases in an archive; it does not publish a machine-readable history of what each release said. The adapter rebuilds that history under a rule fixed in advance (change record CL-024):

- the newest month and the month before it are taken as printed;
- the month two before the newest was revised a second time and is not printed as an index. It is inferred from the two monthly percent changes that the release does print. When more than one one-decimal value fits, the value already known is kept if it fits; otherwise the value nearest the midpoint is taken and the cell is flagged in a log;
- older months are final and are read from the Bureau's database;
- a release that printed no table adds a column that repeats what was known.

The rule was committed before any rebuilt value was compared with the history held until then. The comparison found 88 differing cells in 298,774, all in the inferred month, by 0.1 or 0.2 index points. The rule was not adjusted afterwards.

## 7. Validation architecture

Validation happens at four points, each closing a different gap.

| Point | Question | Mechanism |
|---|---|---|
| At ingestion | Is this answer what the publisher normally sends? | Adapter checks; the engine's parser |
| At load | Is this file the file that was accepted? | SHA-256 against the sidecar |
| At the production gate | Are the records intact and the declarations consistent? | Chain verification; registry and policy checks; selection of the official forecaster |
| Before upload | Is anything in the repository, the export or the built site that may not be published? | `deployment_checks.py`: secrets, development addresses, restricted paths, the retired access path, fields of removed features, sizes, deep links; then the licence gate |

Separately from the run, ten validators and a final audit of 137 checks examine the research repository for consistency between code, records and documents (see the verification document).

## 8. Failure handling

The governing rule: **a failure may withhold new information; it may never replace good information with bad, and it may never be silent.**

- A candidate file is written beside the current file, parsed and checked. Only then is the current file replaced. A rejected candidate leaves the current file and its sidecar untouched.
- Each layer of a run is a separate process with a time limit. A process that crashes or hangs is recorded with its exit code and the last lines of its output, and the run continues with the next layer.
- The run distinguishes three results by exit code: 0 (all production sources healthy), 2 (completed; a source failed, is degraded or stale; the site is built and shows that state), 1 (the gate failed; nothing new may be published).
- A source that fails keeps its last valid data. The registry reports it as DEGRADED while those data are within the declared age limit, and STALE or FAILED beyond it. The site shows the state and the reason.
- A forecast is issued only when the release it depends on is on record. If the index was not fetched, no forecast is issued, and none is estimated.

Figure 14 of the specification gives these states.

## 9. Deterministic execution

- Dependencies are pinned to exact versions.
- Every model has a fixed seed; the boosted trees run single-threaded in deterministic mode.
- Records carry no clock where a clock is not information: the selection record, for example, changes only when the selection or its basis changes.
- The ledger of the evaluation is pinned by its SHA-256. On the platform that produced it, a rerun must give the same bytes.
- On another platform the fitted models differ in the last digits of a 64-bit float. A comparison (`scripts/check_benchmark_ledger.py`) accepts a difference only if every non-probability field is identical, the baselines are identical, every probability of a model is within that model's tolerance, and every reported metric is unchanged at reported precision. The tolerances (1e-10 for the logistic model, 1e-14 for the boosted trees) are the smallest powers of ten at least 100 times the measured platform difference, and a study shows that every tested change of the implementation lies far outside them.

## 10. Configuration

There are three kinds, kept apart on purpose.

| Kind | File | Who changes it | Guard |
|---|---|---|---|
| Method constants (target, band, first test month, seed, feature version) | `src/config.py` | Nobody without a change record | Hash in a register of frozen files |
| Source declarations (addresses, intervals) | `config/sources.yaml` | Maintainer | Registry consistency check |
| Production policy (licence status, rights, which features are public) | `config/production_sources.yaml` | Maintainer | Policy check; licence gate |

No configuration is read from the environment except an optional contact reference for the HTTP client name. There are no secrets.

## 11. Storage

| Store | Content | Lifetime |
|---|---|---|
| `research/data_samples/`, `research/bls_releases/` | The benchmark snapshot: inputs of the evaluation, and the release tables they were rebuilt from | Frozen; changes only under a change record |
| `operations/current/` | Operational copies of the inputs, extended by each run | Committed by the workflow |
| `operations/raw/` | Publishers' answers as retrieved, dated | Committed; never rewritten |
| `operations/*.jsonl` | Ingestion log, forecast ledger, outcomes, run records | Append-only, hash-chained |
| `data/*.sqlite` | The as-of store | Derived on every run; ignored by version control |
| `evaluation/` | Ledger of the evaluation, result tables | Regenerated by `backtest`; pinned |
| `airpulse-web/public/data/` | Exported files | Generated; not committed in the hosted repository |

**Engineering decision: the as-of store is a revision log.** The table `observations` holds one row each time a value first appears or changes, keyed by series, observation date and availability date. "The value of month *m* as known on date *d*" is the row with the latest availability date not after *d*. This makes point-in-time queries a single indexed lookup and makes it impossible to read a revised value by accident, because there is no "current value" column.

## 12. Export contract

The exporter writes into a staging folder, validates every file against the contract, computes a content hash over the files, and only then moves them into place. A failed check publishes nothing and leaves the previous export.

The export is the single place where the production policy is applied to data: a feature that is not PRODUCTION READY has no field in any exported file, and a test fails if one appears. The page of a removed feature therefore cannot show stale content; it has nothing to read.

## 13. Web architecture

A React single-page application built by Vite into static files.

- **No runtime dependencies on other services.** The application requests only its own bundles and `data/*.json` under its base path. Fonts are bundled.
- **Routing on a static host.** The build writes a copy of the application shell as `404.html`, so that the host answers any deep link with the application, which then resolves the route.
- **Base path.** Every address is relative to a base path set at build time, since the site is served under the name of the repository.
- **One page, one job.** Each page answers one question; values come from the export with their source and date; nothing is typed into a page. Tests fail on a hard-coded figure.
- **State.** No account, no cookie, no local storage. The scenario calculator computes in the browser from what the visitor types.

## 14. Deployment architecture

Figure 6 of the specification. Two repositories exist during development and one is deployed:

- the **research repository** holds everything, including research data that may not be redistributed;
- the **hosted repository** is assembled from the committed state of the research repository and of the application by an allow-list (`deploy/public/manifest.yaml`). Only named paths are taken. A list of paths that may never be taken is checked against the result.

One workflow (`production.yml`) runs on three schedules and by hand, never twice at once. Its build job proceeds in a fixed order, each step conditional on all before it: production run, report, engine tests, verification of the record chains, commit of the operational state, export, application tests, build, pre-upload checks, licence gate, upload. A separate job deploys, and a further job fails when a source is not healthy, so that the owner is notified while the site still shows the state.

**Why the state is committed before the site is built.** If the export or the build fails, the record of what was fetched and issued is already safe. The site can be rebuilt from the state; the state could not be rebuilt from the site.

## 15. Security considerations

- **No credentials exist.** Sources are public; the workflow uses only the provider's own token, with write permission granted to the single step that commits the operational state. The checkout keeps no credential.
- **Only the provider's own actions are used,** at a named major version.
- **No expression of the workflow is interpolated into a shell command.**
- **Untrusted input is data.** Retrieved content is parsed as CSV, a spreadsheet, HTML tables or JSON; nothing retrieved is executed.
- **Pre-upload checks** search every text file of the repository, the export and the built site for secrets, private keys, addresses of a development machine and e-mail addresses in exported data.
- **Attack surface of the deployed site:** static files. There is no form that reaches a server and no user content.

## 16. Licensing controls

Licence status is treated as an input of the build, like a test result.

1. Every source carries one status in the policy, with the evidence it rests on and, if a question is open, the question.
2. The policy check refuses a production source whose licence class is unknown or restricted.
3. The allow-list of the hosted repository excludes research data; a second, independent check searches the assembled repository for any file, address, identifier or name of the retired access path. It is applied while the repository is assembled and again by the repository's own tests.
4. The licence gate at the end of the build job passes only if every production source is CLEARED. Otherwise the upload step and the deploy job are skipped and a dedicated job fails.

The effect is that publication cannot happen by oversight: clearing a source is an edit to one file, visible in version control, and the workflow follows the file.

## 17. Known design debts

- `src/ops/selection.py` reads a helper from `src/dashboard`, a package that is otherwise a research tool. The helper should move into the engine.
- The production run keeps a dormant branch for a weekly layer that no declared source uses.
- The operational pipeline imports the event layer, so its code travels with the hosted repository although its sources are switched off there. The import should become optional.
- The hosted repository's selection record cannot list the decisions of the research passes, whose result files are not in that repository. The rule is unaffected; the record there is shorter.
- Accessibility and responsiveness are implemented by convention and are not tested.
