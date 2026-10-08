"""Frontend adapter for observed air traffic: what the engine holds -> public/data/aviation.json.

ONLY OBSERVATION, AND ONLY WHAT THE PRODUCTION POLICY ALLOWS. Two features of the engine's policy
(config/production_sources.yaml) are exported, each only while the policy calls it PRODUCTION READY and does not refuse
its source:

  hong_kong_airport_activity   counts of flights at Hong Kong International Airport per day, from the archive of the
                               airport's own flight information: movements, cargo and passenger flights, cancellations,
                               first stops of cargo departures
  us_route_departures          monthly nonstop departures between US and foreign airports as published by the US DOT,
                               about eight months old: a historical record, never a current figure

Nothing else leaves the engine here: no expected level, no difference, no reading, no flag of unusual activity, no
capacity figure, no position picture, no result of an experiment. Those did not pass the production gate and stay in the
engine's research folders. A source limited to non-commercial reuse is never exported.

The state of each source (last fetch, newest data, stale limit, status) comes from the engine's source registry. A feed
whose archive fails a critical check is withheld and the page says so. A day the source did not cover is absent, never zero."""
import os
from datetime import datetime, timezone
import numpy as np

WINDOW_DAYS = 28            # the two windows compared in the table of first stops: the newest days archived and the same number before them
SERIES_DAYS = 120           # days of the daily series exported
TOP_ROUTES = 30             # routes exported, by departures of the newest twelve months
ROUTE_REGIONS = ("East Asia", "Southeast Asia", "South Asia")
REG_KEYS = ("status", "error", "last_success", "last_attempt", "latest_data", "stale_after_days", "data_stale_after_days", "check_every_days", "frequency", "last_trigger", "scheduled_runs", "manual_runs")
f = lambda v, d=4: None if v is None or (isinstance(v, float) and not np.isfinite(v)) else round(float(v), d)


def _collected(r):
    """How a feed is collected, said from its run records: never typed."""
    if r["scheduled_runs"] > 0 and r["last_trigger"] == "schedule": return f"Collected by a scheduled run; {r['scheduled_runs']} scheduled runs on record."
    if r["scheduled_runs"] > 0: return f"{r['scheduled_runs']} scheduled runs on record; the newest run was started by hand."
    return "Every run on record was started by hand; no scheduled run is on record."


def build(root, now=None):
    from src.aviation import activity, airports, collector, operations, routes
    from src.observability import policy, registry
    now = now or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"); pol = policy.load()
    reg = {r["id"]: r for r in registry.build(registry.parse_time(now))["sources"]}; gate = operations.quality(now=now); critical = gate["critical"]
    table = {a["airport_iata"]: a for a in airports.table()}; out = {"available": False, "generated_at": now, "sources": [], "airport": None, "routes": [], "not_shown": {}}

    def source(sid, name, kind, through):
        p, r = pol["sources"][sid], reg[sid]
        return {"id": sid, "name": name, "kind": kind, "through": through, "attribution": p["attribution"], "license_class": p["license_class"], "collected": _collected(r),
                "registry": {**{k: r[k] for k in REG_KEYS}, "status": policy.public_status(r)}}

    def refused(feature, sid):
        """Why a feature is not exported: the policy, or a critical finding of the quality gate. None when it may be exported."""
        why = policy.feature_refusal(feature, pol)
        if why: return f"Not part of the product: {why}."
        bad = critical.get("log") or critical.get(sid)
        return None if not bad else "Withheld: the data held failed a check (" + "; ".join(str(x) for x in bad) + "). Nothing is shown until the check passes."

    # ---- Hong Kong: counts from the airport's own flight information, as archived
    why = refused("hong_kong_airport_activity", "hkia")
    if why: out["not_shown"]["hong_kong_airport_activity"] = why
    else:
        recs, days = collector.load_hkia()
        if not days: out["not_shown"]["hong_kong_airport_activity"] = "No day of flight information is archived yet."
        else:
            a = table["HKG"]; daily = activity.counts(recs, "HKG", "day", covered=days).set_index("period"); order = sorted(days); last, prev = set(order[-WINDOW_DAYS:]), set(order[-2 * WINDOW_DAYS:-WINDOW_DAYS])
            cargo_dep = [r for r in recs if r["service"] == "cargo" and r["event_type"] == "departure" and r["destination"]]
            cnt = lambda ds: {k: sum(1 for r in cargo_dep if r["destination"] == k and r["timestamp"][:10] in ds) for k in {r["destination"] for r in cargo_dep}}
            c1, c0 = cnt(last), cnt(prev); stops = sorted(c1.items(), key=lambda kv: (-kv[1], kv[0]))[:15]; v = daily.iloc[-1]
            out["airport"] = {"iata": "HKG", "icao": a["airport_icao"], "name": a["airport_name"], "country": a["country"], "through": order[-1], "first_day": order[0], "days_archived": len(order), "window_days": WINDOW_DAYS,
                              "latest": {"day": daily.index[-1], "movements": int(v["movements"]), "arrivals": int(v["arrivals"]), "departures": int(v["departures"]), "cargo_movements": int(v["cargo_movements"]),
                                         "passenger_movements": int(v["passenger_movements"]), "cancellations": int(v["cancellations"])},
                              "series": [{"d": d, "m": int(r["movements"]), "c": int(r["cargo_movements"]), "p": int(r["passenger_movements"]), "x": int(r["cancellations"])} for d, r in daily.iloc[-SERIES_DAYS:].iterrows()],
                              "cancellations": {"total": int(daily["cancellations"].sum()), "days_with_any": int((daily["cancellations"] > 0).sum()), "largest_day": daily["cancellations"].idxmax(), "largest": int(daily["cancellations"].max())},
                              "cargo_first_stops": [{"airport": k, "name": (table.get(k) or {}).get("airport_name"), "last": int(n), "previous": int(c0.get(k, 0))} for k, n in stops if n > 0],
                              "previous_window_complete": len(prev) == WINDOW_DAYS}
            out["sources"].append(source("hkia", "Hong Kong International Airport: flight information", "Every flight with its status, cargo flights apart", order[-1]))
    # ---- US routes: monthly departures as published
    why = refused("us_route_departures", "usdot")
    if why: out["not_shown"]["us_route_departures"] = why
    else:
        usd = operations.us_international(); r = routes.us_routes(usd); asia = r[r["region"].isin(ROUTE_REGIONS)]; months = sorted(asia["month"].unique()); last12 = months[-12:]
        top = asia[asia["month"].isin(last12)].groupby("route")["departures"].sum().sort_values(ascending=False).head(TOP_ROUTES)
        wide = routes.complete(routes.by(asia, "route"), usd["month"].min(), usd["month"].max()); cg = routes.complete(routes.by(asia, "route", "all_cargo_departures"), usd["month"].min(), usd["month"].max())
        for route, n in top.items():
            fa, us = route.split("-"); s = wide[route]
            out["routes"].append({"id": route, "from": fa, "to": us, "from_name": table[fa]["airport_name"], "region": table[fa]["region"], "departures_last_12_months": int(n),
                                  "all_cargo_share": f(cg[route].iloc[-12:].sum() / n if n else None), "latest": {"month": wide.index[-1][:7], "departures": None if np.isnan(s.iloc[-1]) else int(s.iloc[-1])},
                                  "series": [{"m": m[:7], "a": None if np.isnan(x) else int(x)} for m, x in s.loc["2017-01-01":].items()]})
        out["route_window"] = {"months": 12, "through": months[-1][:7], "regions": list(ROUTE_REGIONS), "routes": TOP_ROUTES}
        out["sources"].append(source("usdot", "United States: nonstop international departures", "Official monthly count by airport pair and carrier; both directions together", months[-1][:7]))
    out["available"] = bool(out["airport"] or out["routes"])
    out["statement"] = "Counts of flights from official sources, as published. Nothing here is an estimate of cargo capacity, an expected level, a cause or a statement about freight prices."
    return out
