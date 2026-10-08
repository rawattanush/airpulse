"""Canonical airport table and airport matching. A code that is not in the table is unknown: it is never guessed."""
import csv, functools, os
from src.aviation import config as cfg

FIELDS = ("airport_iata", "airport_icao", "airport_name", "country", "region", "latitude", "longitude", "timezone", "cargo_relevance", "hub_type", "source")
# first letters of ICAO location indicators -> world region used for corridors (coarser than the airport table, and independent of it)
PREFIX_REGION = (("VI", "South Asia"), ("VA", "South Asia"), ("VO", "South Asia"), ("VE", "South Asia"), ("VG", "South Asia"), ("VC", "South Asia"), ("OP", "South Asia"), ("VN", "South Asia"),
                 ("VH", "East Asia"), ("VM", "East Asia"), ("RJ", "East Asia"), ("RO", "East Asia"), ("RK", "East Asia"), ("RC", "East Asia"), ("Z", "East Asia"),
                 ("WS", "Southeast Asia"), ("WM", "Southeast Asia"), ("WB", "Southeast Asia"), ("WI", "Southeast Asia"), ("WA", "Southeast Asia"), ("VT", "Southeast Asia"), ("VV", "Southeast Asia"),
                 ("VD", "Southeast Asia"), ("VL", "Southeast Asia"), ("VY", "Southeast Asia"), ("RP", "Southeast Asia"),
                 ("LT", "Middle East"), ("LL", "Middle East"), ("O", "Middle East"),
                 ("E", "Europe"), ("L", "Europe"), ("BI", "Europe"),
                 ("K", "North America"), ("PA", "North America"), ("PH", "North America"), ("C", "North America"))


@functools.lru_cache(maxsize=4)
def table(path=None):
    """The airport table as a tuple of dicts. Raises if the file is missing: there is no built-in fallback list."""
    with open(path or os.path.join(cfg.REFERENCE_DIR, "airports.csv"), newline="", encoding="utf-8") as f: rows = list(csv.DictReader(f))
    for r in rows: r["latitude"], r["longitude"] = float(r["latitude"]), float(r["longitude"])
    return tuple(rows)


@functools.lru_cache(maxsize=4)
def _index(path=None):
    idx = {}
    for r in table(path): idx[r["airport_iata"]] = r; idx[r["airport_icao"]] = r
    return idx


def match(code, path=None):
    """Airport record for an IATA or ICAO code, or None. Case and surrounding blanks are ignored; nothing else is repaired."""
    if not isinstance(code, str): return None
    return _index(path).get(code.strip().upper())


def region_of(icao):
    """World region of an ICAO location indicator by its prefix, or None when the prefix is not listed or the code is not an ICAO code."""
    if not isinstance(icao, str) or len(icao.strip()) != 4: return None
    c = icao.strip().upper()
    for prefix, region in PREFIX_REGION:
        if c.startswith(prefix): return region
    return None


def validate(path=None):
    """Problems of the airport table itself: duplicate or malformed codes, coordinates out of bounds, missing fields. Empty list = valid."""
    rows = table(path); bad = []
    for k in ("airport_iata", "airport_icao"):
        seen = [r[k] for r in rows]; bad += [f"duplicate {k} {c}" for c in sorted({c for c in seen if seen.count(c) > 1})]
    for r in rows:
        if not (len(r["airport_iata"]) == 3 and r["airport_iata"].isalpha() and r["airport_iata"].isupper()): bad.append(f"IATA code {r['airport_iata']!r}")
        if not (len(r["airport_icao"]) == 4 and r["airport_icao"].isalnum() and r["airport_icao"].isupper()): bad.append(f"ICAO code {r['airport_icao']!r}")
        if not (-90 <= r["latitude"] <= 90 and -180 <= r["longitude"] <= 180): bad.append(f"coordinates of {r['airport_iata']}")
        if region_of(r["airport_icao"]) != r["region"]: bad.append(f"region of {r['airport_iata']}: table says {r['region']}, prefix says {region_of(r['airport_icao'])}")
        bad += [f"{r['airport_iata']}: empty {k}" for k in FIELDS if r.get(k) in (None, "")]
    return bad
