# AirPulse operations report (daily)

Generated 2026-10-22T12:58:43Z from the run records, the ledgers and the clock. Do not edit: the next run overwrites it.

## Pipeline runs

- Runs on record: 19; started by a scheduler: 16; started by hand: 3.
- Last run: 2026-10-22T12:55:51Z, started by schedule, exit 2, gate passed.
- Source fetches on record: 77 by a scheduler, 112 by hand.

## Sources

| Source | Status | Last success | Newest data | Stale after | Note |
|---|---|---|---|---|---|
| US Gulf Coast jet fuel (EIA) | HEALTHY | 2026-10-22T12:57:14Z | 2026-10-20 | 14 days |  |
| Brent crude (EIA) | HEALTHY | 2026-10-22T12:57:14Z | 2026-10-20 | 14 days |  |
| Asia → US air freight price index, every release (BLS IC1312) | DEGRADED | 2026-10-07T06:11:31Z | 2026-09-16 | 28.5 days | HTTP 403 from https://www.bls.gov/bls/news-release/ximpim.htm; the data of the last success are held |
| Europe → US air freight price index, every release (BLS IC1311) | DEGRADED | 2026-10-07T06:11:32Z | 2026-09-16 | 28.5 days | HTTP 403 from https://www.bls.gov/bls/news-release/ximpim.htm; the data of the last success are held |
| All inbound US air freight price index, every release (BLS IC131) | DEGRADED | 2026-10-07T06:11:32Z | 2026-09-16 | 28.5 days | HTTP 403 from https://www.bls.gov/bls/news-release/ximpim.htm; the data of the last success are held |
| US → Europe air freight price index, every release (BLS IS2311) | DEGRADED | 2026-10-07T06:11:33Z | 2026-09-16 | 28.5 days | HTTP 403 from https://www.bls.gov/bls/news-release/ximpim.htm; the data of the last success are held |
| US → Asia air freight price index, every release (BLS IS2312) | DEGRADED | 2026-10-07T06:11:34Z | 2026-09-16 | 28.5 days | HTTP 403 from https://www.bls.gov/bls/news-release/ximpim.htm; the data of the last success are held |
| All outbound US air freight price index, every release (BLS IS231) | DEGRADED | 2026-10-07T06:11:35Z | 2026-09-16 | 28.5 days | HTTP 403 from https://www.bls.gov/bls/news-release/ximpim.htm; the data of the last success are held |
| All US import air freight (BoP) price index, every release (BLS IV131) | DEGRADED | 2026-10-07T06:11:36Z | 2026-09-16 | 28.5 days | HTTP 403 from https://www.bls.gov/bls/news-release/ximpim.htm; the data of the last success are held |
| Europe import air freight (BoP) price index, every release (BLS IV1311) | DEGRADED | 2026-10-07T06:11:36Z | 2026-09-16 | 28.5 days | HTTP 403 from https://www.bls.gov/bls/news-release/ximpim.htm; the data of the last success are held |
| Air Cargo Week headlines | DISABLED | - | - | 3 days |  |
| Splash247 headlines | DISABLED | - | - | 3 days |  |
| Air Cargo Week: reported events | HEALTHY | 2026-10-22T12:57:52Z | 2026-10-22T11:36:33Z | 4 days |  |
| Splash247: reported events | HEALTHY | 2026-10-22T12:57:57Z | 2026-10-22T10:30:00Z | 4 days |  |
| Hong Kong International Airport flight information | HEALTHY | 2026-10-22T12:58:28Z | 2026-10-21 | 3 days |  |
| European airports, daily movements (EUROCONTROL) | DISABLED | - | - | 14 days |  |
| US international nonstop departures (US DOT) | HEALTHY | 2026-10-19T15:46:12Z | 2026-06 | 14 days |  |
| Aircraft positions near airports (adsb.lol) | DISABLED | - | - | 3 days |  |
| Tracked flight lists 2019 to 2022 (Zenodo record 7923702) | DISABLED | - | - | - |  |
| Live flight-tracking interface (research network) | DISABLED | - | - | - |  |
| GDELT news index | DISABLED | - | - | - |  |
| Weekly air-freight lane rates (commercial providers) | DISABLED | - | - | - |  |

## Monthly outlook

- Official forecaster by the selection rule: BL-SEA.
- Newest month due: 2026-09; official outlook on the ledger for it: yes.
- Last official outlook issued: 2026-09 (FLAT), generated 2026-10-07T06:11:42Z, LATE, started by manual.
- Forecasts on the ledger (all series and forecasters): 40; outcomes recorded: 0; outcomes of the official outlook: 0.

## Weekly fuel-cost outlook

- Not issued: the weekly fuel-cost outlook is not in the product (see `config/production_sources.yaml`, feature weekly_fuel_outlook).

