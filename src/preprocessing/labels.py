"""MOD-04 Calendar and labels (REQ-ML-001 to 004). Pure functions over a series' revision log."""
import numpy as np, pandas as pd


def direction(pct, band):
    if pct is None or np.isnan(pct): return None
    return "UP" if pct > band else "DOWN" if pct < -band else "FLAT"


def release_calendar(records, vintage_dates, revision_releases, monthly_era_start):
    """One row per observation month of the monthly era: first_release_date, whether that release is observed
    (the month is not already in the earliest vintage), and final_date = the vintage `revision_releases` after it."""
    df = pd.DataFrame(records, columns=["obs", "vint", "value"])
    first = df.groupby("obs")["vint"].min()
    first = first[first.index >= monthly_era_start[:10]]
    pos = {v: i for i, v in enumerate(vintage_dates)}
    rows = []
    for obs, fr in first.items():
        k = pos[fr] + revision_releases
        rows.append((obs, fr, int(fr > vintage_dates[0]), vintage_dates[k] if k < len(vintage_dates) else None))
    return pd.DataFrame(rows, columns=["obs_month", "first_release_date", "first_release_observed", "final_date"])


def _asof(df, date):
    known = df[df["vint"] <= date].sort_values("vint")
    return known.groupby("obs")["value"].last()


def build_labels(records, calendar, band):
    """FINAL and REALTIME labels for every month with an observed first release.
    A label is undefined (None) when the month or its predecessor was not published; nothing is imputed."""
    df = pd.DataFrame(records, columns=["obs", "vint", "value"])
    months = pd.date_range(calendar["obs_month"].min(), calendar["obs_month"].max(), freq="MS").strftime("%Y-%m-%d")
    cal = calendar.set_index("obs_month")
    out = []
    for t in months:
        prev = (pd.Timestamp(t) - pd.offsets.MonthBegin(1)).strftime("%Y-%m-%d")
        if t not in cal.index:                                   # month never published
            out += [(t, "FINAL", None, None, None), (t, "REALTIME", None, None, None)]; continue
        c = cal.loc[t]
        if not c["first_release_observed"]: continue             # first release predates the vintage archive
        for kind, date in (("REALTIME", c["first_release_date"]), ("FINAL", c["final_date"])):
            if date is None or pd.isna(date): continue           # not final yet: no row
            known = _asof(df, date)
            pct = 100.0 * (known[t] / known[prev] - 1.0) if (t in known.index and prev in known.index) else None
            out.append((t, kind, pct, direction(pct, band), date if pct is not None else None))
    return pd.DataFrame(out, columns=["target_month", "kind", "pct_change", "label", "label_date"])


def issuance_dates(calendar):
    """target month -> issuance date = observed first release of the previous month (REQ-ML-001).
    A month whose own first release is not later than that date has none: when one release is the first record of two
    consecutive months, the second cannot be forecast from the record (CL-024; the condition of the leakage check, applied at issuance)."""
    cal = calendar[calendar["first_release_observed"] == 1]
    nxt = (pd.to_datetime(cal["obs_month"]) + pd.offsets.MonthBegin(1)).dt.strftime("%Y-%m-%d")
    own = dict(zip(calendar["obs_month"], calendar["first_release_date"]))
    return {t: d for t, d in zip(nxt, cal["first_release_date"]) if not (t in own and own[t] <= d)}
