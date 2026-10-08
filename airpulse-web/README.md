# AirPulse Operations

The customer-facing application of AirPulse: an air-freight market intelligence product for logistics professionals,
forwarders, procurement and supply-chain teams.

It is one of two interfaces on one engine.

```
                    AIRPULSE ENGINE  (../AirPlus: data, forecasting, validation)
                         |
             +-----------+-----------+
             |                       |
     AIRPULSE OPERATIONS       CONTROL CENTER
     this folder (React)       ../AirPlus/src/dashboard (Streamlit)
     read the market           compare models, scores, data health, validation
```

The engine in `../AirPlus` is not modified by anything here. This application lays out what the engine has stored; it
computes no forecast and adds no numbers of its own.

## What the customer sees

- **One AirPulse outlook.** Rising, stable or falling for the month ahead, with its outlook probability. Never a choice
  between models. The export script takes the approach the engine's own walk-forward evaluation supports on the
  validated target (today: the seasonal record) and exports only that one. If the evaluation does not single out one
  approach, the export stops instead of choosing.
- **A market level that is not a price.** The BLS Asia → US air-freight price index is shown as an index level, with its
  movement, and is never given a currency symbol.
- **No invented shipment price.** AirPulse has no lane-rate data, so `/estimate` says that route-level estimation is not
  available. It offers a scenario calculator instead: the user's own rate × (1 + the user's own movement), labelled as a
  scenario and not as a forecast.
- **A weekly fuel-cost outlook, named as that.** No public weekly air-freight rate series may be used, so there is no
  weekly freight forecast. `/market/weekly` is an outlook for the weekly average jet fuel price, exported only because it
  passed the rule set for it before it was tested. It says on the page that it is not a freight-price forecast.
- **A carry-forward, named as that.** A second test asked whether anything forecasts next week's fuel price better than
  assuming it stays where it was last published. Nothing did. The weekly page therefore says, above the outlook, that it
  is a carry-forward of the latest published price and not a prediction of the price, and shows the test.
- **Air traffic, as counts.** `/operations` shows flights counted by two official sources whose terms allow it: every flight
  of each day at Hong Kong International Airport, and the monthly nonstop departures between US and foreign airports (marked
  as a historical record). No expected level, no reading of what is unusual, no capacity figure and no statement about
  prices: none of those passed the production gate. A day or month a source did not cover is absent, never zero.
- **Only what passes the production gate.** The engine's policy (`../AirPlus/config/production_sources.yaml`) says which
  sources may be published (terms read at the publisher, with the sentence each class rests on) and which features are in
  the product. The export refuses everything else and checks the files it wrote. The event layer, European airport
  counts, the anomaly reading and results of experiments are not in the product; the Methodology lists them with the reason.
- **A source that needs attention is named.** When a production source has failed or is stale, the top bar, the overview
  and both outlook pages say which one, and that what is shown may be out of date.
- **The evidence, in plain words.** The monthly outlook page shows what was tested to replace the seasonal record
  (71 alternatives, 8 groups of new data), that none met the rule, and how well each probability has held.
- **A public market proxy.** The target is one US lane. It is not a carrier quote and not a South Asia → Europe rate.
  This is stated in the navigation, on the market pages, in the footer and in the methodology.

## Run

```bash
npm install
npm run dev
```

Opens on http://localhost:5183 (set `PORT` to use another port). `npm run build` writes the static site to `dist/`.

## Refresh the data

```bash
npm run export
```

This runs `scripts/export_data.py` with the engine's interpreter (found by `scripts/run-python.mjs`, on Windows and POSIX).
It opens the engine's stores read-only and writes `public/data/`. A forecast that is not a valid probability distribution
is refused (`scripts/guards.py`) and nothing is exported.

One command for the whole chain, engine to site:

```bash
npm run refresh
```

```bash
npm run refresh:offline
```

`refresh` is the whole chain in eight steps: 1 source health, 2 ingestion of what is due, 3 validation, 4 features,
5 forecast, 6 source registry and run record (steps 1 to 6 are the engine's unattended production run,
`scripts/production_run.py` in its repository: the command its scheduled workflow runs), 7 export, 8 web tests. It then
prints a report:

| Column or line | Meaning |
|---|---|
| SOURCE, LATEST DATA, LAST FETCH | every production source, the newest value it holds, the last successful fetch |
| EXPECTED UPDATE | how often a new value is expected and after how many days the source counts as stale |
| STALE? | `no`, `YES` or `FAILED` |
| MONTHLY FORECAST UPDATED? / WEEKLY FUEL UPDATED? | whether this run put a new outlook on record, and which one is on record |
| EXPORT UPDATED? | whether the files of the site changed, with the export version and the engine commit |
| WARNINGS | every failed step, every source that is not healthy, a weekly outlook whose week has passed |

A failed source does not stop the report and does not produce a fresh-looking site: the export still runs, so the pages
name the source that failed. A failed validation gate of the engine does stop it: nothing is exported. Exit code
0 = nothing to warn about, 2 = exported with warnings, 1 = the gate or the export failed and the site keeps its previous
data. `refresh:offline` skips the fetch. Running it twice on unchanged sources gives the same content
(`core.export.content_hash`).

**Where the numbers come from.** Everything observed (index history, fuel prices, outcomes) is read from the engine's
operational store, which its scheduled run updates; outlooks issued since the evaluated record are appended from its
ledger; the evaluated record itself comes from the frozen benchmark store. The state of every source comes from the
engine's source registry and is worked out again in the browser against the present, so an old export cannot look fresh.
No count, date or state is typed into a page (two tests keep it that way). Contract of every value:
`../AirPlus/docs/PRODUCTION_DATA_CONTRACT.md`.

**All or nothing.** The export writes to `public/data.staging`, checks the result, and only then moves the files into
`public/data`. If anything fails, the site keeps what it had, and after `core.export.stale_after_days` every page says
Data delay.

**Publication without a person.** One repository is hosted: the engine at its root and this application in `airpulse-web/`.
Its single workflow (`.github/workflows/production.yml` there; kept in the engine as `deploy/public/production.yml`) runs
the engine's production run, commits the operational state, exports, runs these tests, builds and deploys to GitHub Pages:
daily, weekly and monthly, and when started by hand. It needs no variable and no secret; the path the site is served under
is read from the Pages settings (`VITE_BASE`). The browser receives static files only and no key. Until a run started by
GitHub's scheduler is on record, a run started by a person is recorded as manual and the application says Snapshot.
Step by step: `docs/HOSTING_STEP_BY_STEP.md` of the engine.

| File | Holds |
|---|---|
| `core.json` | lanes, fuel prices, data state, the registry of sources with their terms, the newest run record, what is not in the product and why |
| `outlook.json` | the one official forecast for every month, its record, how its probabilities have held, and what it rests on |
| `market/<lane>.json` | the published index of each of the eight lanes |
| `replay.json` | what was known at each issuance date |
| `weekly.json` | the weekly fuel-cost outlook, its record and the state of its source |
| `aviation.json` | counts of flights: Hong Kong airport by day, US routes by month, each source with its terms, attribution and state |

**No licence switch.** The public product is always held to the commercial standard: a source whose terms are unknown,
non-commercial or research-only is never exported, whatever the environment. The application never calls a data
provider; it reads these files only.

`core.json` also carries, for every source: status, newest value, expected frequency, last successful fetch, checksum,
check result and the number of days after which it counts as stale; and the export version with the dataset versions.

## Test

```bash
npm test
```

46 tests on Node's built-in runner, no extra dependency: the scenario arithmetic, the display derivations, a data
contract that fails if a second forecast, a technical score, an engine label or an invented number reaches the customer
data or the source, the expansion checks (every weekly forecast is a valid distribution issued before its outcome, the
weekly page says it is not a freight forecast, every source carries its quality fields, a stale source is shown as
stale, the export refuses an invalid forecast), and the checks of the third pass: the weekly page calls the outlook a
carry-forward when its test found no skill, a source that needs attention is named wherever an outlook is shown, and
the refresh report lists every production source and turns a failed one into a warning, and the
second pass is shown as measured (what met the rule, what is only being watched). The air-traffic tests fail if an
airport without data is shown as zero, if data that has aged could still be called recent, if a flight count is presented
as cargo capacity, a cause or a price signal, if a page calls a provider, or if the non-commercial source survives a
commercial export.

## Routes

| Route | Its one job | Character |
|---|---|---|
| `/` | Introduce AirPulse and lead into the product | cinematic |
| `/dashboard` | What should I know right now? | morning briefing |
| `/market` | How is the market behaving? | research terminal |
| `/market/forecast` | Monthly outlook: where is the monthly market direction heading, and why this approach? | analytical workspace |
| `/market/weekly` | Weekly fuel-cost outlook: what is the cost of jet fuel doing this week? Not a freight price | weekly bulletin |
| `/market/trends` | The market over time: level, changes, seasonality | data visualisation |
| `/market/history` | Highs, lows, turning points, year by year | record |
| `/market/fuel` | Jet fuel and crude oil, as published | research note |
| `/operations` | Flights counted at Hong Kong and on routes between Asia and the United States | operations record |
| `/operations/route/<IATA>-<IATA>` | One route by month, as the publisher counts it; a historical record | route sheet |
| `/routes` | What is covered, lane by lane | logistics board |
| `/replay` | What did AirPulse know at that time? | forensic reconstruction |
| `/estimate` | Shipment estimation: what exists, what does not, a scenario calculator | decision tool |
| `/methodology` | Target, data, forecast, validation, limits, roadmap | documentation |
| `/data` | Data mode, sources, freshness, limitations | observability |

`/market?lane=<id>` shows a tracked index without an outlook.

## Layout of the code

```
scripts/export_data.py      adapter, engine side: stores -> public/data
scripts/guards.py           a forecast must be a valid distribution before it is exported
scripts/refresh.py          engine steps -> export -> report of every source, in one command
scripts/run-python.mjs      finds the engine's interpreter (Windows and POSIX)
scripts/spa-fallback.mjs    after the build: 404.html = the application, so a reload of any route loads it
scripts/optimize_images.py  WebP copies of the photographs in two widths -> public/img
src/lib/data.js             adapter, browser side: load the JSON once
src/lib/derive.js           arithmetic and counting for display (no forecasting)
src/lib/scenario.js         the scenario calculator
src/lib/format.js           formats and customer wording
src/components/             shell (navigation, footer), shared pieces, SVG charts
src/pages/                  one file per route
src/styles/                 design system and page layouts
tests/                      node --test
```

No chart library and no UI kit: the charts are plain SVG. Dependencies are React, React Router and three font packages.

## Why this folder sits beside the repository

`AirPlus/scripts/validate_artifacts.py` requires every file inside the repository to be registered. Keeping the web
application (and `node_modules`) outside it leaves the validated repository and its audits unchanged.
