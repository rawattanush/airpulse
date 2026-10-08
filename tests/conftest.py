"""Shared fixtures. Tests run against a store built from the real snapshot in a temporary directory,
so they never touch data/airpulse.sqlite."""
import os, sys
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src import config                      # noqa: E402
from src.database import store              # noqa: E402
from src.ingestion.build import build_store  # noqa: E402


RESEARCH_RECORD = os.path.isdir(os.path.join(ROOT, "execution"))       # the registers, audits and evidence of the research repository


def pytest_collection_modifyitems(config, items):
    """The hosted repository holds the engine and its state, not the research record: tests of that record are skipped there, by name and with the reason."""
    if RESEARCH_RECORD: return
    skip = pytest.mark.skip(reason="checks the research record, which is not part of the hosted repository")
    for item in items:
        if item.get_closest_marker("research_record"): item.add_marker(skip)


@pytest.fixture(scope="session")
def db_path(tmp_path_factory):
    p = str(tmp_path_factory.mktemp("store") / "airpulse.sqlite")
    build_store(p)
    return p


@pytest.fixture(scope="session")
def conn(db_path):
    c = store.connect(db_path)
    yield c
    c.close()


@pytest.fixture(scope="session")
def backtest_primary(conn):
    """Backtest of the primary series only, without touching the exported registers."""
    from src.api.backtest import run_backtest
    run_id, n = run_backtest(conn, [config.PRIMARY_SERIES], export=False)
    return run_id, n
