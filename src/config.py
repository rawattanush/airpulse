"""MOD-10 Configuration. The single place for constants (REQ-MNT-002). Values marked FROZEN come from
research/data_feasibility_decision.md and must not change without a change record."""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAPSHOT_DIR = os.path.join(ROOT, "research", "data_samples")
DB_PATH = os.path.join(ROOT, "data", "airpulse.sqlite")
EVAL_DIR = os.path.join(ROOT, "evaluation")

# BLS air freight price indexes, one column per release of the Bureau (rebuilt from its archived releases, CL-024): series id -> (title, snapshot file)
BLS_SERIES = {
    "IC1312": ("Inbound Air Freight, Asia (Asia to US)", "SRC-09_bls_IC1312_all_vintages.csv"),
    "IC1311": ("Inbound Air Freight, Europe (Europe to US)", "SRC-09_bls_IC1311_all_vintages.csv"),
    "IC131": ("Inbound Air Freight, all", "SRC-09_bls_IC131_all_vintages.csv"),
    "IS2311": ("Outbound Air Freight, Europe (US to Europe)", "SRC-09_bls_IS2311_all_vintages.csv"),
    "IS2312": ("Outbound Air Freight, Asia (US to Asia)", "SRC-09_bls_IS2312_all_vintages.csv"),
    "IS231": ("Outbound Air Freight, all", "SRC-09_bls_IS231_all_vintages.csv"),
    "IV131": ("Import (BoP) Air Freight, all", "SRC-09_bls_IV131_all_vintages.csv"),
    "IV1311": ("Import (BoP) Air Freight, Europe", "SRC-09_bls_IV1311_all_vintages.csv"),
}
PRIMARY_SERIES = "IC1312"                      # FROZEN
FUEL_SERIES = {                                 # the Energy Information Administration's own source keys (CL-024)
    "EER_EPJK_PF4_RGC_DPG": ("Jet fuel, US Gulf Coast, USD per gallon", "SRC-01_eia_EER_EPJK_PF4_RGC_DPG.csv"),
    "RBRTE": ("Brent crude, USD per barrel", "SRC-08_eia_RBRTE.csv"),
}
JET_FUEL, BRENT_CRUDE = "EER_EPJK_PF4_RGC_DPG", "RBRTE"

FLAT_BAND_PCT = 0.5                            # FROZEN: |change| <= band -> FLAT
REVISION_RELEASES = 3                          # FROZEN: BLS revises a value in the 3 releases after the first
MONTHLY_ERA_START = "2005-12-01"               # series are quarterly before this month
FUEL_AVAILABILITY_LAG_DAYS = 8                 # REQ-DATA-007: weekly EIA release
FIRST_TEST_MONTH = "2016-01-01"                # REQ-ML-009
MIN_TRAIN_LABELS = 36                          # REQ-ML-014 (DD-08)
RANDOM_SEED = 20261003
FEATURE_VERSION = "F1"
CLASSES = ("DOWN", "FLAT", "UP")               # fixed order of probability columns
