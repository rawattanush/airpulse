# AirPulse

Air-freight market intelligence: a monthly direction outlook for the US import air-freight price index from Asia
(Bureau of Labor Statistics), with its full record, and the public data around it.

This repository is the whole product. It holds the engine, the customer application and one workflow. GitHub's own
machines fetch the data, validate them, issue an outlook when one is due, record it, build the site and publish it on
GitHub Pages. No other machine and no other service takes part.

```
sources ──> scripts/production_run.py ──> operations/ (state, committed) ──> airpulse-web/scripts/export_data.py
        fetch · validate · forecast            ledgers · run records              airpulse-web/public/data (generated)
        when due · registry · gate             vintage files · flight lists              │
                                                                                         v
                                               GitHub Pages  <── deploy <── build <── tests and checks
```

## Status

Built and verified on fresh clones, and released for publication. One licence point is open and accepted by the owner:
the fuel prices are published under the Energy Information Administration's general reuse statement, without a
confirmation for its spot price tables, and are removed if the publisher objects (see `docs/DATA_AND_LICENSING.md`,
section 2.2). Publishing steps: [docs/GITHUB_PUSH_GUIDE.md](docs/GITHUB_PUSH_GUIDE.md).

## What it forecasts, and what it does not

**Forecasts:** the direction (rising, stable or falling; a band of ±0.5 per cent) of the monthly BLS import air-freight
price index for Asia, series IC1312, one month at a time, issued on the day the previous month is first published. The
official forecaster is a seasonal baseline, selected by a recorded rule; its record is 67 correct directions in 122 months.

**Does not forecast:** a commercial freight rate, a lane rate per kilogram, a shipment quote, or anything at a horizon
of days or weeks. The index is a benchmark, not a price.

## What the site shows

| In the product | From |
|---|---|
| Air-freight price index by lane, as published | US Bureau of Labor Statistics, read at the Bureau (archived releases and public data interface) |
| Monthly outlook (rise, fall or little change), its record since 2016, how its probabilities have held, replay | the engine's walk-forward evaluation and the ledger of issued outlooks |
| Jet fuel and crude oil prices | US Energy Information Administration, read at the Administration (published on the owner's decision, without the publisher's confirmation: see `NOTICE.md`) |
| Flights at Hong Kong International Airport, cargo flights apart | the airport's flight information (data.gov.hk) |
| Monthly departures on US international routes (a historical record) | US Department of Transportation |
| News-adjusted view of the outlook (a trial; in testing it did not improve on the official outlook) | a model trained on past months, applied to events reported by two trade publications; summaries and links only, no article text |
| Shipment scenario calculator | arithmetic on a rate the visitor enters; no price is invented |
| State of every source and of the last run | computed from the run records |

What is **not** in the product, and why, is listed on the site's Methodology page from `config/production_sources.yaml`:
anything whose licence is unknown or forbids the use, and anything that did not pass its validation, is left out, not
relabelled.

## How it runs

`.github/workflows/production.yml`, three schedules (UTC) and a manual start:

| When | What |
|---|---|
| daily 07:11 | whatever is due; Hong Kong flight lists; the US route file when its publisher changed it |
| Monday 08:23 | fuel prices and the air-traffic files are asked whether due or not |
| the 23rd 09:31 | after the release window of the index: the release is asked once more; the outlook of the newest month due must be on the ledger |

A run asks only the sources that are due. An outlook is issued once per month, when the release it needs is on file; a
run that finds nothing new changes no data file, issues nothing and produces the same export.

A run does **not** publish when the validation gate fails, a test fails, a hash chain is broken, the export fails its
contract or holds a field of a removed feature, or a secret or a development address is found in the files to be
published. GitHub Pages then keeps serving the site it had. A source that is late or failed does not stop the
publication: the site is deployed and names that source on its Data page, and the run is marked failed so that GitHub
notifies the owner.

`.github/workflows/ci.yml` runs on every change of the code: the benchmark is rebuilt and compared with the validated
ledger, then the engine's tests, the export, the application's tests, the build and the checks. It publishes nothing.

## Where things are

```
src/                      the engine (identical to the research commit named in PUBLIC_REPOSITORY.json)
scripts/                  production_run.py (the unattended run), production_report.py, deployment_checks.py,
                          check_benchmark_ledger.py, run_workflow_locally.py, serve_like_pages.py
config/                   sources.yaml (what is fetched and how often), production_sources.yaml (licences; what may be shown)
operations/               the state: ledgers and run records (append-only, hash-chained), vintage files, flight lists
research/data_samples/    the frozen snapshot the evaluation rests on (ten public series with their checksums)
evaluation/               the validated ledger and the stored results the site shows
airpulse-web/             the customer application (React, Vite); its data are generated, never committed
tests/                    tests that hold in this repository
docs/                     SRS.md and SRS.pdf (specification), SYSTEM_DESIGN.md, REQUIREMENTS_TRACEABILITY.md,
                          VERIFICATION_AND_VALIDATION.md, DATA_AND_LICENSING.md, USER_GUIDE.md, OPERATIONS.md, diagrams/;
                          the data contract, the hosting audit, the step-by-step guide
```

## Running it yourself

Nothing has to be run by hand. If you want to (Python 3.12, Node 22):

```
python -m pip install -r requirements.txt
python -m src.cli build-db && python -m src.cli backtest     # the evaluation, from the frozen snapshot (about 2 min)
python scripts/check_benchmark_ledger.py                     # the ledger equals the validated one
python scripts/production_run.py --plan                      # what is due, and why; nothing is fetched
python scripts/production_run.py                             # the run the workflow starts
python -m pytest tests                                       # the tests that hold in this repository
cd airpulse-web && npm ci && npm run export && npm test && npm run build
```

## Documentation

| Document | Content |
|---|---|
| [docs/SRS.md](docs/SRS.md), [docs/SRS.pdf](docs/SRS.pdf) | Software requirements specification, with diagrams |
| [docs/SYSTEM_DESIGN.md](docs/SYSTEM_DESIGN.md) | Architecture and its reasons |
| [docs/REQUIREMENTS_TRACEABILITY.md](docs/REQUIREMENTS_TRACEABILITY.md) | Requirement to module, test and evidence |
| [docs/VERIFICATION_AND_VALIDATION.md](docs/VERIFICATION_AND_VALIDATION.md) | What was checked and what it proves |
| [docs/DATA_AND_LICENSING.md](docs/DATA_AND_LICENSING.md), [NOTICE.md](NOTICE.md) | Every source and its licence status |
| [docs/USER_GUIDE.md](docs/USER_GUIDE.md) | The website, page by page |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | The production run, failures, recovery |
| [docs/GITHUB_PUSH_GUIDE.md](docs/GITHUB_PUSH_GUIDE.md) | Publishing this repository |

## What this is not

Not a freight rate, not a quotation and not advice. The outlook is a direction for a public price index; its record,
including every month it was wrong, is on the site. The research behind it (protocols, experiments that failed, sources
that could not be used) is kept in a separate research repository and is not needed to run the product.

Data sources and their terms: [NOTICE.md](NOTICE.md).
