# Requirements Traceability Matrix

AirPulse, version 1.1 of the specification (`docs/SRS.md`). Date: 2026-10-07.

This matrix links every requirement of the specification to the design component that carries it, the module that implements it, the tests that verify it and the evidence that validates it. Design components are described in `docs/SYSTEM_DESIGN.md`; tests and evidence in `docs/VERIFICATION_AND_VALIDATION.md`.

## 1. How to read the matrix

- **Baseline** names the requirement of the frozen baseline (`requirements/requirements.csv`, 155 requirements) from which the specification's requirement is consolidated. The baseline has its own, finer matrix in `traceability/requirements.csv`, which a validator checks on every run of the test workflow.
- **Test** identifiers are those in the names of the test functions: T (`tests/test_phase1_data.py`, `tests/test_phase2_6_forecasting.py`), OP-T (`tests/test_ops_pipeline.py`), PR-T (`tests/test_production.py`), PB-T (`tests/test_public_product.py`), DP-T (`tests/test_deployment.py`), LR-T (`tests/test_licence_repair.py`), DB-T (`tests/test_dashboard_replay.py`). Application tests are the files of `airpulse-web/tests`.
- **Evidence** names a check beyond the unit tests: a validator, a section of the final audit (`scripts/final_audit.py`), the clean-clone run, a rehearsal or a scan. Results are recorded in `evaluation/licence_repair/verification.json`.
- **Status**: *Implemented* or *Verified* means the tests and the evidence named pass on the commits stated in the verification document. A qualified status says what is missing.
- The tests of the research record (event layer, experiment passes) are in the research repository only; they verify research results, not requirements of the product, and are not listed here.

## 2. Functional requirements

| Requirement | Design component | Source / module | Tests | Validation evidence | Baseline | Status |
|---|---|---|---|---|---|---|
| **FR-001** Source declaration and registry | Observability: source registry | `src/observability/sources.py`, `registry.py` | PR-T01, PR-T04 | Final audit P; operations report | REQ-PROD-001, REQ-PUB-001 | Implemented |
| **FR-002** Publication-aware scheduling of sources | Operational pipeline: orchestrator | `scripts/production_run.py` (`due`) | PR-T14 | From-zero rehearsal, phase B | REQ-PROD-008 | Implemented |
| **FR-003** Source ingestion through adapters | Operational pipeline: source adapters | `src/ops/adapters.py`, `bls.py`, `eia.py`; `src/aviation/collector.py` | OP-T2, OP-T3, OP-T4, LR-T01, PR-T07 | Clean-clone run (real sources) | REQ-OPS-001, REQ-OPS-004, REQ-OPS-005, REQ-PROD-004 | Implemented |
| **FR-004** Validation before acceptance | Operational pipeline: validation | `src/ops/adapters.py`, `src/ingestion/loaders.py` | PR-T05, PR-T08, T01 (checksum) | Hosted rehearsal, phase D | REQ-OPS-002, REQ-PROD-003, REQ-DATA-006 | Implemented |
| **FR-005** Idempotent ingestion | Operational pipeline: source adapters | `src/ops/adapters.py` | OP-T2 | From-zero rehearsal, phase B; hosted rehearsal, phase C | REQ-OPS-003 | Implemented |
| **FR-006** Preservation of raw data and provenance | Canonical storage: provenance | `src/ingestion/loaders.py`, `src/ops/adapters.py` | T01, T13, PR-T13 | Validator: data contracts | REQ-DATA-003, REQ-DATA-006, REQ-PROD-007 | Implemented |
| **FR-007** Normalisation into the canonical store | Validated engine: ingestion and store | `src/ingestion/build.py`, `src/database/store.py`, `schema.sql` | T01, T02, T06 (fuel rule) | Final audit A | REQ-DATA-001 to REQ-DATA-004, REQ-DATA-007 | Implemented |
| **FR-008** Vintage handling | Operational pipeline: release reconstruction | `src/ops/bls.py`, `scripts/build_bls_vintages.py`, `src/preprocessing/labels.py` | LR-T01 to LR-T05, T04, OP-T4 | Final audit L2 | REQ-ML-001, REQ-OPS-005 | Implemented |
| **FR-009** Data quality and freshness status | Observability: source registry | `src/validation`, `src/observability/registry.py` | T03, PR-T02, PR-T03, OP-T7 | Final audit P | REQ-DATA-005, REQ-OPS-009, REQ-PROD-002 | Implemented |
| **FR-010** Label construction | Validated engine: labels | `src/preprocessing/labels.py` | T05, LR-T06 | Final audit A | REQ-ML-002 to REQ-ML-004 | Implemented |
| **FR-011** Feature construction as of issuance | Validated engine: features | `src/features/build.py` | T06 | Final audit A1 to A7; validator: leakage | REQ-ML-005, REQ-DATA-007 | Implemented |
| **FR-012** Forecast generation | Validated engine: forecasters | `src/forecasting/baselines.py`, `models.py` | T07, T08 | Final audit C | REQ-ML-007, REQ-ML-008, REQ-ML-010 | Implemented |
| **FR-013** Walk-forward evaluation and metrics | Validated engine: evaluation | `src/api/backtest.py`, `src/evaluation/metrics.py` | T09, T10, T11 | Final audit C, D | REQ-ML-006, REQ-ML-009, REQ-ML-011 to REQ-ML-014 | Implemented |
| **FR-014** Selection of the official forecaster by rule | Operational pipeline: selection | `src/ops/selection.py` | PR-T12 | Final audit P | REQ-PROD-006 | Implemented |
| **FR-015** Operational forecast issuance | Operational pipeline: issuance | `src/ops/pipeline.py` | OP-T5, PB-T07 | From-zero rehearsal, phases A and B | REQ-OPS-006, REQ-OPS-007, REQ-PROD-007 | Implemented |
| **FR-016** Forecast ledger | Observability: records | `src/observability/records.py`, `src/ops/pipeline.py` | OP-T1, OP-T6, PR-T13 | Hosted rehearsal, phase E | REQ-FN-001, REQ-FN-002, REQ-OPS-006 | Implemented |
| **FR-017** Outcome recording and historical forecast record | Operational pipeline: outcomes | `src/ops/pipeline.py`; `airpulse-web/scripts/export_data.py` | OP-T6; application tests (production) | Final audit D | REQ-OPS-008, REQ-FN-005 | Implemented |
| **FR-018** Replay of a past forecast | Validated engine: replay | `src/api/backtest.py`, `src/cli.py`; `airpulse-web/src/pages/Replay.jsx` | T12, DB-T3 | Final audit E | REQ-FN-003, REQ-REPLAY-001, REQ-REPLAY-002 | Implemented |
| **FR-019** Failure handling | Operational pipeline: orchestrator | `scripts/production_run.py`, `src/ops/adapters.py` | PR-T05, PR-T06, PR-T15, OP-T8 | From-zero rehearsal, phase C; hosted rehearsal, phase D | REQ-PROD-003, REQ-OPS-002 | Implemented |
| **FR-020** Run record and production gate | Operational pipeline: gate | `scripts/production_run.py`, `src/observability/records.py` | PB-T05, DP-T03 | Hosted rehearsal, phase E | REQ-PUB-004, REQ-HOST-003 | Implemented |
| **FR-021** Source transparency and feature gate | Observability: production policy | `src/observability/policy.py` | PB-T01, PB-T02, PB-T03, LR-T07 | Final audit Q, L4 | REQ-PUB-001, REQ-PUB-002 | Implemented |
| **FR-022** Production export under a data contract | Publication: export | `airpulse-web/scripts/export_data.py`, `guards.py` | Application tests (data-contract, production, expansion); DP-T08 | From-zero rehearsal, phase B | REQ-PROD-011, REQ-HOST-005 | Implemented |
| **FR-023** Website rendering | Publication: application | `airpulse-web/src` | Application tests (47); DP-T09 | Hosted rehearsal, phase B (served like Pages) | REQ-HOST-006 | Implemented |
| **FR-024** Scenario calculator | Publication: application | `airpulse-web/src/pages/Estimate.jsx`, `src/lib` | Application tests (scenario) | Application tests | Policy feature `scenario_calculator` (no baseline requirement) | Implemented |
| **FR-025** Deployment gating | Publication: deployment checks | `scripts/deployment_checks.py`, `.github/workflows/production.yml` | DP-T02, DP-T03, DP-T08, LR-T08 | Hosted rehearsal, phase B; final audit G2, L4 | REQ-HOST-002, REQ-HOST-003, REQ-HOST-005 | Implemented |
| **FR-026** Reproduction from the files held | Validated engine: command line | `src/cli.py`, `scripts/check_benchmark_ledger.py` | T15, T19 to T22, PB-T06, LR-T05 | Clean-clone run; deterministic rerun | REQ-REP-001, REQ-REP-003, REQ-FN-004, REQ-PUB-005 | Implemented |

## 3. Non-functional requirements

| Requirement | Design component | Source / module | Tests | Validation evidence | Baseline | Status |
|---|---|---|---|---|---|---|
| **NFR-001** Correctness of information timing | Engine: as-of store, features | `src/database/store.py`, `src/features/build.py` | T06, T11, PB-T07 | Validator: leakage; final audit A | REQ-ML-005, REQ-ML-006 | Verified |
| **NFR-002** Reproducibility | Engine: command line | `requirements.txt`, `src/cli.py` | T16 | Clean-clone run on Linux; validator: reproducibility | REQ-REP-002, REQ-REP-003 | Verified |
| **NFR-003** Determinism | Engine: evaluation | `src/api/backtest.py`, `scripts/check_benchmark_ledger.py` | T15, T19 to T22 | Deterministic rerun; tolerance study | REQ-REP-001 | Verified |
| **NFR-004** Maintainability | Layered packages | `src/config.py` | T17 | Validator: phase contamination | REQ-MNT-001, REQ-MNT-002 | Verified |
| **NFR-005** Portability | Engine; workflows | `scripts/clean_runner_check.sh` | T20 | Clean-clone run; Linux check of the hosted folder | REQ-PROD-012 | Verified |
| **NFR-006** Reliability of the unattended run | Operational pipeline: orchestrator | `scripts/production_run.py` | PR-T15, OP-T8 | From-zero rehearsal, phase C | REQ-PROD-008, REQ-REL-001 | Verified |
| **NFR-007** Data integrity | Observability: records | `src/observability/records.py`, `src/ingestion/loaders.py` | OP-T1, T01 | Hosted rehearsal, phase E | REQ-DATA-006, REQ-OPS-001 | Verified |
| **NFR-008** Security | Workflows; deployment checks | `.github/workflows`, `scripts/deployment_checks.py` | DP-T04, DP-T05, DP-T08 | Pre-push audit; final audit G3 | REQ-SEC-001, REQ-HOST-004 | Verified |
| **NFR-009** Privacy | Publication: application | `airpulse-web/src/lib/data.js` | Application tests (production) | Private-data scan of the hosted folder and of the built site | REQ-SEC-001 | Verified by inspection and scan |
| **NFR-010** Licensing compliance | Production policy; deployment checks | `src/observability/policy.py`, `scripts/deployment_checks.py` | LR-T07, LR-T08, LR-T09, DP-T06, DP-T07 | Restricted-source scan; final audit L | REQ-PUB-001, REQ-PUB-002 | Verified; one confirmation open (EIA) |
| **NFR-011** Performance | Engine: evaluation | `src/api/backtest.py` | T18 | Clean-clone run (timed steps) | REQ-PERF-001 | Verified |
| **NFR-012** Accessibility | Publication: application | `airpulse-web/src/pages`, `src/styles` | None automated | Inspection of the sources; no audit against a standard was performed | No baseline requirement (engineering decision) | Implemented; not independently audited |
| **NFR-013** Responsive user interface | Publication: application | `airpulse-web/src/styles` | None automated | Inspection during development; no device matrix was tested | No baseline requirement (engineering decision) | Implemented; not systematically tested |
| **NFR-014** Observability | Observability | `src/observability`, `scripts/production_report.py` | PR-T17, PB-T05 | Final audit P, Q | REQ-OBS-001, REQ-PUB-004, REQ-PROD-010 | Verified |
| **NFR-015** Auditability | Governance records | `traceability/`, `execution/change_log.md` | PR-T18 | Validators: requirements, traceability; final audit E, L1 | REQ-DOC-001 | Verified |
| **NFR-016** Failure isolation | Operational pipeline: layers as processes | `scripts/production_run.py`, `src/aviation` | PR-T06, PR-T10, OP-T10 | Hosted rehearsal, phase D | REQ-OPS-011, REQ-PROD-005 | Verified |

## 4. Coverage

- Requirements: 26 functional, 16 non-functional. Every one has a design component, a module and validation evidence. Two (NFR-012 accessibility, NFR-013 responsive interface) have no automated test; their status says so.
- Components of the design without a requirement of their own: none. The research-only packages (`src/v2`, `src/v3`, `src/news`, `src/aviation/experiment.py`, `src/dashboard` as a research tool) carry no requirement of the product; they are documented in section 3.3 of the specification. Of them, `src/v2`, `src/v3` and `src/aviation/experiment.py` are not in the hosted repository; `src/news` and `src/dashboard` are present there as code the pipeline imports, the event layer with its sources switched off and nothing of its data or output shipped.
- Baseline requirements not consolidated into this specification are those of the research layers (families NEWS, NEWSVAL, EXP, GLB, WKL, AVOPS, AVDATA, DASH): they remain in the baseline with their own tests and are research only.

## 5. Maintenance

A change of a requirement, a module or a test changes one row. A requirement added to the specification gets a row before its implementation is merged; a row without a test is given a qualified status, never left blank.
