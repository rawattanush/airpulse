"""MOD-02 Validation: data-quality checks on parsed records (REQ-DATA-005). Pure functions; no storage."""
import pandas as pd


def check_bls(records, vintage_dates, withdrawn, monthly_era_start):
    """records: (obs_date, vintage_date, value). Returns a list of (check_name, value, detail)."""
    df = pd.DataFrame(records, columns=["obs", "vint", "value"])
    months = pd.to_datetime(pd.Series(sorted(df["obs"].unique())))
    era = months[months >= pd.Timestamp(monthly_era_start)]
    expected = pd.date_range(era.min(), era.max(), freq="MS")
    missing = [d.strftime("%Y-%m") for d in expected.difference(pd.DatetimeIndex(era))]
    first = df.groupby("obs")["vint"].min()
    observed = first[first > vintage_dates[0]].sort_index()          # months whose first release is observed
    increasing = bool(observed.is_monotonic_increasing and observed.is_unique)
    dup = int(df.duplicated(["obs", "vint"]).sum())
    return [("duplicate_observation_dates", dup, "rows sharing (observation month, vintage)"),
            ("missing_months_in_monthly_era", len(missing), ",".join(missing)),
            ("non_positive_values", int((df["value"] <= 0).sum()), "values <= 0"),
            ("release_dates_strictly_increasing", int(increasing), f"{len(observed)} observed first releases"),
            ("values_withdrawn_in_later_vintage", withdrawn, "value present in one vintage and empty in the next"),
            ("vintage_count", len(vintage_dates), f"{vintage_dates[0]}..{vintage_dates[-1]}"),
            ("monthly_values_latest", int(len(era)), f"{era.min():%Y-%m}..{era.max():%Y-%m}")]


def check_fuel(records, info):
    df = pd.DataFrame(records, columns=["obs", "avail", "value"])
    gap = pd.to_datetime(df["obs"]).diff().dt.days.max()
    return [("duplicate_observation_dates", info["duplicates"], "duplicate dates in the file"),
            ("missing_rows_in_file", info["rows_in_file"] - len(df) - info["duplicates"], "dates with no quoted value"),
            ("non_positive_values", int((df["value"] <= 0).sum()), "values <= 0"),
            ("longest_gap_days", int(gap), "days between consecutive values"),
            ("observation_count", len(df), f"{df['obs'].min()}..{df['obs'].max()}")]
