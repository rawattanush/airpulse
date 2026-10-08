"""Corridor-level signals (protocol 4.0, section 8).

Corridor index of a month = sum over routes of w x activity / baseline. w is the route's share of the corridor's
departures in a window that ends 12 months earlier, so neither the current period nor the target can shape a weight."""
import numpy as np, pandas as pd
from src.aviation import anomaly, config as cfg


def shares(wide, month, window=cfg.SHARE_WINDOW_MONTHS, gap=12):
    """Route weights for `month` from the `window` months that end `gap` months before it. None when that window is not fully inside the table."""
    idx = list(wide.index); i = idx.index(month); lo, hi = i - gap - window, i - gap
    if lo < 0: return None
    tot = wide.iloc[lo:hi].sum(); s = tot.sum()
    return (tot / s) if s > 0 else None


def index(wide):
    """Monthly corridor index and its anomaly. wide: months x routes (departures). Returns a table with index, weight_covered, z, band, expected-style columns of the plain total."""
    rows = []; base = {r: anomaly.monthly_scores(pd.Series(wide[r].to_numpy(), index=pd.to_datetime(wide.index))) for r in wide.columns}
    for i, month in enumerate(wide.index):
        w = shares(wide, month); val, cov = np.nan, 0.0
        if w is not None:
            parts = [(w[r], base[r]["actual"].iloc[i] / base[r]["expected"].iloc[i]) for r in wide.columns if w[r] > 0 and base[r]["expected"].iloc[i] and base[r]["expected"].iloc[i] >= cfg.BASELINE["min_expected"]]
            cov = float(sum(p[0] for p in parts))
            if cov > 0: val = float(sum(a * b for a, b in parts) / cov)
        rows.append({"month": month, "index": val, "weight_covered": cov})
    out = pd.DataFrame(rows).set_index("month"); tot = anomaly.monthly_scores(pd.Series(wide.sum(axis=1).to_numpy(), index=pd.to_datetime(wide.index)))
    for k in ("actual", "expected", "difference", "ratio", "z", "band"): out[k] = tot[k].to_numpy()
    return out


def corridor_routes(routes, corridor):
    """Routes of the US table that belong to a corridor whose far end is North America (the table holds US-touching routes only)."""
    origins, dest = cfg.CORRIDORS[corridor]
    if dest != ("North America",): return routes.iloc[0:0]
    return routes[routes["region"].isin(origins)]
