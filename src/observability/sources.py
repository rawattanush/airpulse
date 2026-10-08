"""The operational sources of AirPulse and where their records live. Static facts only: no network, no state.

A source is listed here only if the operational pipeline fetches it. Everything else that the project has examined
(GDELT, aviation data, Reddit, X and so on) is research-only or not connected; those are listed, with evidence,
in research/data_pipeline_sources.csv and shown by the dashboard as RESEARCH ONLY or NOT CONNECTED."""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OPS_DIR = os.path.join(ROOT, "operations")
INGESTION_LOG = os.path.join(OPS_DIR, "ingestion_log.jsonl")
FORECAST_LEDGER = os.path.join(OPS_DIR, "forecast_ledger.jsonl")
FORECAST_OUTCOMES = os.path.join(OPS_DIR, "forecast_outcomes.jsonl")
STATUS_FILE = os.path.join(OPS_DIR, "status.json")
RESEARCH_REGISTRY = os.path.join(ROOT, "research", "data_pipeline_sources.csv")

# Friendly names of the eight BLS series (the technical identifiers stay in the details and the methodology).
SERIES_NAMES = {
    "IC1312": "Asia → US air freight", "IC1311": "Europe → US air freight", "IC131": "All inbound US air freight",
    "IS2311": "US → Europe air freight", "IS2312": "US → Asia air freight", "IS231": "All outbound US air freight",
    "IV131": "All US import air freight (BoP)", "IV1311": "Europe import air freight (BoP)",
}

# cadence_days: how often a new publication is expected at the source, as established in the project's own evidence:
#   fuel   EIA publishes the week's daily spot prices once a week (requirement REQ-DATA-007; research/data_audit.md)
#   bls    the import and export price indexes are released once a month, mid-month (the stored release calendar)
#   news   the trade publications publish on working days; the job is scheduled once a day
# check_days: the longest gap between two scheduled looks (for the monthly indexes: from the 22nd to the 9th of the next month).
# grace: multiple of check_days after which a source is STALE.
_FUEL = {"group": "fuel", "kind": "eia_series", "cadence_days": 7, "check_days": 7, "grace": 2.0, "registry_id": None, "production": True}
_BLS = {"group": "bls", "kind": "bls_releases", "cadence_days": 31, "check_days": 19, "grace": 1.5, "registry_id": "SRC-09", "production": True}
_NEWS = {"group": "news", "kind": "news_wordpress", "cadence_days": 1, "check_days": 1, "grace": 3.0, "production": False}

SOURCES = {
    "eia_jet_fuel": {**_FUEL, "name": "US Gulf Coast jet fuel (EIA)", "series": "EER_EPJK_PF4_RGC_DPG", "registry_id": "SRC-01",
                     "url": "https://www.eia.gov/dnav/pet/hist_xls/EER_EPJK_PF4_RGC_DPGd.xls", "file": "SRC-01_eia_EER_EPJK_PF4_RGC_DPG.csv"},
    "eia_brent": {**_FUEL, "name": "Brent crude (EIA)", "series": "RBRTE", "registry_id": "SRC-08",
                  "url": "https://www.eia.gov/dnav/pet/hist_xls/RBRTEd.xls", "file": "SRC-08_eia_RBRTE.csv"},
    **{f"bls_{s}": {**_BLS, "name": f"{n} price index, every release (BLS {s})", "series": s,
                    "url": "https://www.bls.gov/bls/news-release/ximpim.htm", "file": f"SRC-09_bls_{s}_all_vintages.csv"} for s, n in SERIES_NAMES.items()},
    "news_aircargoweek": {**_NEWS, "name": "Air Cargo Week headlines", "series": "aircargoweek", "registry_id": "SRC-23", "url": "https://aircargoweek.com/wp-json/wp/v2/posts", "file": None},
    "news_splash247": {**_NEWS, "name": "Splash247 headlines", "series": "splash247", "registry_id": "SRC-24", "url": "https://splash247.com/wp-json/wp/v2/posts", "file": None},
}
GROUPS = ("fuel", "bls", "news")
GROUP_SCHEDULE = {   # the schedule written in the workflow files; a schedule is a definition, not evidence that anything ran
    "fuel": {"workflow": ".github/workflows/data_refresh.yml", "cron": "41 6 * * 4", "meaning": "weekly, Thursday 06:41 UTC"},
    "bls": {"workflow": ".github/workflows/data_refresh.yml", "cron": "23 14 9-22 * *", "meaning": "daily at 14:23 UTC from the 9th to the 22nd of each month (the release window)"},
    "news": {"workflow": ".github/workflows/news_ingest.yml", "cron": "17 5 * * *", "meaning": "daily, 05:17 UTC"},
}
