"""MOD-01 Ingestion: verify snapshot files and parse them into observation records.
REQ-DATA-001, 002, 006, 007; REQ-REL-001. Values are never altered."""
import hashlib, json, os
import numpy as np, pandas as pd


class IngestionError(Exception):
    """Raised with the name of the offending file."""


def verify_file(path):
    """Return the sidecar metadata after checking the file's SHA-256 against it."""
    name = os.path.basename(path)
    if not os.path.exists(path): raise IngestionError(f"{name}: file missing")
    if not os.path.exists(path + ".meta.json"): raise IngestionError(f"{name}: metadata sidecar missing")
    with open(path + ".meta.json", encoding="utf-8") as f: meta = json.load(f)
    with open(path, "rb") as f: digest = hashlib.sha256(f.read()).hexdigest()
    if digest != meta.get("sha256"): raise IngestionError(f"{name}: SHA-256 does not match its metadata")
    return meta


def parse_vintage_matrix(path):
    """Vintage matrix (rows = observation months, columns = releases) -> (records, vintage_dates, withdrawn).
    records: (obs_date, vintage_date, value) for every value that is new or changed in that vintage."""
    name = os.path.basename(path)
    try:
        df = pd.read_csv(path, index_col=0)
        obs = pd.to_datetime(df.index).strftime("%Y-%m-%d")
        vint = [pd.Timestamp(c.rsplit("_", 1)[1]).strftime("%Y-%m-%d") for c in df.columns]
        vals = df.apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    except Exception as e:
        raise IngestionError(f"{name}: cannot parse ({type(e).__name__}: {e})")
    if vint != sorted(vint) or len(set(vint)) != len(vint): raise IngestionError(f"{name}: vintage columns not strictly increasing")
    records, withdrawn = [], 0
    prev = np.full(vals.shape[0], np.nan)
    for j, vd in enumerate(vint):
        cur = vals[:, j]
        changed = ~np.isnan(cur) & (np.isnan(prev) | (cur != prev))
        withdrawn += int((np.isnan(cur) & ~np.isnan(prev)).sum())
        records += [(obs[i], vd, float(cur[i])) for i in np.flatnonzero(changed)]
        prev = np.where(np.isnan(cur), prev, cur)
    return records, vint, withdrawn


def parse_fuel(path, lag_days):
    """Daily two-column file -> (obs_date, available_date, value); available = obs + lag_days (REQ-DATA-007)."""
    name = os.path.basename(path)
    try:
        df = pd.read_csv(path); df.columns = ["d", "v"]
        df["d"] = pd.to_datetime(df["d"]); df["v"] = pd.to_numeric(df["v"], errors="coerce")
    except Exception as e:
        raise IngestionError(f"{name}: cannot parse ({type(e).__name__}: {e})")
    rows_in_file, duplicates = len(df), int(df["d"].duplicated().sum())
    df = df.dropna(subset=["v"]).drop_duplicates("d", keep="first")
    avail = df["d"] + pd.Timedelta(days=lag_days)
    records = list(zip(df["d"].dt.strftime("%Y-%m-%d"), avail.dt.strftime("%Y-%m-%d"), df["v"].astype(float)))
    return records, {"rows_in_file": rows_in_file, "duplicates": duplicates}
