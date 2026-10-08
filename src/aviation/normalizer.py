"""Canonical flight records. A field the source does not give stays None: nothing is filled in.

One record = one flight event at one airport (a departure, an arrival, a cancellation ...). The schema is cfg.FLIGHT_FIELDS
plus `service` (what the source itself says: 'cargo', 'passenger' or None)."""
import hashlib, re
from src.aviation import aircraft, config as cfg

FIELDS = cfg.FLIGHT_FIELDS + ("service",)
HK = "+08:00"
DONE = ("Dep ", "At gate ", "Landed ")     # the statuses with which the airport reports a completed departure or arrival


def flight_id(source, source_record_id):
    return hashlib.sha1(f"{source}|{source_record_id}".encode("utf-8")).hexdigest()[:20]


def record(**kw):
    """A canonical record: every field present, unknown ones None, the event type checked."""
    extra = set(kw) - set(FIELDS)
    if extra: raise ValueError(f"not in the flight schema: {sorted(extra)}")
    r = {k: kw.get(k) for k in FIELDS}
    if r["event_type"] not in cfg.EVENT_TYPES: raise ValueError(f"event type {r['event_type']!r}")
    if not r["source"] or not r["source_record_id"]: raise ValueError("source and source_record_id are required")
    r["flight_id"] = flight_id(r["source"], r["source_record_id"]); r["aircraft_category"] = r["aircraft_category"] or "unknown"
    return r


def _clock(day, hhmm, shown=None):
    """ISO time in Hong Kong for 'HH:MM' on `day`; `shown` is the publisher's own '(dd/mm/yyyy)' when the event fell on another day."""
    if not hhmm or not re.fullmatch(r"\d{2}:\d{2}", hhmm): return None
    if shown and re.fullmatch(r"\d{2}/\d{2}/\d{4}", shown): day = f"{shown[6:]}-{shown[3:5]}-{shown[:2]}"
    return f"{day}T{hhmm}:00{HK}"


def from_hkia(day_block, cargo, arrival, retrieved_at, source_hash):
    """Records of one list of the Hong Kong airport flight information: one day, cargo or passenger, arrivals or departures."""
    day = day_block.get("date"); out = []
    for i, f in enumerate(day_block.get("list") or []):
        flights = f.get("flight") or [{}]; no = (flights[0].get("no") or "").strip(); op = (flights[0].get("airline") or "").strip() or None
        status = (f.get("status") or "").strip(); m = re.search(r"(\d{2}:\d{2})(?: \((\d{2}/\d{2}/\d{4})\))?", status)
        done = _clock(day, m.group(1), m.group(2)) if m and status.startswith(DONE) else None        # 'Est at 20:10' is an estimate: the flight is not confirmed
        ends = f.get("origin" if arrival else "destination") or []; other = ends[0] if ends else None
        event = "cancellation" if status.startswith("Cancel") else ("arrival" if arrival else "departure") if done else "unknown"
        digits = re.sub(r"\D", "", no)
        out.append(record(source="hkia", source_record_id=f"{day}|{'A' if arrival else 'D'}|{'C' if cargo else 'P'}|{f.get('time')}|{no}|{i}", event_type=event,
                          callsign=f"{op}{digits}" if op and digits else None, aircraft_category="unknown", origin=other if arrival else "HKG", destination="HKG" if arrival else other,
                          origin_country=None if arrival else "HK", destination_country="HK" if arrival else None,
                          scheduled_departure=None if arrival else _clock(day, f.get("time")), actual_departure=None if arrival else done,
                          scheduled_arrival=_clock(day, f.get("time")) if arrival else None, actual_arrival=done if arrival else None,
                          timestamp=_clock(day, f.get("time")), ingestion_timestamp=retrieved_at, data_version=retrieved_at[:10], source_hash=source_hash, service="cargo" if cargo else "passenger"))
    return out


def from_flightlist(row, retrieved_at, source_hash):
    """Records of one row of a flight list (a flight with its first and last observation): a departure where the origin is known, an arrival where the destination is."""
    op = aircraft.operator_of(row.get("callsign")); typ = row.get("typecode") or None; cat = aircraft.classify(typ, op)["category"]; out = []
    base = dict(source="flightlist", callsign=(row.get("callsign") or "").strip() or None, registration=row.get("registration") or None, aircraft_icao24=row.get("icao24") or None, aircraft_type=typ,
                aircraft_category=cat, origin=row.get("origin") or None, destination=row.get("destination") or None, ingestion_timestamp=retrieved_at, data_version=retrieved_at[:10], source_hash=source_hash)
    key = f"{row.get('icao24')}|{row.get('firstseen')}"
    if base["origin"]: out.append(record(**base, source_record_id=key + "|D", event_type="departure", actual_departure=row.get("firstseen"), timestamp=row.get("firstseen")))
    if base["destination"]: out.append(record(**base, source_record_id=key + "|A", event_type="arrival", actual_arrival=row.get("lastseen"), timestamp=row.get("lastseen")))
    return out


def dedupe(records, keep="last"):
    """One record per flight_id. keep='first': the record as first ingested; 'last': the latest version ingested. Returns (records, number removed)."""
    best = {}
    for r in sorted(records, key=lambda r: (r["ingestion_timestamp"] or "")):
        if keep == "first" and r["flight_id"] in best: continue
        best[r["flight_id"]] = r
    return list(best.values()), len(records) - len(best)


def as_of(records, cutoff, keep="last"):
    """What was known at `cutoff` (ISO time): records ingested by then whose event time is not after it. A record without an event time is left out: it cannot be placed."""
    known = [r for r in records if r["ingestion_timestamp"] and r["ingestion_timestamp"] <= cutoff and r["timestamp"] and _utc(r["timestamp"]) <= _utc(cutoff)]
    return dedupe(known, keep)[0]


def _utc(ts):
    import pandas as pd
    return pd.Timestamp(ts).tz_convert("UTC") if pd.Timestamp(ts).tzinfo else pd.Timestamp(ts, tz="UTC")
