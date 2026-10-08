"""Monthly aviation features for the screening ablation (protocol 4.0, sections 2 and 9).

Information time. The sources carry no release history. A reference month enters a feature of a forecast issued on date I
only if the month ended at least L days before I (L declared per source in cfg.LAG_DAYS). The values are those of the
retrieval date, so every feature here is a screening feature. The no-lag variant (L = 0) uses months that were not yet
published at issuance: it is an upper bound and supports no claim. For every row the reference month and its assumed
availability date are recorded, and leakage_report() checks them against the issuance date."""
import numpy as np, pandas as pd
from src.aviation import activity, airports, anomaly, config as cfg, network, routes

GROUPS = {"B": ["av_hub_yoy", "av_hub_c3", "av_asia_us_yoy", "av_asia_us_c3"], "C": ["av_cargo_yoy", "av_cargo_share"], "D": ["av_hub_unusual_share", "av_hub_mean_z", "av_corridor_z"],
          "E": ["av_east_asia_yoy", "av_china_yoy", "av_japan_yoy", "av_korea_yoy", "av_south_asia_yoy"]}
GROUPS["F"] = [c for g in ("B", "C", "D", "E") for c in GROUPS[g]]
EUR, USD = "european_airports", "us_international_departures"
_ms = lambda s: pd.to_datetime(s).strftime("%Y-%m-01")


def monthly_sources(eur=None, usd=None):
    """Monthly tables behind the features, one per source (index: month start as text). Months a source does not cover completely are absent."""
    eur = activity.european_daily() if eur is None else eur; usd = activity.us_international() if usd is None else usd
    hubs = [a["airport_icao"] for a in airports.table() if a["region"] == "Europe"]; e = eur[eur["airport_icao"].isin(hubs)]
    days = e.groupby("airport_icao")["date"].nunique(); span = len(pd.date_range(e["date"].min(), e["date"].max()))
    excluded = {h: int(span - days.get(h, 0)) for h in hubs if days.get(h, 0) != span}                                  # an airport with missing days would remove its months for all: it is left out, by name
    hubs = [h for h in hubs if h not in excluded]; e = e[e["airport_icao"].isin(hubs)]
    tot = activity.monthly_total(e).pivot(index="month", columns="airport_icao", values="total").dropna()                # a month counts only when every hub has every day
    z = {}
    for h in hubs:
        s = e[e["airport_icao"] == h].set_index("date")["movements"]; sc = anomaly.daily_scores(s); z[h] = sc["z"]
    Z = pd.DataFrame(z); zm = Z.groupby(Z.index.strftime("%Y-%m")); full = Z.notna().all(axis=1).groupby(Z.index.strftime("%Y-%m")).sum() >= 25
    a = pd.DataFrame({"hub_movements": tot.sum(axis=1), "hub_unusual_share": (Z.abs() >= 2).where(Z.notna()).groupby(Z.index.strftime("%Y-%m")).mean().mean(axis=1), "hub_mean_z": zm.mean().mean(axis=1)})
    a.loc[~full.reindex(a.index).fillna(False).to_numpy(), ["hub_unusual_share", "hub_mean_z"]] = np.nan
    a = a[a["hub_movements"].notna()]; a.index = [m + "-01" for m in a.index]
    r = routes.us_routes(usd); asia = r[r["region"].isin(("East Asia", "Southeast Asia", "South Asia"))]; g = lambda d, v="departures": d.groupby("month")[v].sum()
    u = pd.DataFrame({"asia_us": g(asia), "asia_us_cargo": g(asia, "all_cargo_departures"), "east_asia": g(asia[asia["region"] == "East Asia"]), "china": g(asia[asia["country"].isin(("CN", "HK"))]),
                      "japan": g(asia[asia["country"] == "JP"]), "korea": g(asia[asia["country"] == "KR"]), "south_asia": g(asia[asia["region"] == "South Asia"])}).sort_index()
    u["cargo_share"] = u["asia_us_cargo"] / u["asia_us"]
    wide = routes.complete(routes.by(asia, "route"), u.index.min(), u.index.max()); ix = network.index(wide); u["corridor_z"] = ix["z"].reindex(u.index); u["corridor_index"] = ix["index"].reindex(u.index)
    return {EUR: a.sort_index(), USD: u, "meta": {"european_hubs": hubs, "excluded_for_missing_days": excluded}}


def latest_month(issued_at, lag_days):
    """The newest month that ended at least `lag_days` days before the issuance date."""
    I = pd.Timestamp(issued_at); m = (I - pd.Timedelta(days=lag_days)).to_period("M")
    if (m.to_timestamp(how="end").normalize() + pd.Timedelta(days=lag_days)) > I: m = m - 1
    return m.to_timestamp().strftime("%Y-%m-01")


def _chg(t, col, m, k):
    a, b = t[col].get(m, np.nan), t[col].get((pd.Timestamp(m) - pd.DateOffset(months=k)).strftime("%Y-%m-01"), np.nan)
    return 100.0 * (a / b - 1.0) if b and not np.isnan(a) and not np.isnan(b) else np.nan


def build(frame, sources, lags=None, suffix=""):
    """Aviation columns for every row of a forecast frame (needs issued_at). lags: {source: days}; default the declared lags. suffix marks a variant."""
    lags = cfg.LAG_DAYS if lags is None else lags; E, U = sources[EUR], sources[USD]; rows = []
    for I in frame["issued_at"]:
        me, mu = latest_month(I, lags[EUR]), latest_month(I, lags[USD]); end = lambda m, L: (pd.Timestamp(m) + pd.offsets.MonthEnd(0) + pd.Timedelta(days=L)).strftime("%Y-%m-%d")
        x = {"av_hub_yoy": _chg(E, "hub_movements", me, 12), "av_hub_c3": _chg(E, "hub_movements", me, 3), "av_hub_unusual_share": E["hub_unusual_share"].get(me, np.nan), "av_hub_mean_z": E["hub_mean_z"].get(me, np.nan),
             "av_asia_us_yoy": _chg(U, "asia_us", mu, 12), "av_asia_us_c3": _chg(U, "asia_us", mu, 3), "av_cargo_yoy": _chg(U, "asia_us_cargo", mu, 12), "av_cargo_share": U["cargo_share"].get(mu, np.nan),
             "av_corridor_z": U["corridor_z"].get(mu, np.nan), **{f"av_{k}_yoy": _chg(U, k, mu, 12) for k in ("east_asia", "china", "japan", "korea", "south_asia")}}
        x = {k + suffix: v for k, v in x.items()}
        x.update({f"av_eur_reference{suffix}": me if me in E.index else None, f"av_eur_available{suffix}": end(me, lags[EUR]) if me in E.index else None,
                  f"av_usd_reference{suffix}": mu if mu in U.index else None, f"av_usd_available{suffix}": end(mu, lags[USD]) if mu in U.index else None})
        rows.append(x)
    return pd.DataFrame(rows, index=frame.index)


def leakage_report(frame, suffix="", strict=True):
    """Rows whose aviation inputs break the information-time rule. strict: the assumed availability date must not be after the issuance (declared lag);
    in every variant the reference month must be over before the issuance. `violations` must be empty."""
    viol = []
    for r in frame.itertuples():
        for src in ("eur", "usd"):
            ref, av = getattr(r, f"av_{src}_reference{suffix}"), getattr(r, f"av_{src}_available{suffix}")
            if not isinstance(ref, str): continue
            if (pd.Timestamp(ref) + pd.offsets.MonthEnd(0)) >= pd.Timestamp(r.issued_at): viol.append((r.target_month, f"{src}: reference month not over at issuance", ref))
            if strict and av > r.issued_at: viol.append((r.target_month, f"{src}: assumed availability after issuance", av))
    cols = [c for c in frame.columns if c.startswith("av_") and c.endswith(("_reference" + suffix,))]
    age = {c: int(((pd.to_datetime(frame["target_month"]).dt.to_period("M") - pd.to_datetime(frame[c]).dt.to_period("M")).dropna().map(lambda p: p.n)).median()) for c in cols if frame[c].notna().any()}
    return {"rows": int(len(frame)), "violations": viol, "median_age_months_of_reference": age, "rows_with_values": {c: int(frame[c].notna().sum()) for c in cols}}
