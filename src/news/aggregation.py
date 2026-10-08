"""Time-window aggregation of canonical events into features (REQ-NEWS-009, REQ-NEWS-010).

Everything is computed AS OF a cut-off time T from the article-level links, never from the finished canonical
event rows: an event's corroboration, severity and confidence at T use only the articles published before T,
and an event exists at T only if at least one of its articles was published before T.

Definitions (also in research/event_feature_definitions.md):
  an event is IN the window of w days at T if one of its non-duplicate articles was published in [T - w, T)
  score(event, T) = (severity / 3) * status_weight * confidence * source_weight
      severity, confidence, source_weight: maximum over the event's articles published before T
      status_weight: ACTIVE 1.0, POTENTIAL 0.5; ENDED events have no score and are counted as relief
  group feature   = sum over events in the window of direction * score, for the event types of the group
  *_rate feature  = 100 * group feature / article_count of the same window   (events per 100 archived headlines)"""
import numpy as np, pandas as pd
from src.news import config, events

SIGNED_GROUPS = ["geopolitical_shock", "air_capacity_shock", "cargo_demand_shock", "airfreight_rate_signal", "fuel_shock", "trade_flow"]
UNSIGNED_GROUPS = ["maritime_disruption", "airspace_disruption", "trade_disruption"]
GROUPS = sorted(SIGNED_GROUPS + UNSIGNED_GROUPS)
COUNTS = ["event_count", "high_severity_event_count", "potential_event_count", "relief_event_count", "corroborated_event_count", "article_count"]
EXTRA = ["shipping_diversion_pressure"]            # maritime events whose diversion_pressure effect is INCREASE
# the experimental feature group of the ablation, fixed before it was run (30-day window, rates)
NEWS_EVENT_FEATURES_V1 = [f"{g}_{config.ABLATION_WINDOW_DAYS}d_rate" for g in
                          ("geopolitical_shock", "maritime_disruption", "airspace_disruption", "air_capacity_shock", "cargo_demand_shock", "airfreight_rate_signal")]


def feature_names(windows=None):
    out = []
    for w in (windows or config.WINDOWS_DAYS):
        out += [f"{g}_{w}d" for g in GROUPS + EXTRA + COUNTS] + [f"{g}_{w}d_rate" for g in GROUPS]
    return out


class EventIndex:
    """In-memory view of the event store for fast as-of queries."""

    def __init__(self, links, articles):
        """links: frame with event_id, article_id, publication_time, event_type, feature_group, status, direction, severity,
        extraction_confidence, source_reliability, is_duplicate, category, affected_mode, diversion_pressure.
        articles: frame with article_id, published_utc, duplicate_of."""
        l = links.copy(); l["pub"] = pd.to_datetime(l["publication_time"].str.slice(0, 19))
        self.links = l[l["is_duplicate"] == 0].sort_values("pub").reset_index(drop=True)
        a = articles[articles["duplicate_of"].isna()]
        self.article_times = np.sort(pd.to_datetime(a["published_utc"].str.slice(0, 19)).to_numpy())
        self.first_article = pd.Timestamp(self.article_times[0]) if len(self.article_times) else None

    def features(self, as_of, windows=None):
        """as_of: timestamp (UTC). Returns (features dict, provenance dict feature -> sorted event ids)."""
        T = pd.Timestamp(as_of); known = self.links[self.links["pub"] < T]; feats, prov = {}, {}
        asof = known.groupby("event_id").agg(event_type=("event_type", "first"), feature_group=("feature_group", "first"), status=("status", "first"),
                                             direction=("direction", "first"), category=("category", "first"), affected_mode=("affected_mode", "first"),
                                             diversion_pressure=("diversion_pressure", "first"), severity=("severity", "max"), confidence=("extraction_confidence", "max"),
                                             weight=("source_reliability", "max"), corroboration=("article_id", "nunique"), last=("pub", "max"))
        asof["score"] = (asof["severity"] / 3.0) * asof["status"].map(events.STATUS_WEIGHT) * asof["confidence"] * asof["weight"]
        for w in (windows or config.WINDOWS_DAYS):
            start = T - pd.Timedelta(days=w); e = asof[asof["last"] >= start]; live = e[e["status"] != "ENDED"]
            n_art = int(np.searchsorted(self.article_times, T.to_datetime64(), side="left") - np.searchsorted(self.article_times, start.to_datetime64(), side="left"))
            for g in GROUPS:
                sel = live[live["feature_group"] == g]
                v = float((sel["direction"] * sel["score"]).sum()) if g in SIGNED_GROUPS else float(sel["score"].sum())
                feats[f"{g}_{w}d"] = v; feats[f"{g}_{w}d_rate"] = (100.0 * v / n_art) if n_art else float("nan"); prov[f"{g}_{w}d"] = sorted(sel.index)
            div = live[(live["category"] == "MARITIME") & (live["diversion_pressure"] == "INCREASE")]
            feats[f"shipping_diversion_pressure_{w}d"] = float(div["score"].sum()); prov[f"shipping_diversion_pressure_{w}d"] = sorted(div.index)
            feats[f"event_count_{w}d"] = int(len(live)); prov[f"event_count_{w}d"] = sorted(live.index)
            hs = live[(live["severity"] == 3) & (live["status"] == "ACTIVE")]; feats[f"high_severity_event_count_{w}d"] = int(len(hs)); prov[f"high_severity_event_count_{w}d"] = sorted(hs.index)
            feats[f"potential_event_count_{w}d"] = int((live["status"] == "POTENTIAL").sum())
            rel = e[e["status"] == "ENDED"]; feats[f"relief_event_count_{w}d"] = int(len(rel)); prov[f"relief_event_count_{w}d"] = sorted(rel.index)
            feats[f"corroborated_event_count_{w}d"] = int((live["corroboration"] >= 2).sum())
            feats[f"article_count_{w}d"] = n_art
        latest = known["pub"].max() if len(known) else pd.NaT
        feats["_latest_event_publication"] = None if pd.isna(latest) else latest.strftime("%Y-%m-%dT%H:%M:%SZ")
        return feats, prov
