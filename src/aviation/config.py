"""Aviation operations layer (change record CL-017; protocol evaluation/validation_protocol_v4.md).

An experimental layer beside the validated system: nothing here is read by the benchmark, by the official forecast or by
the experiments of protocols 2.0 and 3.0. Three things are kept apart everywhere:
  A. observed activity            flights or movements a source reports
  B. inferred pressure            baselines, anomalies and the capacity PROXY computed from A
  C. forecast of a freight price  not produced here; tested in the ablation and promoted only by the rule
No number in this package is a cargo capacity. Weights of the capacity proxy are fixed, declared values."""
import os
from src import config as base

PROTOCOL_VERSION = "4.0"
SCHEMA_VERSION = "1.0"                    # canonical flight schema
PROCESSING_VERSION = "1.0"                # aggregation, baseline and anomaly rules
REFERENCE_DIR = os.path.join(base.ROOT, "data", "reference")
SNAPSHOT_DIR = os.path.join(base.ROOT, "research", "aviation_data", "v4")          # historical snapshots, each file with a sidecar
OPS_DIR = os.path.join(base.ROOT, "operations", "aviation")                        # machine-written: raw archive of the collector, logs, event store
EVAL_DIR = os.path.join(base.EVAL_DIR, "aviation")
RESEARCH_DIR = os.path.join(base.ROOT, "research")

CATEGORIES = ("passenger_narrowbody", "passenger_widebody", "freighter_narrowbody", "freighter_widebody", "regional", "general", "unknown")
EVENT_TYPES = ("departure", "arrival", "airborne", "cancellation", "diversion", "unknown")
FLIGHT_FIELDS = ("flight_id", "source", "source_record_id", "event_type", "callsign", "registration", "aircraft_icao24", "aircraft_type", "aircraft_category", "origin", "destination",
                 "origin_country", "destination_country", "scheduled_departure", "estimated_departure", "actual_departure", "scheduled_arrival", "actual_arrival", "latitude", "longitude",
                 "altitude", "velocity", "heading", "timestamp", "ingestion_timestamp", "data_version", "source_hash")

# Capacity PROXY schemes (protocol 4.0, section 5). Declared weights, not measurements: relative units per movement.
# A counts movements; B weights by body and role; C counts widebodies only; D counts freighters only.
SCHEMES = {
    "A": {c: 1.0 for c in CATEGORIES},
    "B": {"passenger_narrowbody": 1.0, "passenger_widebody": 4.0, "freighter_narrowbody": 5.0, "freighter_widebody": 20.0, "regional": 0.3, "general": 0.0, "unknown": 1.0},
    "C": {"passenger_narrowbody": 0.0, "passenger_widebody": 1.0, "freighter_narrowbody": 0.0, "freighter_widebody": 1.0, "regional": 0.0, "general": 0.0, "unknown": 0.0},
    "D": {"passenger_narrowbody": 0.0, "passenger_widebody": 0.0, "freighter_narrowbody": 1.0, "freighter_widebody": 4.0, "regional": 0.0, "general": 0.0, "unknown": 0.0},
}

# Anomaly bands on |z| (protocol 4.0, section 6): descriptive, declared before any anomaly was computed.
BANDS = (("NORMAL", 0.0), ("ELEVATED", 1.0), ("UNUSUAL", 2.0), ("EXTREME", 3.0))
BASELINE = {"same_weekday_weeks": 8, "min_history": 6, "seasonal_years": 3, "seasonal_window_days": 10, "min_expected": 5.0, "min_std_share": 0.05}
DETECTOR = {"collapse_ratio": -0.5, "surge_ratio": 0.5, "route_min_expected": 8.0, "cancellation_min": 5}

# Corridors: origin regions -> destination regions. Route weights are historical shares from an earlier window (never the target).
CORRIDORS = {"South Asia to Europe": (("South Asia",), ("Europe",)), "South Asia to North America": (("South Asia",), ("North America",)), "South Asia to Middle East": (("South Asia",), ("Middle East",)),
             "East Asia to North America": (("East Asia",), ("North America",)), "East Asia to Europe": (("East Asia",), ("Europe",)),
             "Asia to North America": (("East Asia", "Southeast Asia", "South Asia"), ("North America",))}
SHARE_WINDOW_MONTHS = 24

# Freshness: when a feed counts as live, recent, delayed or stale (hours since the newest observation)
MODES = (("LIVE", 0.25), ("RECENT", 48.0), ("DELAYED", 24.0 * 14))        # older than the last bound: STALE; no observation: UNAVAILABLE; fixed history: HISTORICAL

# Monthly features for the screening ablation: publication lag in days after the reference month (declared; no release history is held)
LAG_DAYS = {"european_airports": 60, "us_international_departures": 240}
LEADS = (0, 1, 2, 3)                      # months by which activity precedes the target change in the lead-lag table
FIRST_SCORED = "2016-01-01"

# Known disruptions (protocol 4.0, section 7): written from the public record before the detector was run. (name, class, ICAO codes, first day, last day)
KNOWN_DISRUPTIONS = (
    ("Brussels Airport closed after the attack", "closure", ("EBBR",), "2016-03-22", "2016-04-02"),
    ("Dublin: operations suspended in snow", "closure", ("EIDW",), "2018-03-01", "2018-03-02"),
    ("Gatwick: runway closed after drone sightings", "closure", ("EGKK",), "2018-12-20", "2018-12-20"),
    ("Pandemic collapse of traffic", "closure", ("EDDF", "EHAM", "EGLL", "LFPG", "LEMD"), "2020-03-16", "2020-03-31"),
    ("Ukrainian airspace closed", "closure", ("UKBB",), "2022-02-24", "2022-03-02"),
    ("Brussels Airport: national strike", "closure", ("EBBR",), "2022-06-20", "2022-06-20"),
    ("German airports: strike of 17 February 2023", "closure", ("EDDF", "EDDM", "EDDH"), "2023-02-17", "2023-02-17"),
    ("German airports: strike of 27 March 2023", "closure", ("EDDF", "EDDM"), "2023-03-27", "2023-03-27"),
    ("Munich: closed in snow", "closure", ("EDDM",), "2023-12-02", "2023-12-02"),
    ("Heathrow closed after a power failure", "closure", ("EGLL",), "2025-03-21", "2025-03-21"),
    ("Storm over the Netherlands", "partial", ("EHAM",), "2022-02-18", "2022-02-18"),
    ("UK air traffic control failure", "partial", ("EGLL", "EGKK"), "2023-08-28", "2023-08-28"),
    ("Frankfurt: strike of 7 March 2024", "partial", ("EDDF",), "2024-03-07", "2024-03-07"),
    ("Worldwide IT outage", "partial", ("EHAM", "EDDB"), "2024-07-19", "2024-07-19"),
    ("Iberian power failure", "partial", ("LPPT", "LEMD"), "2025-04-28", "2025-04-28"),
)
PANDEMIC = ("2020-03-01", "2021-06-30")   # excluded from the false-alarm count
STATUS_RULE = {"min_recall_closure": 0.80, "max_false_alarm_share": 0.05, "proxy_min_spearman": 0.60, "coverage_band": 0.10, "coverage_min_months_share": 0.90,
               "monitor_max_age_days": 60, "monitor_min_coverage": 0.70}
