# Notice

## Data in this repository and on the site

Every source below is read at its publisher. The terms were read on the dates given in the policy file (2026-10-05 to 2026-10-07). The class of each licence, the sentence it rests on and the
address it was read at are in `config/production_sources.yaml`; that file, not this page, decides what the site may show.
A reading of a publisher's terms is not legal advice.

| Data | Publisher | Terms as read | Held here |
|---|---|---|---|
| Import and export air-freight price indexes (eight series, one column per release) | U.S. Bureau of Labor Statistics, read at the Bureau: its archived monthly releases and its public data interface | Public domain; the Bureau asks to be cited. Licence status: CLEARED | `research/data_samples/`, `research/bls_releases/`, `operations/current/` |
| Jet fuel (US Gulf Coast) and Brent crude oil prices | U.S. Energy Information Administration, read at the Administration: its spreadsheets | The Administration's reuse page allows use and distribution with an acknowledgment. Its tables name a commercial data vendor as the source of the spot prices; whether that limits reuse was not asked of the Administration. Published on the owner's decision of 2026-10-08, without a confirmation; removed if the publisher or the vendor objects | `research/data_samples/`, `operations/current/`, `operations/raw/` |
| Flight information of Hong Kong International Airport | Airport Authority Hong Kong, through data.gov.hk | Free for commercial and non-commercial use with the source named. CLEARED | `operations/aviation/raw/hkia/` |
| International report: departures (US airports) | U.S. Department of Transportation | Public domain. CLEARED | `operations/aviation/official/usdot/` |
| Airport names and coordinates in `data/reference/airports.csv` | OurAirports | Public domain | `data/reference/` |

BLS.gov cannot vouch for the data or analyses derived from these data after the data have been retrieved from BLS.gov.

**The licence gate.** The workflow deploys only while every source of the product is recorded as CLEARED in
`config/production_sources.yaml` (`python scripts/deployment_checks.py licence`). The two fuel sources are recorded so by the
owner's decision; the basis is written out there under `limits`. No confirmation of the publisher is claimed.

**A retired access path.** Until 2026-10-07 the index and the fuel prices were read through FRED and ALFRED, two services of
the Federal Reserve Bank of St. Louis. Their terms forbid, without the Bank's written consent, keeping the data, passing
kept copies on and building models on them. That path is retired: no file, address or identifier of it is in this
repository, and a check in the workflow fails if one appears. The weekly fuel-cost outlook, which was built on dated
releases only those services hold, is not offered.


Sources that are declared in the configuration but switched off here, because their terms do not allow publication or
could not be read, are listed with the reason in `config/production_sources.yaml` and on the site's Methodology page.
None of their data is in this repository.

## Code and other content

The code, the text and the brand images of this repository belong to the owner of the repository. No licence to reuse
them is granted by their being public, unless a LICENSE file is added by the owner.

The fonts are loaded from the packages named in `airpulse-web/package.json` and are published by their authors under
the SIL Open Font License.

## What the figures are

A direction for a public price index, with a record that includes every month it was wrong. Not a freight rate, not a
quotation, not advice. Counts of flights are counts as published by their source: they are not an estimate of cargo
capacity and say nothing about prices.
