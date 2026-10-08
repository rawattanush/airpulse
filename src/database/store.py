"""MOD-03 Canonical store: connection, schema creation and as-of reads (REQ-DATA-003, REQ-DATA-004)."""
import os, sqlite3
import pandas as pd

SCHEMA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")


def connect(path):
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_schema(conn):
    with open(SCHEMA, encoding="utf-8") as f:
        conn.executescript(f.read())


def asof(conn, series_id, as_of_date):
    """Each observation's value as it was available on as_of_date. Returns a frame indexed by obs_date
    (Timestamp) with columns value and available_date. Observations not yet published are absent."""
    q = """SELECT o.obs_date, o.value, o.available_date FROM observations o
           JOIN (SELECT obs_date, MAX(available_date) AS m FROM observations
                 WHERE series_id = ? AND available_date <= ? GROUP BY obs_date) x
             ON o.obs_date = x.obs_date AND o.available_date = x.m
           WHERE o.series_id = ? ORDER BY o.obs_date"""
    df = pd.read_sql_query(q, conn, params=(series_id, str(as_of_date)[:10], series_id), parse_dates=["obs_date", "available_date"])
    return df.set_index("obs_date")


class History:
    """In-memory copy of one series' revision log; same answer as asof() without a query per call."""

    def __init__(self, conn, series_id):
        self.series_id = series_id
        self.log = pd.read_sql_query("SELECT obs_date, available_date, value FROM observations WHERE series_id = ? ORDER BY available_date, obs_date",
                                     conn, params=(series_id,), parse_dates=["obs_date", "available_date"])

    def asof(self, as_of_date):
        known = self.log[self.log["available_date"] <= pd.Timestamp(as_of_date)]
        return known.groupby("obs_date").last()          # log is ordered by available_date, so last = latest known


def table(conn, name, where="", params=()):
    return pd.read_sql_query(f"SELECT * FROM {name} {where}", conn, params=params)
