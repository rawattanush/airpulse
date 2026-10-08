"""Data-quality checks of canonical flight records and of the feeds behind them. A check reports; it never repairs."""
import datetime
import pandas as pd
from src.aviation import airports, config as cfg, normalizer


def _parse(ts):
    try: return normalizer._utc(ts)
    except Exception: return None


def check(records, tolerance_hours=1.0):
    """Counts and examples of every problem in a set of records. Keys with a zero count are kept so that a report always shows every check."""
    out = {k: [] for k in ("unknown_airport", "bad_timestamp", "missing_timestamp", "event_after_ingestion", "duplicate", "bad_coordinates", "bad_category", "bad_event_type", "same_origin_and_destination", "missing_schema_field")}
    seen = set()
    for r in records:
        rid = r.get("flight_id")
        if set(normalizer.FIELDS) - set(r): out["missing_schema_field"].append(rid)
        if rid in seen: out["duplicate"].append(rid)
        seen.add(rid)
        for k in ("origin", "destination"):
            if r.get(k) and airports.match(r[k]) is None: out["unknown_airport"].append(r[k])
        if r.get("origin") and r.get("origin") == r.get("destination"): out["same_origin_and_destination"].append(rid)
        if not r.get("timestamp"): out["missing_timestamp"].append(rid)
        else:
            t, ing = _parse(r["timestamp"]), _parse(r.get("ingestion_timestamp") or "")
            if t is None: out["bad_timestamp"].append(rid)
            elif ing is not None and r.get("event_type") in ("arrival", "departure") and t > ing + pd.Timedelta(hours=tolerance_hours): out["event_after_ingestion"].append(rid)   # a completed flight dated after it was read
        lat, lon = r.get("latitude"), r.get("longitude")
        if (lat is not None and not -90 <= lat <= 90) or (lon is not None and not -180 <= lon <= 180): out["bad_coordinates"].append(rid)
        if r.get("aircraft_category") not in cfg.CATEGORIES: out["bad_category"].append(rid)
        if r.get("event_type") not in cfg.EVENT_TYPES: out["bad_event_type"].append(rid)
    n = len(records) or 1
    missing = {k: sum(1 for r in records if r.get(k) in (None, "")) / n for k in ("aircraft_type", "callsign", "origin", "destination", "registration")}
    return {"records": len(records), "problems": {k: {"count": len(v), "examples": sorted({str(x) for x in v})[:5]} for k, v in out.items()}, "missing_share": missing,
            "unknown_airports": sorted({x for x in out["unknown_airport"]})}


def mode(newest_observation, now=None, historical=False):
    """Freshness of a feed from the time of its newest observation: LIVE, RECENT, DELAYED, STALE, UNAVAILABLE, or HISTORICAL for a fixed research data set.
    Returns (mode, age in hours or None)."""
    if historical: return "HISTORICAL", None
    t = _parse(newest_observation) if newest_observation else None
    if t is None: return "UNAVAILABLE", None
    now = _parse(now) if isinstance(now, str) else (now or pd.Timestamp(datetime.datetime.now(datetime.timezone.utc)))
    age = (now - t).total_seconds() / 3600.0
    if age < -1.0: return "UNAVAILABLE", None                              # an observation dated after the present cannot be given a freshness
    age = max(age, 0.0)
    for name, limit in cfg.MODES:
        if age <= limit: return name, age
    return "STALE", age


def age_text(hours):
    """'4 minutes', '2 h 14 min', '3 days' for an age in hours; None for None."""
    if hours is None: return None
    if hours < 1: return f"{max(int(round(hours * 60)), 0)} minutes"
    if hours < 48: return f"{int(hours)} h {int(round((hours - int(hours)) * 60))} min"
    return f"{int(hours // 24)} days"
