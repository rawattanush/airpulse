"""News-adjusted outlook (CL-028, protocol 7.0): the press is read without keeping a headline, a failed reading changes
nothing, the trained model is applied beside the official outlook and never in its place, and a source whose terms are
not established is published only on the owner's recorded decision. No network."""
import json, os
import pytest, yaml

from src import config
from src.press import reading as press
from src.observability import policy, records

ROOT = config.ROOT
P = lambda *a: os.path.join(ROOT, *a)
T0 = __import__("datetime").datetime(2026, 10, 9, 12, 0, 0, tzinfo=__import__("datetime").timezone.utc)
TITLES = ["Lufthansa Cargo cuts freighter capacity to Asia as demand weakens", "Air freight rates from Shanghai surge ahead of peak season", "Airline orders two new aircraft"]


def _fetch(pub, base, after=None, max_pages=None, log=None):
    return [{"source_id": pub, "native_id": str(100 + i), "url": f"{base}/article-{i}/", "title_raw": t, "published_utc": f"2026-10-0{i + 1}T08:00:00Z", "modified_utc": f"2026-10-0{i + 1}T08:00:00Z", "fetched_at": "2026-10-09T12:00:00Z"}
            for i, t in enumerate(TITLES)]


def test_NOT1_a_reading_keeps_parsed_events_and_no_headline(tmp_path):
    rec = press.read_source("press_aircargoweek", str(tmp_path), fetch=_fetch, now=lambda: T0)
    assert rec["result"] == "UPDATED" and rec["record_count"] == 3 and rec["latest_observation"] == "2026-10-03T08:00:00Z" and "headline text not stored" in rec["validation"]
    text = open(press.path_of("press_aircargoweek", str(tmp_path)), encoding="utf-8").read(); body = json.loads(text)
    for t in TITLES:
        assert t not in text and t.lower() not in text.lower()                                        # no headline, in any case
    assert "title" not in text and "matched_text" not in text and '"pattern"' not in text              # nor the fragment a rule matched
    kinds = [m["event_type"] for a in body["articles"] for m in a["mentions"]]; assert "AIR_CAPACITY_REDUCTION" in kinds and len(body["articles"]) == 3
    assert all(set(a) == {"article_id", "source_id", "url", "published_utc", "text_hash", "mentions"} for a in body["articles"])
    again = press.read_source("press_aircargoweek", str(tmp_path), fetch=_fetch, now=lambda: T0); assert again["result"] == "UNCHANGED" and open(press.path_of("press_aircargoweek", str(tmp_path)), encoding="utf-8").read() == text


def test_NOT2_a_failed_empty_or_invalid_reading_changes_nothing(tmp_path):
    press.read_source("press_aircargoweek", str(tmp_path), fetch=_fetch, now=lambda: T0); path = press.path_of("press_aircargoweek", str(tmp_path)); before = open(path, "rb").read()
    def down(*a, **k): raise OSError("no route to host")
    elsewhere = lambda pub, base, **k: [{**r, "url": "https://example.org/x"} for r in _fetch(pub, base)]
    old = lambda pub, base, **k: [{**r, "published_utc": "2019-01-01T00:00:00Z"} for r in _fetch(pub, base)]
    for fetch, word in ((down, "OSError"), (lambda *a, **k: [], "no article in the window"), (elsewhere, "not at the publication's address"), (old, "outside the window")):
        rec = press.read_source("press_aircargoweek", str(tmp_path), fetch=fetch, now=lambda: T0)
        assert rec["result"] == "FAILED" and word in rec["error"] and open(path, "rb").read() == before and rec["latest_observation"] == "2026-10-03T08:00:00Z"     # the reading held stays, and is still reported
    log = str(tmp_path / "log.jsonl"); out = press.refresh(str(tmp_path), log, trigger="test", fetch=down, now=lambda: T0)
    assert [r["result"] for r in out] == ["FAILED", "FAILED"] and not records.verify(log) and len(records.read(log)) == 2                                          # one record per source whatever happened


def test_NOT3_the_model_is_applied_beside_the_official_outlook_and_never_changes_it(tmp_path):
    from src.press import outlook as news_tilt
    press.refresh(str(tmp_path), str(tmp_path / "log.jsonl"), fetch=_fetch, now=lambda: T0); led = P("operations", "forecast_ledger.jsonl"); before = open(led, "rb").read()
    out = news_tilt.live(press_dir=str(tmp_path), out_path=str(tmp_path / "outlook.json")); official = [r for r in records.read(led) if r["series"] == config.PRIMARY_SERIES and r.get("is_official")][-1]
    assert open(led, "rb").read() == before                                                                                                                       # the ledger of the official outlook is only read
    assert out["experimental"] is True and out["baseline"]["probabilities"] == {k: official["probabilities"][k] for k in ("down", "flat", "up")} and out["baseline"]["prediction"] == official["prediction"]
    p = out["news_adjusted"]["probabilities"]; assert abs(sum(p.values()) - 1) < 1e-9 and out["news_adjusted"]["prediction"] in config.CLASSES and out["news_adjusted"]["as_of"] == "2026-10-09T12:00:00Z"
    assert len(out["news_adjusted"]["by_group"]) == 6 and all(abs(sum(g["shift_points"].values())) < 0.31 for g in out["news_adjusted"]["by_group"])                 # a shift moves probability between directions
    text = open(tmp_path / "outlook.json", encoding="utf-8").read()
    for t in TITLES: assert t not in text
    assert all(e["url"].startswith("https://") and "title" not in e for e in out["events"]) and out["events_in_window"] >= 2
    first = os.path.getmtime(tmp_path / "outlook.json"); news_tilt.live(press_dir=str(tmp_path), out_path=str(tmp_path / "outlook.json")); assert os.path.getmtime(tmp_path / "outlook.json") == first   # unchanged readings, unchanged file
    assert news_tilt.live(press_dir=str(tmp_path / "empty"), out_path=str(tmp_path / "none.json")) is None and not os.path.exists(tmp_path / "none.json")           # no reading held: nothing is written, nothing is invented


def test_NOT4_terms_not_established_are_published_only_on_the_owners_recorded_decision():
    pol = policy.load(); feat = pol["features"]["news_adjusted_outlook"]; srcs = [pol["sources"][i] for i in press.SOURCES]
    assert feat["status"] == "PRODUCTION READY" and set(press.SOURCES) <= set(feat["sources"]) and policy.feature_refusal("news_adjusted_outlook", pol) is None
    for s in srcs:
        assert s["license_class"] == policy.OWNER and "CL-028" in s["owner_decision"] and "not stored" in s["owner_decision"] and policy.refusal(s) is None
        assert "licence class OWNER-ACCEPTED without a recorded decision" in policy.refusal({**s, "owner_decision": ""}) and policy.refusal({**s, "license_class": "UNKNOWN"}) == "licence class UNKNOWN"
    for i in ("news_aircargoweek", "news_splash247"): assert policy.refusal(pol["sources"][i])                                                                     # the headline archive stays research
    assert policy.feature_refusal("event_intelligence", pol)
    import importlib.util
    spec = importlib.util.spec_from_file_location("deployment_checks", P("scripts", "deployment_checks.py")); dc = importlib.util.module_from_spec(spec); spec.loader.exec_module(dc)
    assert dc.policy_ids() == policy.publishable_sources(pol) and set(press.SOURCES) <= set(dc.policy_ids())                                                     # the check before an upload reads the policy by the same rule


def test_NOT5_the_stored_test_says_what_its_ledger_says_and_the_rule_was_fixed_first():
    import pandas as pd
    res = json.load(open(P("evaluation", "news_tilt_results.json"), encoding="utf-8")); led = pd.read_csv(P("evaluation", "news_tilt_ledger.csv"), keep_default_na=False); sc = led[led["STATUS"] == "SCORED"]
    for fid, m in res["metrics"].items():
        g = sc[sc["FORECASTER"] == fid]; assert len(g) == m["n"] == res["scored_months"] and abs((g["PREDICTION"] == g["ACTUAL"]).mean() - m["hit_rate"]) < 1e-12
    c = res["comparison"]; assert c["news_adds_value"] == (c["T1_vs_SEA"]["better"] and c["T1_vs_T0"]["better"]) and c["news_adds_value"] is False
    tab = pd.read_csv(P("evaluation", "news_tilt_training.csv")); assert list(tab.columns)[:2] == ["target_month", "issued_at"] and len(tab) >= res["train_n_last_origin"] and not any("title" in c for c in tab.columns)
    proto = open(P("evaluation", "validation_protocol_v7.md"), encoding="utf-8").read(); assert "PRE-REGISTERED" in proto and "SEA remains the official outlook" in proto
