"""MOD-05 Feature builder (REQ-ML-005). Every feature for target month t is computed from values as known
on the issuance date I(t). The function also returns the latest availability date it used."""
import math
import numpy as np, pandas as pd
from src import config

FEATURES = ["own_chg_1", "own_chg_2", "own_chg_3", "own_chg_3m", "own_abs_1", "peers_chg_1", "peers_chg_2",
            "jet_chg_1m", "jet_chg_3m", "jet_vol_1m", "brent_chg_1m", "month_sin", "month_cos"]


def _pct(a, b):
    return 100.0 * (a / b - 1.0) if (a is not None and b is not None and b != 0 and not (np.isnan(a) or np.isnan(b))) else np.nan


def _monthly_changes(known, target_month):
    """known: as-of frame indexed by obs_date. Returns the last three month-on-month changes before the target
    month, the three-month change, and the latest availability date among the months used."""
    t = pd.Timestamp(target_month)
    m = [t - pd.DateOffset(months=k) for k in (1, 2, 3, 4)]
    v = [known["value"].get(d, np.nan) for d in m]
    used = known.loc[known.index.intersection(m), "available_date"]
    return ([_pct(v[0], v[1]), _pct(v[1], v[2]), _pct(v[2], v[3]), _pct(v[0], v[3])], used.max() if len(used) else pd.NaT)


def _fuel(known):
    """known: as-of daily frame. Changes of 21-observation means and volatility of daily log returns."""
    x = known["value"].to_numpy(dtype=float)
    if len(x) < 84: return np.nan, np.nan, np.nan
    m0, m1, m3 = x[-21:].mean(), x[-42:-21].mean(), x[-84:-63].mean()
    vol = float(np.std(np.diff(np.log(x[-22:])), ddof=1) * 100.0)
    return _pct(m0, m1), _pct(m0, m3), vol


def build_features(histories, series_id, target_month, issued_at, peers, jet=config.JET_FUEL, brent=config.BRENT_CRUDE):
    """histories: {series_id: History}. Returns (dict of features, max information date as 'YYYY-MM-DD')."""
    info = []
    own, d = _monthly_changes(histories[series_id].asof(issued_at), target_month); info.append(d)
    p1, p2 = [], []
    for p in peers:
        ch, d = _monthly_changes(histories[p].asof(issued_at), target_month)
        p1.append(ch[0]); p2.append(ch[1]); info.append(d)
    jk = histories[jet].asof(issued_at); bk = histories[brent].asof(issued_at)
    j1, j3, jv = _fuel(jk); b1, _, _ = _fuel(bk)
    for k in (jk, bk):
        if len(k): info.append(k["available_date"].max())
    month = pd.Timestamp(target_month).month
    f = {"own_chg_1": own[0], "own_chg_2": own[1], "own_chg_3": own[2], "own_chg_3m": own[3],
         "own_abs_1": abs(own[0]) if not np.isnan(own[0]) else np.nan,
         "peers_chg_1": float(np.nanmean(p1)) if np.any(~np.isnan(p1)) else np.nan,
         "peers_chg_2": float(np.nanmean(p2)) if np.any(~np.isnan(p2)) else np.nan,
         "jet_chg_1m": j1, "jet_chg_3m": j3, "jet_vol_1m": jv, "brent_chg_1m": b1,
         "month_sin": math.sin(2 * math.pi * month / 12), "month_cos": math.cos(2 * math.pi * month / 12)}
    info = [d for d in info if not pd.isna(d)]
    return f, (max(info).strftime("%Y-%m-%d") if info else str(issued_at)[:10])
