"""Route aggregates: airport pair, country pair, region pair. A route end that is not in the airport table has no country and no region here."""
import csv, functools, os
import numpy as np, pandas as pd
from src.aviation import airports, config as cfg


@functools.lru_cache(maxsize=2)
def cargo_codes(path=None):
    with open(path or os.path.join(cfg.REFERENCE_DIR, "cargo_carrier_codes.csv"), newline="", encoding="utf-8") as f: return {r["carrier_code"]: r["role"] for r in csv.DictReader(f)}


def us_routes(dep):
    """Monthly activity of every US-foreign airport pair whose foreign end is in the airport table.
    Columns: month, route ('HKG-ANC': foreign end first), foreign_airport, us_airport, country, region, departures, all_cargo_departures, combination_departures.
    The source does not say in which direction a departure flew; a pair is therefore the sum of both directions."""
    role = dep["carrier"].map(cargo_codes()); x = dep.assign(all_cargo=np.where(role == "all_cargo", dep["departures"], 0), combination=np.where(role == "combination", dep["departures"], 0))
    info = {r["airport_iata"]: r for r in airports.table()}; x = x[x["foreign_airport"].isin(info)]
    g = x.groupby(["month", "foreign_airport", "us_airport"], as_index=False).agg(departures=("departures", "sum"), all_cargo_departures=("all_cargo", "sum"), combination_departures=("combination", "sum"))
    g["route"] = g["foreign_airport"] + "-" + g["us_airport"]; g["country"] = g["foreign_airport"].map(lambda a: info[a]["country"]); g["region"] = g["foreign_airport"].map(lambda a: info[a]["region"])
    return g


def by(routes, level, value="departures"):
    """Sum a route table to 'route', 'country' or 'region' and month. Returns a wide table (index month, one column per group)."""
    return routes.pivot_table(index="month", columns=level, values=value, aggfunc="sum").sort_index()


def complete(wide, start, end):
    """Reindex a wide monthly table to every month from start to end. A month the source has no row for is zero only inside the span the source covers, missing outside it."""
    idx = pd.date_range(start, end, freq="MS").strftime("%Y-%m-%d"); return wide.reindex(idx).fillna(0.0)


def flag_changes(wide, min_expected=None):
    """Route disappearance and recovery by month: a route whose median of the same month in the previous 3 years is at least `min_expected` and that shows no departure,
    and the first month with departures after such a gap. Returns a list of dicts."""
    m = cfg.DETECTOR["route_min_expected"] if min_expected is None else min_expected; out = []; idx = list(wide.index)
    for route in wide.columns:
        s = wide[route]; gone = False
        for i, month in enumerate(idx):
            if i < 36: continue
            ref = [s.iloc[i - 12 * y] for y in (1, 2, 3)]; e = float(np.median(ref)); a = float(s.iloc[i])
            if not gone and e >= m and a == 0: out.append({"route": route, "month": month, "event_type": "route_disappearance", "observed": a, "expected": e}); gone = True
            elif gone and a > 0: out.append({"route": route, "month": month, "event_type": "route_recovery", "observed": a, "expected": e}); gone = False
    return out
