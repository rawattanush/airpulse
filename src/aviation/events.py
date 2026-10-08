"""Unusual-activity detector and its append-only event store (protocol 4.0, section 6).

An event states what was observed against what was expected. It names no cause: a link to a known disruption is
recorded as 'coincident with', by date and place only."""
import hashlib, os
import numpy as np
from src.observability import records
from src.aviation import config as cfg

METHOD_VERSION = f"detector {cfg.PROCESSING_VERSION}; bands {cfg.PROTOCOL_VERSION}"
STORE = os.path.join(cfg.OPS_DIR, "events.jsonl")
D = cfg.DETECTOR


def classify(sc):
    """Event type and severity of one scored period, or None when it is not an event (|z| below 2 or no baseline)."""
    z, ratio = sc.get("z"), sc.get("ratio")
    if z is None or not np.isfinite(z) or abs(z) < 2: return None
    r = ratio if ratio is not None and np.isfinite(ratio) else None
    if r is not None and abs(z) >= 3 and r <= D["collapse_ratio"]: kind = "activity_collapse"
    elif r is not None and abs(z) >= 3 and r >= D["surge_ratio"]: kind = "activity_surge"
    else: kind = "unusually_low_activity" if z < 0 else "unusually_high_activity"
    return {"event_type": kind, "severity": "EXTREME" if abs(z) >= 3 else "UNUSUAL"}


def detect(scores, place, source, measure="movements", confidence="official count"):
    """Events of one place from a scored table (index: period). Returns event dicts without store fields."""
    out = []
    for period, row in scores.iterrows():
        c = classify(row)
        if c is None: continue
        t = period.strftime("%Y-%m-%d") if hasattr(period, "strftime") else str(period)
        out.append({"event_id": hashlib.sha1(f"{source}|{place}|{measure}|{t}|{c['event_type']}".encode()).hexdigest()[:16], "event_time": t, "place": place, "measure": measure, **c,
                    "observed_value": float(row["actual"]), "expected_value": float(row["expected"]), "deviation": float(row["difference"]), "ratio": None if not np.isfinite(row["ratio"]) else float(row["ratio"]),
                    "z": float(row["z"]), "confidence": confidence, "source": source, "method_version": METHOD_VERSION})
    return out


def cancellation_spike(counts_row, place, source):
    """An event when a covered period holds at least the minimum number of cancellations and they are more than a fifth of what was scheduled."""
    n, rate = counts_row.get("cancellations", 0), counts_row.get("cancellation_rate")
    if n < D["cancellation_min"] or rate is None or rate < 0.2: return None
    t = str(counts_row["period"])
    return {"event_id": hashlib.sha1(f"{source}|{place}|cancellations|{t}".encode()).hexdigest()[:16], "event_time": t, "place": place, "measure": "cancellations", "event_type": "cancellation_spike",
            "severity": "EXTREME" if rate >= 0.5 else "UNUSUAL", "observed_value": float(n), "expected_value": None, "deviation": None, "ratio": float(rate), "z": None,
            "confidence": "reported by the airport", "source": source, "method_version": METHOD_VERSION}


def coincident(event, known):
    """Names of the known disruptions whose place and dates cover the event. known: [{'name', 'places', 'start', 'end'}]. A coincidence, not a cause."""
    return [k["name"] for k in known if event["place"] in k["places"] and k["start"] <= event["event_time"][:10] <= k["end"]]


def append(events, detected_at, path=None):
    """Add events that are not yet in the store. An event already stored is never rewritten. Returns the number added."""
    path = path or STORE; have = {r["event_id"] for r in records.read(path)}; n = 0
    for e in events:
        if e["event_id"] in have: continue
        records.append(path, {**e, "detected_at": detected_at}); have.add(e["event_id"]); n += 1
    return n


def read(path=None):
    return records.read(path or STORE)


def verify(path=None):
    """Problems of the store's hash chain (empty = intact)."""
    return records.verify(path or STORE)
