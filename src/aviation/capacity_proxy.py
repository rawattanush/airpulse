"""Capacity PROXY (protocol 4.0, section 5): a weighted count of movements by aircraft class.

It is not cargo capacity. Aircraft type does not give payload, and a flight count does not give what was loaded. The
weights are declared in cfg.SCHEMES and are never fitted."""
import pandas as pd
from src.aviation import config as cfg

LABEL = "capacity proxy (declared weights per movement; not cargo capacity)"


def proxy(counts, scheme):
    """Proxy of one airport or route and period. counts: {aircraft class: movements}. None when there are no counts at all (missing is not zero)."""
    w = cfg.SCHEMES[scheme]; unknown = set(counts) - set(w)
    if unknown: raise ValueError(f"not an aircraft class: {sorted(unknown)}")
    if not counts: return None
    return float(sum(w[c] * n for c, n in counts.items()))


def frame(long, keys, scheme, cat="cat", value="flights"):
    """Proxy for every group of a long table (one row per group and aircraft class). Returns a Series indexed by `keys`."""
    w = pd.Series(cfg.SCHEMES[scheme]); bad = set(long[cat].unique()) - set(w.index)
    if bad: raise ValueError(f"not an aircraft class: {sorted(bad)}")
    return (long[value] * long[cat].map(w)).groupby([long[k] for k in keys]).sum()


def mix(counts):
    """Shares that describe the fleet behind a count: widebody, freighter and unknown shares of all movements. None for an empty count."""
    n = sum(counts.values())
    if not n: return None
    g = lambda *cs: sum(counts.get(c, 0) for c in cs) / n
    return {"movements": n, "widebody_share": g("passenger_widebody", "freighter_widebody"), "freighter_share": g("freighter_narrowbody", "freighter_widebody"), "unknown_share": g("unknown")}
