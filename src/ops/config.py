"""Configuration of the operational pipeline (Phase 7). Separate from src/config.py, which is frozen with the benchmark.

The operational pipeline never writes to the benchmark snapshot (research/data_samples) or to the benchmark store
(data/airpulse.sqlite). It keeps its own files under operations/ and its own derived store."""
import os
from src import config as base
from src.observability import sources

ROOT = base.ROOT
OPS_DIR = sources.OPS_DIR
RAW_DIR = os.path.join(OPS_DIR, "raw")                 # immutable raw responses, one gzip file per changed fetch
CURRENT_DIR = os.path.join(OPS_DIR, "current")         # latest verified files, in the layout the validated loader reads
NEWS_EXPORT_DIR = os.path.join(OPS_DIR, "news")        # export of the event store, so that a scheduled run does not discard it
OPS_DB_PATH = os.path.join(ROOT, "data", "airpulse_operational.sqlite")   # derived from CURRENT_DIR; never tracked

PIPELINE_VERSION = "OPS-1.0"
RUN_SCHEMA_VERSION = "RUN-1"
FORECAST_SCHEMA_VERSION = "FC-2"   # FC-2 adds source_versions, configuration_version, official_forecaster and is_official; records of FC-1 stay as issued
CONFIGURATION_VERSION = f"band {base.FLAT_BAND_PCT}; features {base.FEATURE_VERSION}; revision releases {base.REVISION_RELEASES}; fuel lag {base.FUEL_AVAILABILITY_LAG_DAYS} days"
ON_TIME_DAYS = 3            # a forecast generated within this many days after its issuance date is ON_TIME, otherwise LATE
HTTP_TIMEOUT = 90
HTTP_ATTEMPTS = 3           # bounded: at most three requests per URL
HTTP_BACKOFF = (5, 20)      # seconds before the second and the third attempt
REQUEST_PAUSE = 2.0         # seconds between requests to the same host


def http_headers():
    """What every request of the pipeline says about its client. The contact is where the operator can be reached: the
    address in AIRPULSE_CONTACT when the operator sets one, otherwise the hosted repository that runs the job. No personal
    address is built in."""
    repo = os.environ.get("GITHUB_REPOSITORY")
    contact = os.environ.get("AIRPULSE_CONTACT") or (f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/{repo}" if repo else "operator not configured")
    return {"User-Agent": f"AirPulse/{PIPELINE_VERSION} (scheduled data refresh, one request at a time; contact: {contact})",
            "Accept": "text/html,application/json;q=0.9,*/*;q=0.8", "Accept-Language": "en"}
