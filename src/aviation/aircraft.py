"""Aircraft classification: ICAO type designator and operator -> one of seven classes.

A type designator does not say whether an airframe is a freighter: the 777 Freighter and the 777-200LR share B77L, the
747-400F and the passenger 747-400 share B744. The role of such a type is taken from the operator when the operator is
an all-cargo airline; for an airline that flies passenger aircraft and freighters under one code it stays unknown.
Nothing is classed as a freighter by default."""
import csv, functools, os
import numpy as np, pandas as pd
from src.aviation import config as cfg


@functools.lru_cache(maxsize=2)
def types(path=None):
    with open(path or os.path.join(cfg.REFERENCE_DIR, "aircraft_types.csv"), newline="", encoding="utf-8") as f: return {r["aircraft_type"]: r for r in csv.DictReader(f)}


@functools.lru_cache(maxsize=2)
def operators(path=None):
    with open(path or os.path.join(cfg.REFERENCE_DIR, "aircraft_operators.csv"), newline="", encoding="utf-8") as f: return {r["operator_icao"]: r for r in csv.DictReader(f)}


def operator_of(callsign):
    """ICAO operator designator of an airline callsign (three letters followed by a flight number), or None."""
    if not isinstance(callsign, str): return None
    c = callsign.strip().upper()
    return c[:3] if len(c) >= 4 and c[:3].isalpha() and c[3].isdigit() else None


def classify(aircraft_type, operator=None):
    """{'category', 'widebody', 'freighter', 'cargo_capable', 'confidence'} for one aircraft type and operator designator.
    widebody / freighter are True, False or None (not established)."""
    t = types().get(aircraft_type.strip().upper()) if isinstance(aircraft_type, str) else None
    op = operators().get(operator.strip().upper()) if isinstance(operator, str) and operator.strip() else None
    cargo_op = bool(op and op["role"] == "all_cargo")
    if t is None: return {"category": "unknown", "widebody": None, "freighter": True if cargo_op else None, "cargo_capable": None, "confidence": "none"}
    body, role = t["category"], t["freighter"]; wide = body == "widebody"; out = {"widebody": wide, "cargo_capable": t["cargo_capable"]}
    if body == "general": return {**out, "category": "general", "freighter": bool(cargo_op), "confidence": t["confidence"]}
    if role == "always" or (role == "mixed" and cargo_op): freighter, conf = True, (t["confidence"] if role == "always" else min(t["confidence"], op["confidence"], key=("medium", "high").index))
    elif role == "never": freighter, conf = False, t["confidence"]
    elif op is not None and op["role"] == "combination": freighter, conf = None, "low"          # this airline flies the type in both roles
    elif isinstance(operator, str) and operator.strip(): freighter, conf = False, "medium"       # an airline that is not on the cargo lists: passenger by default
    else: freighter, conf = None, "low"                                                          # no operator known
    if body == "regional": return {**out, "category": "regional", "freighter": freighter, "confidence": conf}
    if freighter is None: return {**out, "category": "unknown", "freighter": None, "confidence": conf}
    return {**out, "category": ("freighter_" if freighter else "passenger_") + body, "freighter": freighter, "confidence": conf}


def classify_frame(typecode, operator):
    """Vectorised classify for two aligned Series. Returns a Series of categories."""
    key = pd.DataFrame({"t": typecode.fillna("").astype(str).str.strip().str.upper(), "o": operator.fillna("").astype(str).str.strip().str.upper()})
    pairs = key.drop_duplicates(); pairs = pairs.assign(c=[classify(t or None, o or None)["category"] for t, o in zip(pairs["t"], pairs["o"])])
    return key.merge(pairs, on=["t", "o"], how="left")["c"].set_axis(typecode.index)


def validate():
    """Problems of the two reference tables. Empty list = valid."""
    bad = []
    for k, r in types().items():
        if r["category"] not in ("widebody", "narrowbody", "regional", "general"): bad.append(f"{k}: body {r['category']!r}")
        if r["freighter"] not in ("always", "never", "mixed"): bad.append(f"{k}: role {r['freighter']!r}")
        if (r["widebody"] == "yes") != (r["category"] == "widebody"): bad.append(f"{k}: widebody flag disagrees with the body class")
        if r["confidence"] not in ("high", "medium"): bad.append(f"{k}: confidence {r['confidence']!r}")
    for k, r in operators().items():
        if r["role"] not in ("all_cargo", "combination"): bad.append(f"{k}: role {r['role']!r}")
        if not (len(k) == 3 and k.isalpha() and k.isupper()): bad.append(f"operator code {k!r}")
    return bad
