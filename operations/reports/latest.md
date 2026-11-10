# AirPulse operations report (daily)

Generated 2026-11-10T15:36:05Z from the run records, the ledgers and the clock. Do not edit: the next run overwrites it.

## Pipeline runs

- Runs on record: 42; started by a scheduler: 39; started by hand: 3.
- Last run: 2026-11-10T15:32:30Z, started by schedule, exit 2, gate passed.
- Source fetches on record: 190 by a scheduler, 112 by hand.

## Sources

| Source | Status | Last success | Newest data | Stale after | Note |
|---|---|---|---|---|---|
| US Gulf Coast jet fuel (EIA) | HEALTHY | 2026-11-09T18:57:06Z | 2026-11-03 | 14 days |  |
| Brent crude (EIA) | HEALTHY | 2026-11-09T18:57:06Z | 2026-11-03 | 14 days |  |
| Asia → US air freight price index, every release (BLS IC1312) | FAILED | 2026-10-07T06:11:31Z | 2026-09-16 | 28.5 days | HTTP 403 from https://www.bls.gov/bls/news-release/ximpim.htm; last success 34 days ago |
| Europe → US air freight price index, every release (BLS IC1311) | FAILED | 2026-10-07T06:11:32Z | 2026-09-16 | 28.5 days | HTTP 403 from https://www.bls.gov/bls/news-release/ximpim.htm; last success 34 days ago |
| All inbound US air freight price index, every release (BLS IC131) | FAILED | 2026-10-07T06:11:32Z | 2026-09-16 | 28.5 days | HTTP 403 from https://www.bls.gov/bls/news-release/ximpim.htm; last success 34 days ago |
| US → Europe air freight price index, every release (BLS IS2311) | FAILED | 2026-10-07T06:11:33Z | 2026-09-16 | 28.5 days | HTTP 403 from https://www.bls.gov/bls/news-release/ximpim.htm; last success 34 days ago |
| US → Asia air freight price index, every release (BLS IS2312) | FAILED | 2026-10-07T06:11:34Z | 2026-09-16 | 28.5 days | HTTP 403 from https://www.bls.gov/bls/news-release/ximpim.htm; last success 34 days ago |
| All outbound US air freight price index, every release (BLS IS231) | FAILED | 2026-10-07T06:11:35Z | 2026-09-16 | 28.5 days | HTTP 403 from https://www.bls.gov/bls/news-release/ximpim.htm; last success 34 days ago |
| All US import air freight (BoP) price index, every release (BLS IV131) | FAILED | 2026-10-07T06:11:36Z | 2026-09-16 | 28.5 days | HTTP 403 from https://www.bls.gov/bls/news-release/ximpim.htm; last success 34 days ago |
| Europe import air freight (BoP) price index, every release (BLS IV1311) | FAILED | 2026-10-07T06:11:36Z | 2026-09-16 | 28.5 days | HTTP 403 from https://www.bls.gov/bls/news-release/ximpim.htm; last success 34 days ago |
| Air Cargo Week headlines | DISABLED | - | - | 3 days |  |
| Splash247 headlines | DISABLED | - | - | 3 days |  |
| Air Cargo Week: reported events | FAILED | 2026-11-05T15:26:01Z | 2026-11-05T15:10:10Z | 4 days | HTTPError: HTTP Error 403: Forbidden; last success 5 days ago |
| Splash247: reported events | HEALTHY | 2026-11-10T15:35:33Z | 2026-11-10T12:00:00Z | 4 days |  |
| Hong Kong International Airport flight information | HEALTHY | 2026-11-09T18:58:42Z | 2026-11-08 | 3 days |  |
| European airports, daily movements (EUROCONTROL) | DISABLED | - | - | 14 days |  |
| US international nonstop departures (US DOT) | HEALTHY | 2026-11-09T18:58:34Z | 2026-06 | 14 days |  |
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

