# AirPulse: Data and Licensing

Version 1.1, 2026-10-07.

This document states where every piece of data in AirPulse comes from, what the system does with it, and where its licence stands. It records readings of publishers' own terms on the dates given. **It is not legal advice**, and where a reading is uncertain the status says so instead of assuming permission. The authoritative machine-readable form is `config/production_sources.yaml`; the deployment workflow follows that file, not this document.

## 1. Classification

Every source has exactly one licence status.

| Status | Meaning | Effect |
|---|---|---|
| CLEARED | Every right the product uses (automated retrieval, storage, derived values, public display) is stated in the publisher's own terms | May be deployed |
| PENDING_CONFIRMATION | A named question to the publisher is open | Built and checked; **not deployed** |
| RESEARCH_ONLY | Held for research; terms unknown or restrictive | Never in the hosted repository |
| RETIRED | No longer read | Nothing of it in production |
| NOT_CONNECTED | Assessed and never read | Listed so that the gap is visible |

A second attribute, the licence class (for example "commercial use with attribution", "non-commercial", "licence required", "unknown"), records the kind of terms. A production source with class *unknown* or a restrictive class is refused by the policy check whatever else is set.

## 2. Production sources

### 2.1 U.S. Bureau of Labor Statistics: air-freight price indexes

- **Status: CLEARED.**
- **What:** eight series of the International Price Program (import and export air freight), every monthly release from 2010-03-16, values from 1990.
- **Where read:** the Bureau's archive of news releases and its public data interface (version 1, no key, limited to 25 requests a day, which the pipeline stays far below: the interface is asked only when a new release exists).
- **Basis:** the Bureau's publications are works of the U.S. Government in the public domain; it asks for citation.
- **Attribution used:** "Source: U.S. Bureau of Labor Statistics, Import and Export Price Indexes".
- **Conduct of the client:** the Bureau's terms ask that automated clients do not burden its servers and can be identified. Requests are spaced, bounded, and carry a client name with a contact reference (the address of the hosted repository, or a value the maintainer sets). No personal address is built in.
- **Stored:** the release tables as retrieved, a vintage matrix per series, checksums.

### 2.2 U.S. Energy Information Administration: jet fuel and Brent spot prices

- **Status: CLEARED in the policy, by the owner's decision of 2026-10-08. Not confirmed by the publisher.**
- **What:** two daily spot price series, from the history spreadsheets of the petroleum spot price tables.
- **The open point.** The Administration's reuse page says its publications are in the public domain and may be used and distributed with an acknowledgment. The definitions page of the spot price tables names a commercial data vendor (Refinitiv, an LSEG business) as the source of these prices, and the reuse page sets apart "protected materials" of private contributors without saying whether these tables are such material. Neither page settles it.
- **What was not done.** A message with six specific questions was drafted in the research repository. **It was not sent.** No answer exists.
- **Owner's decision (change record CL-027).** The owner publishes the two series on the strength of the Administration's reuse statement and accepts the open point. If the Administration or the vendor objects, the fuel prices and the two comparison models that use them are removed; the official forecast does not use fuel prices and is unaffected.
- **What this is and is not.** It is a decision about risk taken by the person responsible for the site. It is not a confirmation, and this document does not claim one.
- **Attribution used:** "Source: U.S. Energy Information Administration", with the date of the release.

### 2.3 Airport Authority Hong Kong: flight information

- **Status: CLEARED**, with attribution. Published through DATA.GOV.HK under that portal's terms, which permit free use, including commercial use, with acknowledgment.
- **Use:** counts of flights, cargo flights apart, shown as observed. No derived reading is published.

### 2.4 U.S. Department of Transportation: international departures

- **Status: CLEARED.** A work of the U.S. Government.
- **Use:** a historical record of departures by route.

### 2.5 Air Cargo Week and Splash247: press events for the news-adjusted view

- **Status: CLEARED in the policy by the owner's decision of 2026-10-09 (class OWNER-ACCEPTED). Not confirmed by the publishers.**
- **What is read:** the article metadata of the last 45 days, once a day, through each publication's public interface.
- **What is kept and shown:** for each article the events a fixed set of rules recognises in its headline (kind, direction, places and organisations named), its address and date, and a hash of the normalised headline. **The headline text and the article are not stored, not committed and not shown.** The site shows what kind of event was reported and links to the article.
- **Terms.** No terms of reuse were found on either site; no permission was asked. The owner accepts that and removes the sources if a publisher objects. The policy refuses this class unless the owner's decision is written beside it.
- **Use.** Inputs of the experimental news-adjusted view only. Not an input of the official outlook.
- **Not the same as** the research archive of headlines (section 4), which holds the publishers' text and is not in the hosted repository.

## 3. Retired: the access path through FRED and ALFRED

Until 2026-10-07 the product read the index vintages through ALFRED and the fuel series through FRED, two data services of the Federal Reserve Bank of St. Louis. An earlier licence audit had classed that path as usable with limits, on the strength of the service's summary of its terms.

The full terms, read again with those of the programming interface, license a download for personal, non-commercial use and forbid, without the Bank's prior written consent, storing or archiving the content, passing stored portions to third parties, and using it to develop or train software or models. AirPulse had done each of these. The earlier reading was wrong. It is kept in the record, marked as superseded.

**What was done (change record CL-024).**

1. The index history was rebuilt from the Bureau's own archived releases under a rule fixed before any comparison (see the system design, section 6.1). The fuel series were taken from the Administration's own spreadsheets; they are identical to the copies held, observation for observation.
2. Both adapters for the retired services were removed. Twelve source entries were replaced.
3. The evaluation was rerun on the first-party inputs with the unchanged method, and compared field by field with the ledger of the earlier inputs. Both ledgers are kept. The official forecaster's forecasts are unchanged; its record is 67 of 122 months instead of 68 of 123, because one month can no longer be issued.
4. The weekly fuel-cost outlook, whose release windows existed only through ALFRED, was taken out of the product. It was not approximated.
5. A deployment check fails a hosted repository that contains any file, address, identifier or name of the retired path. Research scripts that used to fetch from the services refuse the request.

**What remains.** Files that came through those services are still in the research repository, classed RESEARCH_ONLY or RETIRED: the earlier benchmark snapshot, the data of the research passes, the operational record made before the repair. They are not in the hosted repository. The Bank's consent to the copies already held and to the past research use was not sought; a draft request exists. Whether to send it, or to delete the copies, is the owner's decision.

## 4. Research-only data

| Data | Why research only |
|---|---|
| Trade-press headline archive (two publications, from 2014) | The publishers' text; terms on reuse unknown; not redistributed. A table of numbers derived from it (monthly rates of reported events) is shipped for training the news-adjusted model |
| EUROCONTROL airport statistics | Commercial use forbidden |
| Historical flight lists 2019 to 2022 | A research data set with its own terms |
| Aircraft positions (community network) | Not in the product; source switched off |
| Macro-economic, trade and market series of the research passes | Obtained through the retired path |
| Derivatives and positioning data of protocol 6.0 | Research; the result was negative |

None of these is in the hosted repository. The allow-list that assembles it names what is taken; a list of paths that may never be taken is checked against the result.

## 5. Commercial freight-rate sources

A feasibility study and a final audit examined twenty candidate sources of current air-freight prices: commercial rate indexes, forwarders' and marketplaces' quotation tools, carriers' rate pages and surcharge notices, and official statistics.

**Findings.**

- Sources that publish current lane rates or quotes either sell them under a commercial licence or forbid, in their own terms, automated collection and the building of derived products. Several require a registered account.
- Carriers' fuel surcharges are published with dates. They are a component of a price, not a price, and public reuse would need each carrier's written permission.
- Official trade statistics give charges and weights of air imports monthly, about five weeks late; on the audit date they could be read only with a key.

**Why none is used.**

- No licence was bought, no account was created, no quotation form was submitted, and no access control was worked around. These were constraints of the project, not omissions.
- A proposal to collect rates through rotating proxies was declined: evading a provider's limits does not create a right to its data.
- No rate was constructed from proxies. A fabricated price would be worse than none.

**Consequence for the product.** AirPulse forecasts the direction of an official index. It does not forecast, estimate or quote a commercial rate. The path to a rate product is a commercial data licence; that decision has not been taken.

## 6. Storage policy

| What | Kept | Why |
|---|---|---|
| Publishers' answers of production sources | As retrieved, with the date | So that what was published can be reproduced; the fuel publisher keeps no dated releases itself |
| Accepted files | With a checksum sidecar naming source, address and time | Integrity and provenance |
| Operational records | Append-only, hash-chained | Tamper evidence |
| Personal data | None is collected or stored | The site has no accounts, no cookies and no analytics |
| Research data | In the research repository only | Not redistributable or of unknown terms |

## 7. The deployment gate

Licence status is enforced by the build, not by a reader's care.

1. The policy check runs on every production run and fails the gate if the policy is inconsistent or a production source has an unknown or restricted class.
2. Before any upload, the repository, the exported data and the built site are searched for restricted paths and for the retired access path.
3. The **licence gate** then asks whether every production source is CLEARED. If not, the upload step and the deploy job are skipped, and a job named for the purpose fails, so that the run is visibly incomplete.

At present every production source is CLEARED in the policy (the two fuel sources by the owner's decision, section 2.2), so the gate is open.

## 8. Attribution shown on the site

Each figure on the site names its source and the date of its data. The Data page lists, for every source: provider, data set, purpose, publication frequency, age, state of the last retrieval and licence status, generated from the policy and the records.

## 9. Summary of legal status

| Item | Status | Open action |
|---|---|---|
| BLS indexes | CLEARED | None |
| Hong Kong flight information; U.S. route departures | CLEARED | None |
| EIA fuel prices | CLEARED by the owner's decision; not confirmed by the publisher | Remove on objection. The drafted question can still be sent |
| FRED / ALFRED in production | RETIRED; none present | None |
| FRED / ALFRED copies in the research repository | RESEARCH_ONLY / RETIRED | Owner decides: ask the Bank's consent, or delete |
| Press events (two trade publications) | CLEARED by the owner's decision; terms not established | Remove on objection |
| Commercial rate data | Not used | A licence, if a rate product is wanted |
| Brand photographs on the site | Right to publish to be confirmed by the owner (known issue KI-092) | Owner confirms or replaces |
| Hosting provider's rule on commercial use of free static hosting | Noted (known issue KI-093) | Owner reviews before any commercial use |

No clearance is claimed beyond what this table states. In particular, no confirmation of the Energy Information Administration is claimed.
