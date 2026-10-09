# AirPulse: User Guide

Version 1.2, 2026-10-09. This guide describes the website as it is built. Every page below was opened in the production build of the site, served the way the static host serves it, and the description was written from what the page showed. Figures quoted as examples are those of the data exported on 7 October 2026 and will differ later.

## 1. Before you start

AirPulse publishes **one outlook a month**: whether the official price index for air freight from Asia to the United States (U.S. Bureau of Labor Statistics, series IC1312) is more likely to be **Rising**, **Stable** or **Falling**. Around it the site shows the published index, fuel prices and official counts of flights, each with its source and date.

- **An index is not a quote.** The site repeats this next to every index figure. AirPulse provides no shipment quote, no rate per kilogram and no forecast of a commercial lane rate.
- **Rising, Stable, Falling.** A change of more than +0.5 per cent against the previous month is Rising, of more than −0.5 per cent Falling, anything between is Stable.
- **Monthly and late.** The index of a month is first published in the middle of the next month and revised in the three following releases. Pages mark a figure as *First release* or *Final*.
- **Snapshot.** The foot of each page states the time of the last data refresh and how far the index and the fuel prices reach.

Navigation: **Overview**, **Market** (Market, Monthly outlook, News-adjusted, Trends, History, Fuel prices), **Operations** (Air traffic, Lanes, Replay, Estimate), **Research** (Methodology, Data). On a narrow screen the navigation is behind a Menu button.

## 2. Routes

| Address | Page | In the navigation |
|---|---|---|
| `/` | Home | entry page |
| `/dashboard` | Overview | yes |
| `/market` | Market | yes |
| `/market/forecast` | Monthly outlook | yes |
| `/market/trends` | Trends | yes |
| `/market/history` | History | yes |
| `/market/fuel` | Fuel prices | yes |
| `/market/news` | News-adjusted outlook (a trial) | yes |
| `/market/weekly` | Weekly fuel-cost outlook (not offered) | linked from Fuel prices |
| `/operations` | Air traffic | yes |
| `/operations/route/<pair>` | One route, for example `HKG-ANC` | from the route table |
| `/routes` | Lanes | yes |
| `/replay` | Replay | yes |
| `/estimate` | Estimate | yes |
| `/methodology` | Methodology | yes |
| `/data` | Data | yes |
| any other address | "Page not found", with links to the four sections | |

Four old addresses redirect: `/forecast`, `/history`, `/intelligence/drivers` (to Fuel prices) and `/data-health` (to Data).

## 3. Home (`/`)

- **Purpose.** To say what AirPulse is and is not.
- **What you see.** A headline; three steps under "How it works" (it reads what is published, it states one outlook, it keeps the record); two statements, "What AirPulse tells you" (the direction of the monthly BLS Asia to U.S. index, a public proxy) and "What it does not" (carrier quotes, route-level prices per kilogram, South Asia to Europe rates).
- **Controls.** Links: How it works, Methodology, Open AirPulse, Explore AirPulse, Data.
- **Limitations.** No figure on this page is data.

## 4. Overview (`/dashboard`)

- **Purpose.** The current outlook and what changed, on one screen.
- **What you see.**
  - The outlook for the named month with its issuance date: one word (for example STABLE), a sentence saying what it means, and a note when two directions carry the same probability ("read this as a close call").
  - The three probabilities; the forecast period; the date the outcome will be published; the historical record ("55% correct of 122 months by direction").
  - A chart of the index over the last three years, labelled "index level, not a freight quote".
  - **What changed?** The latest movement of the index (level, change on the month and on the year, whether it is a first release) and the latest movement of jet fuel.
  - **Why?** The seasonal count behind the outlook, for example "in the 16 Septembers from 2010 to 2025, the index rose in 6, was stable in 6 and fell in 4".
  - "Around the market": a one-line summary, stated to be context and not inputs of the outlook.
- **Controls.** Links to Market, Fuel prices, the forecast, Air traffic, Replay, Data state.
- **Interpretation.** The probabilities come from counting earlier years of the same calendar month. When two are equal, a fixed rule names one; treat it as an even call.
- **Source.** BLS (index); EIA (fuel).
- **Limitations.** The outlook is a calendar rule and knows nothing of this month's events.

## 5. Market

### 5.1 Market (`/market`)

- **Purpose.** Where the Asia to U.S. index stands.
- **What you see.** The movement of the latest published month (Rising, Stable or Falling, with the percentage); the index level; whether the figure is a first release and when it was published; the current outlook in one line; change over three months and over a year; the historical high; the length of the current run; a chart of the index level; "What this means" in plain sentences; the outlook; the seasonality of the month; fuel context; and a month-by-month table (level, change, movement, first release or final, date first published).
- **Controls.** Chart range: 2Y, 5Y, 10Y, All. A "What is an index?" explanation. Links to Forecast, Trends, History, Fuel.
- **Interpretation.** Index points, not money. "34% below its record high" compares levels of the index. A first release can be revised, and a revision can change the direction.
- **Limitations.** This page shows the validated lane only. The seven other indexes are on the Lanes page. A month the publisher did not publish (October 2025) is shown as missing.

### 5.2 Monthly outlook (`/market/forecast`)

- **Purpose.** The outlook in full, and its whole record.
- **What you see.**
  - The outlook, its three probabilities, forecast period, issuance date, date the outcome is published, status (Pending until scored), and a line stating when it was generated and whether the run was started by a person or a schedule.
  - How often earlier outlooks of the same direction were correct.
  - **How this outlook is formed**: the seasonal count.
  - **Its record**: "67 of 122 months correct", checked against the final published figure, with the remark that picking one of three directions at random would be right about a third of the time; a table by period.
  - **How far to trust the probabilities**: for each direction, the probability given on average and how often it happened. The page says plainly where the probabilities are too high (for Stable).
  - **Forecast history**: the probabilities issued for every month since January 2016 with the result under each; how often each direction was called and how often it was correct.
  - **Forecast against outcome**: a table per month with issuance date, outlook, probability, first release, final figure and result (Correct, Missed, Pending).
  - **Information available at issuance** and the market signals at that date.
- **Controls.** Year selector for the table; "Show all 126 months"; links to the record by direction, Methodology, Data state.
- **Interpretation.** A forecast is Correct when its direction equals the direction of the final figure. Four of the 126 outlooks still await a final figure.
- **Limitations.** One month ahead only. No size of move is forecast. Months without an outlook (October and November 2025, January 2026) are absent because the publisher's release pattern did not allow one to be issued before its outcome.

### 5.2a News-adjusted outlook (`/market/news`)

- **Purpose.** To show how recent news would shift the outlook, as a trial. It is not the AirPulse outlook.
- **What you see.** A statement at the top that this is a trial and how it did in testing. The official outlook and the version with recent news side by side, each with its three probabilities. **The shift**: the probability points news adds to or takes from each direction. **Which news moves it**: for each of six kinds of news (disruption at sea, reported air-freight rates, cargo demand, air cargo capacity, geopolitical events, airspace disruption) its level now, its usual level and what it contributes. **What the press reported**: one line per reported event of the last 30 days (date, kind of event, places and organisations named, whether it presses prices up or down, and a link to the article). **How it did in testing**: months, months correct and how sure each version was, and a month-by-month table.
- **Controls.** "Show all months" on the test table. Each source name opens the article at its publisher.
- **Interpretation.** Read the direction of the shift, not its size. In testing the version with news was right about as often as the seasonal outlook (33 of 63 months against 32) and was much more sure of itself than that justified.
- **Data source.** Two trade publications, read once a day. The text of an article or of its title is not shown and not kept; only what kind of event it reported.
- **Limitations.** The reading of articles is done by fixed rules that miss many events and sometimes misread one. The model was trained on past months and has not shown that news improves the outlook. The official outlook never changes with news.

### 5.3 Trends (`/market/trends`)

- **Purpose.** The index over time and the seasonal pattern the outlook rests on.
- **What you see.** The index level since January 2006 with local highs and lows marked; the change year over year; the change month over month; a grid of every month since 2006 coloured Rising, Stable or Falling; how often each calendar month rose; a table of four periods (start and end level, average month, largest rise and fall, months by direction).
- **Controls.** Links to History, Forecast, Fuel prices.
- **Interpretation.** The seasonal shares are descriptive. November rose most often, January and February least.
- **Limitations.** The pattern differs between periods, as the table shows.

### 5.4 History (`/market/history`)

- **Purpose.** How the index has behaved: extremes and turning points.
- **What you see.** "The marks of the record" (record high and low, largest monthly rise and fall, longest rising and falling runs, the month without a figure); a table of turning points; a year-by-year table with year-end level, change over the year, months by direction and how many outlooks were correct in that year.
- **Interpretation.** A turning point is the highest or lowest month within eighteen months on either side.
- **Limitations.** This page is about the index. The full record of the outlook is on the Monthly outlook page.

### 5.5 Fuel prices (`/market/fuel`)

- **Purpose.** Context: published prices of jet fuel and crude oil.
- **What you see.** U.S. Gulf Coast jet fuel in dollars per gallon and Brent crude in dollars per barrel, with the monthly average and its changes over one month, three months and a year, and the date of the latest value.
- **Controls.** Range: Since 2005, Last two years. Links to the weekly page and to Sources.
- **Source.** U.S. Energy Information Administration.
- **Limitations.** Spot prices of a commodity, not a carrier's fuel surcharge. Published weekly. **Fuel is not an input of the monthly outlook.** The prices are published under the publisher's general reuse statement; the publisher was not asked to confirm it for these tables, and they are removed if it objects.

### 5.6 Weekly fuel-cost outlook (`/market/weekly`)

Not offered. The page states the reason: the dated weekly data it was built on are held only by a service whose terms forbid keeping them and building models on them. It links back to the Monthly outlook.

## 6. Operations

### 6.1 Air traffic (`/operations`)

- **Purpose.** Official counts of flights, shown as published.
- **What you see.**
  - A statement of what the page is: counts, with no estimate of cargo capacity, no expected level and no statement about prices.
  - The state and the newest date of the two sources.
  - **Hong Kong International Airport**: movements of the newest day with arrivals and departures, cargo flights, passenger flights, cancelled flights; a chart over the archived days; the first stop of cargo departures in the last 28 days against the 28 days before.
  - **Routes between Asia and the United States**: the 30 routes with the most nonstop departures in the newest twelve months, with the share flown by all-cargo airlines and the newest month.
- **Controls.** Chart switch: All movements, Cargo flights. Each route opens its own page.
- **Source.** Airport Authority Hong Kong via DATA.GOV.HK; U.S. Department of Transportation.
- **Limitations.** Flights, not tonnes. The Hong Kong archive starts on the first day this system archived (about 90 days); a day not archived is absent, not zero. The U.S. route counts are published months late: a historical record.

### 6.2 Route page (`/operations/route/<pair>`)

Departures of one airport pair, both directions together: the newest month, the newest twelve months, the share by all-cargo airlines and a chart by month. A month the publisher did not list is a gap. Links back to all routes.

### 6.3 Lanes (`/routes`)

- **Purpose.** What AirPulse covers, lane by lane.
- **What you see.** A map of four regions; the one lane with an outlook (Asia to United States) with its level, latest month and links to Market and Forecast; a table of seven **tracked indices** with level, latest month, a five-year sparkline and the label "index only"; and a section "Not covered": South Asia to Europe, any airport-to-airport route, and differences between carriers and services.
- **Limitations.** No outlook is issued for the seven tracked indices. No route has a rate.

### 6.4 Replay (`/replay`)

- **Purpose.** To show what was known when a past outlook was issued.
- **What you see.** For the chosen month: issuance date, month of the outlook, date the outcome was first published; the published figures available on the issuance date with the date each was published; market signals at that date; the outlook issued; the outcome.
- **Controls.** A month selector from January 2016 with previous and next arrows.
- **Limitations.** Covers the months that have an outlook.

### 6.5 Estimate (`/estimate`)

- **Purpose.** To say what AirPulse can and cannot tell about the cost of a shipment, and to offer a calculator for a scenario of your own.
- **Inputs.** Origin; destination; chargeable weight in kilograms; currency (USD, EUR, INR, GBP: a label only, nothing is converted); your current known rate per kilogram.
- **What you see.** "Route-level estimation: not yet available for this route", with the reason (it needs historical lane rates, which AirPulse does not have) and the statement that showing a rate would be inventing it.
- **Scenario calculator.** Choose a movement (−10, −5, +2, +5, +10 per cent) or enter one. Output: the scenario rate (current rate × (1 + movement)) and the shipment cost in that scenario, marked "a scenario, not a forecast". Without a rate and a movement it shows nothing.
- **Further down.** "What a real estimate will need" (nine steps, none built) and "Currency is a separate question".
- **Limitations.** The rate and the movement are yours. AirPulse supplies neither and predicts neither.

## 7. Research

### 7.1 Methodology (`/methodology`)

Sections, in order: what AirPulse predicts and what it does not; the data; the target (the ±0.5 per cent band, first release and final figure, when an outlook is issued); how the outlook is formed (the seasonal count, step by step); the benchmarks it was compared with; what is not in the product and why; air traffic; walk-forward validation; no hindsight; limitations; towards rate estimates; and a note on the Control Center, a separate research tool that is run locally from the repository and is not part of the site.

### 7.2 Data (`/data`)

- **Purpose.** Where the numbers come from, how fresh they are and under what terms they are shown.
- **What you see.** The data mode (SNAPSHOT until a scheduler has run); the last data refresh and what started it; scheduled fetches on record; sources healthy; whether the run records are intact; how far the index and fuel reach. Then a table of every source: used for, status, last success, last attempt, started by, newest data, publication frequency, check interval, staleness limit and terms. Further sections: last pipeline run, coverage and freshness, refresh schedule, known limitations, versions (export version and time, engine and content identifiers).
- **Interpretation.** *Healthy*: last fetch succeeded and the data are within their limit. A source can also be degraded, stale or failed; the table then says why.
- **Limitations.** Nothing in the table is typed; it is worked out from the run records. Until the site is deployed and scheduled, every refresh was started by a person, and the page says so.

## 8. What the site does not contain

| Not on the site | Why |
|---|---|
| A price or quote for a shipment; a rate per kilogram | No lane-rate data are held |
| A forecast of a commercial lane rate, at any horizon | No validated model exists |
| An archive of news, a news search, briefings | Only the trial page of 5.2a exists; it shows summaries of reported events and links, no article text |
| A weekly outlook | See 5.6 |
| Expected levels or anomaly flags for air traffic | Did not meet its test |
| Accounts, alerts, downloads, cookies | The site is static and stores nothing about a visitor |

## 9. Reading the outlook responsibly

The outlook is right in 67 of 122 scored months on one U.S. import index. Use it as a benchmark beside what you know about your own lanes. It says nothing about the size of a move, about other lanes, or about your rates.
