-- AirPulse canonical schema (design/database/schema.md). SQLite. Dates are ISO strings (YYYY-MM-DD).
CREATE TABLE source_files (
    file_id       INTEGER PRIMARY KEY,
    file_name     TEXT NOT NULL UNIQUE,
    source_id     TEXT NOT NULL,            -- research/source_registry.csv
    url           TEXT NOT NULL,
    sha256        TEXT NOT NULL,
    retrieved_at  TEXT NOT NULL
);
CREATE TABLE series (
    series_id     TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    kind          TEXT NOT NULL CHECK (kind IN ('BLS_INDEX', 'FUEL')),
    frequency     TEXT NOT NULL,
    file_id       INTEGER NOT NULL REFERENCES source_files(file_id)
);
-- revision log: one row each time a value first appears or changes
CREATE TABLE observations (
    series_id       TEXT NOT NULL REFERENCES series(series_id),
    obs_date        TEXT NOT NULL,
    available_date  TEXT NOT NULL,          -- vintage date (BLS) or obs_date + 8 days (fuel)
    value           REAL NOT NULL,
    file_id         INTEGER NOT NULL REFERENCES source_files(file_id),
    PRIMARY KEY (series_id, obs_date, available_date)
);
CREATE INDEX ix_obs_available ON observations(series_id, available_date);
CREATE TABLE vintages (
    series_id     TEXT NOT NULL REFERENCES series(series_id),
    vintage_date  TEXT NOT NULL,
    PRIMARY KEY (series_id, vintage_date)
);
CREATE TABLE releases (
    series_id            TEXT NOT NULL REFERENCES series(series_id),
    obs_month            TEXT NOT NULL,
    first_release_date   TEXT NOT NULL,
    first_release_observed INTEGER NOT NULL CHECK (first_release_observed IN (0, 1)),  -- 0: month already present in the earliest vintage
    final_date           TEXT,              -- date of the 4th vintage holding the month; NULL until then
    PRIMARY KEY (series_id, obs_month)
);
CREATE TABLE labels (
    series_id     TEXT NOT NULL REFERENCES series(series_id),
    target_month  TEXT NOT NULL,
    kind          TEXT NOT NULL CHECK (kind IN ('FINAL', 'REALTIME')),
    pct_change    REAL,
    label         TEXT CHECK (label IN ('UP', 'FLAT', 'DOWN')),   -- NULL = undefined (unpublished month); never imputed
    label_date    TEXT,                     -- date the label became known
    PRIMARY KEY (series_id, target_month, kind)
);
CREATE TABLE data_quality_results (
    result_id   INTEGER PRIMARY KEY,
    series_id   TEXT NOT NULL REFERENCES series(series_id),
    check_name  TEXT NOT NULL,
    value       REAL NOT NULL,
    detail      TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
CREATE TABLE model_versions (
    forecaster_id  TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    kind           TEXT NOT NULL CHECK (kind IN ('BASELINE', 'MODEL')),
    version        TEXT NOT NULL,
    params_json    TEXT NOT NULL
);
CREATE TABLE forecast_runs (
    run_id         INTEGER PRIMARY KEY,
    started_at     TEXT NOT NULL,
    finished_at    TEXT,
    config_json    TEXT NOT NULL,
    snapshot_hash  TEXT NOT NULL,
    code_hash      TEXT NOT NULL,
    n_forecasts    INTEGER
);
CREATE TABLE forecasts (
    forecast_id            TEXT PRIMARY KEY,           -- series|forecaster|target month
    run_id                 INTEGER NOT NULL REFERENCES forecast_runs(run_id),
    series_id              TEXT NOT NULL REFERENCES series(series_id),
    forecaster_id          TEXT NOT NULL REFERENCES model_versions(forecaster_id),
    forecaster_version     TEXT NOT NULL,
    feature_version        TEXT NOT NULL,
    snapshot_hash          TEXT NOT NULL,
    target_month           TEXT NOT NULL,
    issued_at              TEXT NOT NULL,
    max_feature_info_time  TEXT NOT NULL,
    target_time            TEXT NOT NULL,              -- first release of the target month (nominal if not yet released)
    p_down REAL, p_flat REAL, p_up REAL,
    predicted              TEXT,
    actual                 TEXT,                       -- final label
    correct                INTEGER,
    actual_realtime        TEXT,
    correct_realtime       INTEGER,
    n_train                INTEGER NOT NULL,
    status                 TEXT NOT NULL CHECK (status IN ('SCORED', 'PENDING', 'UNSCORABLE', 'SKIPPED', 'FAILED')),
    message                TEXT NOT NULL DEFAULT ''
);
CREATE INDEX ix_fc_series ON forecasts(series_id, forecaster_id, target_month);
CREATE TABLE evaluation_results (
    run_id         INTEGER NOT NULL REFERENCES forecast_runs(run_id),
    series_id      TEXT NOT NULL REFERENCES series(series_id),
    forecaster_id  TEXT NOT NULL REFERENCES model_versions(forecaster_id),
    label_kind     TEXT NOT NULL CHECK (label_kind IN ('FINAL', 'REALTIME')),
    period         TEXT NOT NULL,
    metric         TEXT NOT NULL,
    value          REAL,
    n              INTEGER NOT NULL,
    PRIMARY KEY (series_id, forecaster_id, label_kind, period, metric)
);
