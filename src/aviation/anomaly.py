"""Expected activity, surplus or deficit, and anomaly (protocol 4.0, section 6).

Every baseline uses earlier periods only. A baseline that cannot be formed is missing, a ratio against an expected value
below the minimum is not computed, and no result is ever infinite. Bands are descriptive and fixed in the protocol."""
import numpy as np, pandas as pd
from src.aviation import config as cfg

B = cfg.BASELINE


def band(z):
    """NORMAL, ELEVATED, UNUSUAL or EXTREME for a z value; None when z is not available."""
    if z is None or not np.isfinite(z): return None
    name = cfg.BANDS[0][0]
    for n, lo in cfg.BANDS:
        if abs(z) >= lo: name = n
    return name


def score(actual, reference):
    """One comparison of an observed value with its reference values (earlier comparable periods).
    Returns expected, spread, difference, ratio, z, band, direction; every part None when it cannot be computed."""
    ref = np.asarray([v for v in reference if v is not None and np.isfinite(v)], dtype=float)
    out = {"actual": None if actual is None or not np.isfinite(actual) else float(actual), "expected": None, "spread": None, "difference": None, "ratio": None, "z": None, "band": None, "direction": None, "reference_values": int(len(ref))}
    if out["actual"] is None or len(ref) < B["min_history"]: return out
    e = float(np.median(ref)); s = max(1.4826 * float(np.median(np.abs(ref - e))), B["min_std_share"] * e); d = out["actual"] - e
    out.update(expected=e, difference=d, direction="SURPLUS" if d > 0 else "DEFICIT" if d < 0 else "NONE")
    if e >= B["min_expected"]: out["ratio"] = d / e
    if s > 0: out.update(spread=s, z=d / s, band=band(d / s))
    return out


def _matrix(s, shifts):
    return np.column_stack([s.shift(k, freq="D").reindex(s.index).to_numpy(dtype=float) for k in shifts])


def daily_scores(series, method="rolling"):
    """Scores of every day of one daily series (index: dates; a missing day is missing, not zero).
    rolling: the same weekday in the previous 8 weeks. seasonal: the same weekday within 10 days of the date in each of the previous 3 years."""
    s = pd.Series(series, dtype=float).sort_index(); s.index = pd.to_datetime(s.index); s = s[~s.index.duplicated()].asfreq("D")
    if method == "rolling": shifts = [7 * k for k in range(1, B["same_weekday_weeks"] + 1)]
    elif method == "seasonal": shifts = [364 * y + 7 * j for y in range(1, B["seasonal_years"] + 1) for j in (-1, 0, 1) if abs(7 * j) <= B["seasonal_window_days"]]
    else: raise ValueError(method)
    M = _matrix(s, shifts); n = (~np.isnan(M)).sum(axis=1); ok = n >= B["min_history"]
    M0 = np.where(ok[:, None], M, 0.0)                                       # rows without a baseline are computed on zeros and masked afterwards
    e0 = np.nanmedian(M0, axis=1); e = np.where(ok, e0, np.nan); mad = np.where(ok, np.nanmedian(np.abs(M0 - e0[:, None]), axis=1), np.nan)
    a = s.to_numpy(); sp = np.maximum(1.4826 * mad, B["min_std_share"] * e); d = a - e
    with np.errstate(all="ignore"):
        ratio = np.where(e >= B["min_expected"], d / e, np.nan); z = np.where(sp > 0, d / sp, np.nan)
    out = pd.DataFrame({"actual": a, "expected": e, "spread": sp, "difference": d, "ratio": ratio, "z": z, "reference_values": n}, index=s.index)
    out.loc[out["actual"].isna() | ~ok, ["expected", "spread", "difference", "ratio", "z"]] = np.nan
    out["band"] = [band(v) for v in out["z"]]
    return out


def monthly_scores(series):
    """Scores of a monthly series (index: month starts) against the same month of the previous 3 years; all three are needed."""
    s = pd.Series(series, dtype=float).sort_index(); s.index = pd.to_datetime(s.index); rows = []
    for m, a in s.items():
        ref = [s.get(m - pd.DateOffset(years=y), np.nan) for y in range(1, B["seasonal_years"] + 1)]; r = {"actual": a, "expected": np.nan, "spread": np.nan, "difference": np.nan, "ratio": np.nan, "z": np.nan}
        if not np.isnan(a) and not np.isnan(ref).any():
            e = float(np.median(ref)); sp = max(1.4826 * float(np.median(np.abs(np.array(ref) - e))), B["min_std_share"] * e); d = a - e
            r.update(expected=e, spread=sp, difference=d, ratio=d / e if e >= B["min_expected"] else np.nan, z=d / sp if sp > 0 else np.nan)
        rows.append(r)
    out = pd.DataFrame(rows, index=s.index); out["band"] = [band(v) for v in out["z"]]
    return out


def statement(code, sc, unit="movements", proxy=False):
    """The surplus or deficit of one airport and period in words. Returns None when there is no baseline: nothing is said instead of a guess.
    A count of flights of any kind is ACTIVITY. Only a value of the capacity proxy (proxy=True) is named as such; nothing is ever named capacity."""
    if sc.get("expected") is None or sc.get("actual") is None or (isinstance(sc["expected"], float) and np.isnan(sc["expected"])): return None
    pct = "" if sc.get("ratio") is None or np.isnan(sc["ratio"]) else f" ({100 * sc['ratio']:+.1f}%)"
    kind = "CAPACITY PROXY" if proxy else "ACTIVITY"
    return f"{code}: observed {sc['actual']:.0f} {unit}, expected {sc['expected']:.0f}, difference {sc['difference']:+.0f}{pct}: {kind} {'SURPLUS' if sc['difference'] > 0 else 'DEFICIT' if sc['difference'] < 0 else 'AS EXPECTED'}"
