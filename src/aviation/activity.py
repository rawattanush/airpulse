"""Activity counts by airport and period, and readers of the stored historical snapshots.

A period a source does not cover is absent from the result. A covered period without a flight is zero. The two are never
mixed: counts() takes the set of covered periods explicitly."""
import glob, gzip, io, os
import numpy as np, pandas as pd
from src.ingestion import loaders
from src.aviation import airports, capacity_proxy, config as cfg

RES = {"hour": 13, "day": 10, "month": 7}


def period_of(ts, resolution):
    """Period label of an ISO local time: hour 'YYYY-MM-DDTHH', day, ISO week (its Monday), month."""
    if resolution == "week":
        d = pd.Timestamp(ts[:10]); return (d - pd.Timedelta(days=d.weekday())).strftime("%Y-%m-%d")
    return ts[:RES[resolution]]


def counts(records, airport, resolution="day", covered=None):
    """Activity of one airport from canonical records. covered: the periods the source answered for; periods outside it are not returned,
    periods inside it without a record are zero. Cancellations are counted beside movements, never among them."""
    code = airports.match(airport); iata = code["airport_iata"] if code else airport; rows = {}
    for r in records:
        if not r.get("timestamp"): continue
        side = "arrivals" if r["destination"] == iata and r["event_type"] in ("arrival", "cancellation", "unknown") and r["origin"] != iata else "departures" if r["origin"] == iata else None
        if side is None: continue
        p = period_of(r["timestamp"], resolution); c = rows.setdefault(p, {"arrivals": 0, "departures": 0, "cancellations": 0, "not_confirmed": 0, "cargo_movements": 0, "passenger_movements": 0, "ends": set(), "classes": {}})
        if r["event_type"] == "cancellation": c["cancellations"] += 1; continue
        if r["event_type"] == "unknown": c["not_confirmed"] += 1; continue
        c[side] += 1; c["classes"][r["aircraft_category"]] = c["classes"].get(r["aircraft_category"], 0) + 1
        if r.get("service") in ("cargo", "passenger"): c[r["service"] + "_movements"] += 1
        other = r["origin"] if side == "arrivals" else r["destination"]
        if other: c["ends"].add((side, other))
    periods = sorted(rows) if covered is None else sorted(covered); out = []
    for p in periods:
        c = rows.get(p, {"arrivals": 0, "departures": 0, "cancellations": 0, "not_confirmed": 0, "cargo_movements": 0, "passenger_movements": 0, "ends": set(), "classes": {}})
        scheduled = c["arrivals"] + c["departures"] + c["cancellations"]
        out.append({"airport": iata, "period": p, "arrivals": c["arrivals"], "departures": c["departures"], "movements": c["arrivals"] + c["departures"], "cancellations": c["cancellations"],
                    "cancellation_rate": c["cancellations"] / scheduled if scheduled else None, "not_confirmed": c["not_confirmed"], "cargo_movements": c["cargo_movements"], "passenger_movements": c["passenger_movements"],
                    "unique_origins": len({e for s, e in c["ends"] if s == "arrivals"}), "unique_destinations": len({e for s, e in c["ends"] if s == "departures"}),
                    **{f"proxy_{k}": capacity_proxy.proxy(c["classes"], k) for k in cfg.SCHEMES}})
    return pd.DataFrame(out)


# ---------------------------------------------------------------------------------------------------------------- stored snapshots

def _read(rel, **kw):
    path = os.path.join(cfg.SNAPSHOT_DIR, rel); loaders.verify_file(path)                 # a missing or altered file stops the read
    return pd.read_csv(path, **kw)


def european_daily(snapshot_dir=None):
    """Official daily IFR movements by airport (EUROCONTROL). Columns: date, airport_icao, departures, arrivals, movements."""
    d = snapshot_dir or os.path.join(cfg.SNAPSHOT_DIR, "eurocontrol"); parts = []
    for f in sorted(glob.glob(os.path.join(d, "airport_traffic_*.csv.gz"))):
        loaders.verify_file(f); parts.append(pd.read_csv(f, usecols=["FLT_DATE", "APT_ICAO", "FLT_DEP_1", "FLT_ARR_1", "FLT_TOT_1"]))
    if not parts: raise loaders.IngestionError("no airport traffic file found")
    x = pd.concat(parts).rename(columns={"FLT_DATE": "date", "APT_ICAO": "airport_icao", "FLT_DEP_1": "departures", "FLT_ARR_1": "arrivals", "FLT_TOT_1": "movements"})
    x["date"] = x["date"].str[:10]
    return x.drop_duplicates(["date", "airport_icao"]).sort_values(["airport_icao", "date"]).reset_index(drop=True)


def us_international(snapshot_dir=None):
    """Official monthly nonstop departures between US and foreign airports (US DOT). Columns: month, us_airport, foreign_airport, carrier, us_carrier, scheduled, charter, departures."""
    f = os.path.join(snapshot_dir or os.path.join(cfg.SNAPSHOT_DIR, "usdot"), "international_report_departures.csv.gz"); loaders.verify_file(f)
    x = pd.read_csv(f, usecols=["Year", "Month", "usg_apt", "fg_apt", "carrier", "carriergroup", "Scheduled", "Charter", "Total"], dtype={"carrier": str})
    x["month"] = x["Year"].astype(str) + "-" + x["Month"].astype(str).str.zfill(2) + "-01"
    return x.rename(columns={"usg_apt": "us_airport", "fg_apt": "foreign_airport", "Scheduled": "scheduled", "Charter": "charter", "Total": "departures"}).assign(us_carrier=x["carriergroup"] == 1)[
        ["month", "us_airport", "foreign_airport", "carrier", "us_carrier", "scheduled", "charter", "departures"]]


def flightlist(name):
    """One aggregate of the 2019-2022 flight lists: 'airport_daily', 'airport_monthly_types', 'route_monthly', 'region_monthly' or 'quality'."""
    return _read(os.path.join("flightlists", f"flightlist_{name}.csv.gz"), keep_default_na=False, na_values=[""])


def monthly_total(daily, value="movements", key="airport_icao"):
    """Monthly sums of a daily table, only for months in which every day is present (an incomplete month is missing)."""
    d = daily.assign(month=daily["date"].str[:7]); g = d.groupby([key, "month"]).agg(total=(value, "sum"), days=("date", "nunique")).reset_index()
    full = pd.to_datetime(g["month"] + "-01").dt.days_in_month
    return g[g["days"] == full].drop(columns="days")
