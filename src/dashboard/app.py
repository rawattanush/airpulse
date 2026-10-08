"""MOD-09 Dashboard (REQ-USE-001 to 004, REQ-NEWS-014, REQ-DASH-001 to 004). Run:  streamlit run src/dashboard/app.py

It reads the local stores and the run records, fetches nothing and starts no ingestion. If the derived benchmark
store is absent (a fresh clone, a deployed copy) it is rebuilt once from the frozen snapshot; nothing else is written.
The validated target is the BLS series IC1312 (air freight from Asia into the United States), a public proxy;
on screen the lanes carry plain names and the technical identifiers are listed in the Methodology view.
Nothing here is live: every forecast shown comes from the stored data, and every freshness statement is
derived from the ingestion run log and the clock (src/dashboard/data.py, src/observability/health.py).
Labels on screen: HISTORICAL and BACKTEST for the validated replay of history, SNAPSHOT / AUTOMATED / LIVE for the
data mode of the sources, EXPERIMENTAL for the event layer and the two models, RESEARCH for unconnected sources."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import altair as alt
import pandas as pd
import streamlit as st
from src import config
from src.api import backtest as bt
from src.dashboard import data as dd
from src.database import store
from src.observability import health, sources

YELLOW, DEEP, SKY, CLOUD, WHITE, NAVY, MUTED, GREY = "#FFC928", "#123B5D", "#6FAED6", "#F5F8FA", "#FFFFFF", "#102A43", "#627D98", "#9FB3C8"
CLASS_COLOURS = alt.Scale(domain=["down", "flat (within ±0.5%)", "up"], range=[DEEP, GREY, YELLOW])
STATE_COLOURS = {"LIVE": "#1B7F4B", "AUTOMATED": DEEP, "SNAPSHOT": MUTED, "HISTORICAL": NAVY, "BACKTEST": NAVY, "EXPERIMENTAL": "#9A6A00", "RESEARCH": MUTED,
                 "HEALTHY": "#1B7F4B", "STALE": "#9A6A00", "FAILED": "#B42318", "NOT CONFIGURED": MUTED, "RESEARCH ONLY": MUTED, "NOT CONNECTED": MUTED}
PROXY_STATEMENT = dd.PROXY_STATEMENT                      # "... It is a US-lane proxy, not a South Asia to Europe rate. ..."

st.set_page_config(page_title="AirPulse", layout="wide")
st.markdown(f"""<style>
.block-container {{padding-top: 2.2rem;}}
h1, h2, h3 {{color: {NAVY};}}
.ap-brand {{display:flex; align-items:baseline; gap:.75rem; border-bottom:4px solid {YELLOW}; padding-bottom:.4rem; margin-bottom:.8rem;}}
.ap-brand .name {{font-size:1.9rem; font-weight:700; color:{DEEP}; letter-spacing:.01em;}}
.ap-brand .tag {{color:{MUTED}; font-size:.95rem;}}
.ap-card {{background:{CLOUD}; border-left:5px solid {DEEP}; border-radius:6px; padding:.75rem 1rem; height:100%;}}
.ap-card .k {{color:{MUTED}; font-size:.72rem; letter-spacing:.08em; text-transform:uppercase;}}
.ap-card .v {{color:{NAVY}; font-size:1.25rem; font-weight:650; line-height:1.3;}}
.ap-card .s {{color:{MUTED}; font-size:.82rem;}}
.ap-badge {{display:inline-block; border-radius:4px; padding:.05rem .45rem; font-size:.72rem; font-weight:650; letter-spacing:.05em; color:{WHITE}; vertical-align:middle;}}
</style>""", unsafe_allow_html=True)


def badge(state):
    return f'<span class="ap-badge" style="background:{STATE_COLOURS.get(state, MUTED)}">{state}</span>'


def card(col, key, value, sub="", accent=DEEP):
    col.markdown(f'<div class="ap-card" style="border-left-color:{accent}"><div class="k">{key}</div><div class="v">{value}</div><div class="s">{sub}</div></div>', unsafe_allow_html=True)


def section(state, title):
    st.subheader(f"{state} — {title}")


def day(ts):
    return "never" if not ts else pd.Timestamp(ts[:10]).strftime("%d %b %Y")


def month(ym):
    return pd.Timestamp(ym[:7] + "-01").strftime("%b %Y")


st.markdown('<div class="ap-brand"><span class="name">AirPulse</span><span class="tag">air-freight price-index direction · validated backtest, snapshot data</span></div>', unsafe_allow_html=True)
st.warning(PROXY_STATEMENT)

if not os.path.exists(config.DB_PATH):
    # A fresh clone or a deployed copy has no derived store. It is rebuilt from the frozen snapshot (no network), which takes about two minutes.
    with st.spinner("First start: building the store from the frozen data snapshot and running the walk-forward backtest (about two minutes, once)."):
        try: dd.ensure_store()
        except Exception as e:
            st.error(f"The store could not be built ({type(e).__name__}: {e}). Run `python -m src.cli build-db` and then `python -m src.cli backtest`."); st.stop()
conn = store.connect(config.DB_PATH)
VIEWS = ["Overview", "Forecasts", "Market Intelligence", "Replay", "Models", "Data Health", "Methodology"]
view = st.sidebar.radio("View", VIEWS)
series = st.sidebar.selectbox("Lane (price index)", list(config.BLS_SERIES), format_func=lambda s: dd.series_label(s) + (" · validated target" if s == config.PRIMARY_SERIES else ""))
forecaster = st.sidebar.selectbox("Forecaster", list(dd.NAMES), index=2, format_func=lambda f: f"{dd.NAMES[f]} · {dd.KIND[f].lower()}")
st.sidebar.caption("HISTORICAL / BACKTEST: produced by replaying history with only the data available at each issuance date. SNAPSHOT: data fetched by hand, shown with its retrieval date. "
                   "AUTOMATED: fetched by a scheduler that has recently run. EXPERIMENTAL: not validated. Nothing in AirPulse is live.")
fc_all = dd.forecasts(conn, series)
if fc_all.empty: st.info("No forecasts stored for this lane. Run the backtest."); st.stop()
state = dd.data_state()
MODE_TEXT = {"SNAPSHOT": "Snapshot", "AUTOMATED": "Automated", "LIVE": "Live"}
TRIGGER_TEXT = {"seed": "copied from the benchmark snapshot (a manual fetch)", "manual": "started by hand", "manual-dispatch": "started by hand on GitHub", "schedule": "started by a scheduler", None: "no run recorded"}


def prob_chart(fc):
    d = fc.dropna(subset=["p_up"]).assign(month=lambda x: pd.to_datetime(x["target_month"]))[["month", "p_down", "p_flat", "p_up"]]
    d = d.rename(columns={"p_down": "down", "p_flat": "flat (within ±0.5%)", "p_up": "up"}).melt("month", var_name="direction", value_name="probability")
    return alt.Chart(d).mark_area().encode(x=alt.X("month:T", title="target month"), y=alt.Y("probability:Q", stack="normalize", title="forecast probability"),
                                           color=alt.Color("direction:N", scale=CLASS_COLOURS, legend=alt.Legend(orient="top", title=None)),
                                           order=alt.Order("direction:N"), tooltip=["month:T", "direction:N", alt.Tooltip("probability:Q", format=".2f")]).properties(height=260)


def prob_bars(row):
    d = pd.DataFrame({"direction": ["down", "flat (within ±0.5%)", "up"], "probability": [row["p_down"], row["p_flat"], row["p_up"]]})
    base = alt.Chart(d).encode(y=alt.Y("direction:N", sort=["up", "flat (within ±0.5%)", "down"], title=None), x=alt.X("probability:Q", scale=alt.Scale(domain=[0, 1]), title="forecast probability"))
    return (base.mark_bar(size=26).encode(color=alt.Color("direction:N", scale=CLASS_COLOURS, legend=None)) + base.mark_text(align="left", dx=5, color=NAVY).encode(text=alt.Text("probability:Q", format=".0%"))).properties(height=140)


if view == "Overview":
    latest = dd.latest_forecast(conn, series); head = latest[latest["forecaster_id"] == "BL-SEA"].iloc[0]; led, _ = dd.ops_ledger()
    c = st.columns(3)
    card(c[0], "Data mode", MODE_TEXT[state["data_mode"]], "inputs of the forecast: fuel prices and BLS indexes", YELLOW if state["data_mode"] == "SNAPSHOT" else DEEP)
    card(c[1], "Latest ingestion", day(state["latest_ingestion"]), TRIGGER_TEXT.get(state["latest_ingestion_trigger"], state["latest_ingestion_trigger"]))
    pend = int((fc_all[fc_all["forecaster_id"] == "BL-SEA"]["status"] == "PENDING").sum())
    card(c[2], "Forecast status", "Historical / pending" if pend else "Historical", f"newest target month {month(head['target_month'])}; {pend} month(s) await the published outcome")
    st.caption(f"Scheduled runs recorded: {state['scheduled_runs']}. Runs started by hand: {state['manual_runs']}. "
               + ("No scheduler has run yet, so the data are a snapshot and stay as old as their retrieval date until someone refreshes them." if state["scheduled_runs"] == 0 else ""))
    section("HISTORICAL", f"{dd.series_label(series)}: newest forecast in the store, {month(head['target_month'])}")
    a, b = st.columns([2, 3])
    with a:
        st.markdown(f"**{dd.NAMES['BL-SEA']}** {badge('BACKTEST')} &nbsp; the strongest benchmark", unsafe_allow_html=True)
        st.altair_chart(prob_bars(head), use_container_width=True)
        st.caption(f"Forecast: {head['predicted']}. Issued {day(head['issued_at'])} from data published by that date. Kind of value: {head['value_kind']}. "
                   "Direction of the monthly change of the price index: up or down by more than 0.5%, otherwise flat.")
    with b:
        t = latest[["forecaster", "kind", "predicted", "p_down", "p_flat", "p_up", "value_kind"]].rename(columns={"kind": "role", "predicted": "forecast", "p_down": "P(down)", "p_flat": "P(flat)", "p_up": "P(up)", "value_kind": "kind of value"})
        st.dataframe(t.round(2), use_container_width=True, hide_index=True)
        st.caption("Benchmarks are simple calendar and persistence rules. The two models are experimental: " + dd.BENCHMARK_SENTENCE)
    section("HISTORICAL", "what the validated backtest shows")
    mt = dd.model_table(conn, config.PRIMARY_SERIES)
    if not mt.empty:
        k = st.columns(4); sea = mt.loc["BL-SEA"]; ml = mt[mt["role"] == "Experimental model"]
        card(k[0], "Validated target", "Asia → US air freight", "monthly direction of the BLS price index (a public proxy)")
        card(k[1], "Strongest benchmark", f"{sea['hit rate']:.3f} hit rate", f"{dd.NAMES['BL-SEA']}; {int(sea['months scored'])} months")
        card(k[2], "Best experimental model", f"{ml['hit rate'].max():.3f} hit rate", "below the seasonal benchmark", MUTED)
        hs = [h for h in state["sources"] if h["group"] in ("fuel", "bls")]
        card(k[3], "Forecast-input sources", f"{sum(h['status'] == 'HEALTHY' for h in hs)} of {len(hs)} healthy", f"data mode: {MODE_TEXT[state['data_mode']].lower()}")
    st.caption(dd.BENCHMARK_SENTENCE + " The comparison is on the Models page.")
    section("SNAPSHOT" if state["data_mode"] == "SNAPSHOT" else state["data_mode"], "operational forecast ledger")
    if led.empty: st.info("No operational forecast has been issued. `python -m src.ops.cli run` issues the forecast of the newest target month and appends it to an append-only ledger.")
    else:
        l1 = led[led["target_period"] == led["target_period"].max()]; r = l1[(l1["series"] == series) & (l1["forecaster_id"] == "BL-SEA")]
        st.markdown(f"{len(led)} forecasts issued; newest target month **{month(l1['target_period'].iloc[0])}**, issuance date {day(l1['issuance_date'].iloc[0])}, generated {day(l1['generated_at'].iloc[0])} "
                    f"({'on time' if l1['timing'].iloc[0] == 'ON_TIME' else 'late: generated after its issuance date from data as published by that date'}). "
                    + (f"For this lane the seasonal benchmark says **{r['prediction'].iloc[0]}**. " if len(r) else "") + "Outcome: " + ("published." if l1["actual_final"].notna().any() else "pending."))
    section("EXPERIMENTAL", "what AirPulse does not do")
    st.markdown("- It does **not** forecast South Asia → Europe air-freight rates. No public historical series for that lane was obtained.\n"
                "- It does **not** run live. Data are refreshed when a person or a scheduler starts the pipeline.\n"
                "- Its two models do **not** beat the seasonal benchmark.\n"
                "- News events are extracted by fixed rules, are experimental, and are **not used by the forecasts**.")

elif view == "Forecasts":
    fc = fc_all[fc_all["forecaster_id"] == forecaster]; last = fc.iloc[-1]
    section("HISTORICAL · BACKTEST", f"{dd.series_label(series)} — newest forecast, {month(last['target_month'])}")
    c = st.columns(5)
    c[0].metric("Forecast direction", last["predicted"] or "—"); c[1].metric("P(down)", f"{last['p_down']:.2f}"); c[2].metric("P(flat, within ±0.5%)", f"{last['p_flat']:.2f}")
    c[3].metric("P(up)", f"{last['p_up']:.2f}"); c[4].metric("Kind of value", dd.value_kind(last))
    snap = store.table(conn, "source_files")
    st.caption(f"{dd.NAMES[forecaster]} ({dd.KIND[forecaster].lower()}). Issued {last['issued_at']} from data available on that date; trained on {last['n_train']} months with final outcomes. "
               f"Snapshot retrieved {snap['retrieved_at'].max()[:10]}. This is a replay of history, not a live forecast. Technical series: {series}.")
    section("HISTORICAL · BACKTEST", "forecast probabilities over time")
    st.altair_chart(prob_chart(fc), use_container_width=True)
    section("HISTORICAL · BACKTEST", "forecast history against the published outcome")
    t = fc[["target_month", "issued_at", "p_down", "p_flat", "p_up", "predicted", "actual", "correct", "actual_realtime", "n_train", "status"]].copy()
    t["target_month"] = t["target_month"].str[:7]; t["correct"] = t["correct"].map({1: "yes", 0: "no"}).fillna(""); t["status"] = [dd.value_kind(r) for _, r in fc.iterrows()]
    st.dataframe(t.rename(columns={"predicted": "forecast", "actual": "observed (final)", "actual_realtime": "observed (first release)", "status": "kind of value", "issued_at": "issued"}).iloc[::-1], use_container_width=True, hide_index=True)
    st.caption("Forecast: produced at the issuance date. Observed: the direction published later by BLS (first release, and final after three revisions). Pending: the outcome is not yet published.")
    led, outs = dd.ops_ledger()
    section("SNAPSHOT" if state["data_mode"] == "SNAPSHOT" else state["data_mode"], "operational forecast ledger (append-only)")
    if led.empty: st.info("No operational forecast has been issued yet.")
    else:
        l = led[led["series"] == series][["target_period", "forecaster_name", "prediction", "p_down", "p_flat", "p_up", "issuance_date", "generated_at", "timing", "data_cutoff", "train_n", "actual_realtime", "actual_final", "value_kind"]]
        st.dataframe(l.rename(columns={"target_period": "target month", "forecaster_name": "forecaster", "prediction": "forecast", "issuance_date": "issuance date", "generated_at": "generated", "data_cutoff": "data cut-off",
                                       "train_n": "training months", "actual_realtime": "observed (first release)", "actual_final": "observed (final)", "value_kind": "kind of value"}).round(3), use_container_width=True, hide_index=True)
        st.caption("A forecast in this ledger is never changed after it is issued; its outcome is added to a separate file when BLS publishes it. LATE means the forecast was generated more than three days after its issuance date, from data as published by that date.")

elif view == "Market Intelligence":
    # Experimental event-intelligence layer (REQ-NEWS-014). It is not an input of any forecast shown in the other views.
    from src.news import config as ncfg, provenance
    st.subheader("EXPERIMENTAL — Market Intelligence (experimental event layer)")
    pv = dd.parser_validation()
    st.caption("Events are extracted from trade-press headlines by fixed rules; no language model is involved. This layer exists to test whether news adds predictive value. "
               "It is not used by the forecasts in the other views. In its first test the event features added no predictive value.")
    if pv:
        c = st.columns(4)
        card(c[0], "Parser status", pv["status"].title(), f"configuration {pv['configuration']}", "#9A6A00")
        card(c[1], "Precision (held-out)", f"{pv['precision']:.2f}", f"of the events it emits, on {pv['held_out_headlines']} held-out headlines")
        card(c[2], "Recall (held-out)", f"{pv['recall']:.2f}", "of the events in the reference annotation")
        card(c[3], "Reference annotation", "Not independently verified", "one annotation, no annotator recorded", MUTED)
    if not os.path.exists(ncfg.NEWS_DB_PATH):
        ev, meta = dd.event_export()
        if ev is None: st.info("Event store not found. Run `python -m src.news.cli build`.")
        else:
            st.subheader("EXPERIMENTAL — recent canonical events")
            st.caption(f"From the exported event store (operations/news): archive to {meta['latest_article'][:10]}, taxonomy {meta['taxonomy_version']}, parser {meta['parser_version']}.")
            st.dataframe(ev.sort_values("publication_time", ascending=False).head(200)[["publication_time", "parent_category", "event_type", "status", "severity", "source_id", "corroboration_count", "first_headline", "source_url"]], use_container_width=True, hide_index=True)
    else:
        nconn = provenance.connect(); meta = dict(nconn.execute("SELECT key, value FROM build_meta").fetchall())
        last = nconn.execute("SELECT MAX(published_utc) FROM raw_articles").fetchone()[0]; days = st.slider("Days shown", 7, 90, 30)
        start = (pd.Timestamp(last[:19]) - pd.Timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        ev = pd.read_sql_query("""SELECT e.publication_time, e.parent_category AS category, e.event_type, e.status, e.severity, e.geographic_scope, e.countries, e.regions,
                                         e.source_id AS source, e.corroboration_count AS corroboration, a.title_clean AS first_headline, e.source_url
                                  FROM canonical_events e JOIN raw_articles a ON a.url = e.source_url WHERE e.last_publication_time >= ? ORDER BY e.publication_time DESC""", nconn, params=(start,))
        ev["where"] = [", ".join(json.loads(c) + json.loads(r)) or "unknown" for c, r in zip(ev["countries"], ev["regions"])]
        nh = {h["source"]: h for h in state["sources"] if h["group"] == "news"}
        st.caption(f"Headline archive to {last[:10]}; taxonomy {meta['taxonomy_version']}, parser {meta['parser_version']}. {len(ev)} canonical events in the last {days} days of the archive. "
                   "Times are publication times of the first article; the time of the event itself is not established by the parser. "
                   + " ".join(f"{h['name']}: {h['status'].lower()}, last successful run {day(h['last_successful_fetch'])}." for h in nh.values()))
        st.subheader("EXPERIMENTAL — recent canonical events")
        st.dataframe(ev[["publication_time", "category", "event_type", "status", "severity", "where", "source", "corroboration", "first_headline", "source_url"]], use_container_width=True, hide_index=True)
        st.subheader("EXPERIMENTAL — event timeline (events first reported per week, by category)")
        tl = pd.read_sql_query("SELECT publication_time, parent_category FROM canonical_events WHERE status != 'ENDED' AND publication_time >= ?", nconn,
                               params=((pd.Timestamp(last[:19]) - pd.Timedelta(days=365)).strftime("%Y-%m-%dT%H:%M:%SZ"),))
        if not tl.empty:
            tl["week"] = pd.to_datetime(tl["publication_time"].str.slice(0, 10)).dt.to_period("W").dt.start_time
            g = tl.groupby(["week", "parent_category"]).size().reset_index(name="events")
            st.altair_chart(alt.Chart(g).mark_bar().encode(x=alt.X("week:T", title="week of first report"), y=alt.Y("events:Q", title="events first reported"),
                                                           color=alt.Color("parent_category:N", title="category", scale=alt.Scale(range=[DEEP, SKY, YELLOW, MUTED, GREY, NAVY]), legend=alt.Legend(orient="top")),
                                                           tooltip=["week:T", "parent_category:N", "events:Q"]).properties(height=260), use_container_width=True)
        st.subheader("EXPERIMENTAL — aggregated disruption indicators")
        from src.news import aggregation
        feats, _ = provenance.load_index(nconn).features(pd.Timestamp(last[:10]) + pd.Timedelta(days=1), windows=[7, 30])
        rows = [{"indicator": g, "last 7 days": round(feats[f"{g}_7d"], 3), "last 30 days": round(feats[f"{g}_30d"], 3)} for g in aggregation.GROUPS + aggregation.EXTRA + aggregation.COUNTS]
        st.dataframe(pd.DataFrame(rows), use_container_width=False, hide_index=True)
        st.caption("Indicator definitions: research/event_feature_definitions.md. Signed indicators: positive means tighter capacity, stronger demand, higher rates or more conflict. "
                   "Because the parser misses events and emits some that are not events, these indicators undercount and are noisy.")

elif view == "Replay":
    section("HISTORICAL · BACKTEST", "replay: what did AirPulse know at this point in time?")
    months = sorted(fc_all["target_month"].unique(), reverse=True)
    target = st.selectbox("Target month", months, format_func=lambda m: month(m), index=min(4, len(months) - 1))
    nconn = None
    try:
        from src.news import config as ncfg, provenance
        if os.path.exists(ncfg.NEWS_DB_PATH): nconn = provenance.connect()
    except Exception: nconn = None
    b = dd.replay_bundle(conn, series, target, nconn)
    c = st.columns(4)
    card(c[0], "1 · Issuance time", day(b["issuance_date"]), f"forecast of {month(b['target_month'])} for {b['series_name']}")
    card(c[1], "Newest information used", day(b["latest_information_date"]), "publication date of the newest input")
    card(c[2], "Target first published", day(b["target_first_release"]) if b["outcome_first_release"]["label"] else "not yet published", "after the issuance time", MUTED)
    card(c[3], "Leakage check", "Passed" if b["leakage_check"]["passed"] else "FAILED", "no input was published after the issuance time", "#1B7F4B" if b["leakage_check"]["passed"] else "#B42318")
    st.markdown("#### 2 · Data available then")
    st.dataframe(b["available_then"], use_container_width=True, hide_index=True)
    st.caption("Reference period: the month or day a value describes. Published: the date it became available. A forecast uses a value only if it was published by the issuance time. "
               "\"Value as revised later\" was published after the issuance time and was not used; it is shown to make the difference visible.")
    st.markdown("#### 3 · Features available then")
    st.dataframe(b["features"], use_container_width=True, hide_index=True)
    st.markdown("#### 4 · Forecast")
    f = b["forecasts"].drop(columns="forecaster_id").rename(columns={"p_down": "P(down)", "p_flat": "P(flat)", "p_up": "P(up)", "predicted": "forecast", "n_train": "training months"})
    st.dataframe(f.round(3), use_container_width=True, hide_index=True)
    if st.button("Recompute this forecast from the store and compare"):
        s, o, diff = bt.replay(conn, series, forecaster, target)
        st.write(f"{dd.NAMES[forecaster]}: stored forecast {s['predicted']}, recomputed {o['predicted']}; largest probability difference {diff}.")
    st.markdown("#### 5 · Subsequent outcome")
    o1, o2 = b["outcome_first_release"], b["outcome_final"]; k = st.columns(2)
    card(k[0], "Observed, first release", o1["label"] or "Pending", f"{o1['pct_change']:+.2f}% · published {day(o1['label_date'])}" if o1["label"] else "not yet published", DEEP if o1["label"] else MUTED)
    card(k[1], "Observed, final (after three revisions)", o2["label"] or "Pending", f"{o2['pct_change']:+.2f}% · known {day(o2['label_date'])}" if o2["label"] else "not yet final", DEEP if o2["label"] else MUTED)
    if b["events"] is not None:
        st.markdown(f"#### News events published before the issuance time {badge('EXPERIMENTAL')}", unsafe_allow_html=True)
        ev = b["events"]["table"]
        st.caption(f"{len(ev)} events whose first article was published in the {b['events']['window_days']} days before {b['events']['cutoff'][:10]} 00:00 UTC. Shown as context only: events are not an input of the forecast. "
                   "The cut-off is on the publication time; the time of the event itself is not established (column event_time is empty).")
        st.dataframe(ev, use_container_width=True, hide_index=True)

elif view == "Models":
    kind = st.radio("Scored against", ["FINAL", "REALTIME"], horizontal=True, format_func=lambda k: "final outcome" if k == "FINAL" else "first-release outcome")
    period = st.radio("Period", ["ALL", "2016-2019", "2020-2022", "2023-2026"], horizontal=True)
    section("HISTORICAL · BACKTEST", f"walk-forward scores, {dd.series_label(series)}, {period}")
    t = dd.model_table(conn, series, kind, period)
    if t.empty: st.info("No scores.")
    else:
        st.info(dd.BENCHMARK_SENTENCE if series == config.PRIMARY_SERIES else f"Lowest Brier score on this lane: {dd.NAMES[dd.best_by(t, 'Brier score', True)]}. The validated target is the Asia → US lane; " + dd.BENCHMARK_SENTENCE.lower())
        st.dataframe(t[["forecaster", "role", "hit rate", "Brier score", "months scored", "evaluation period", "status"]], use_container_width=True)
        ch = t.reset_index()[["forecaster", "role", "hit rate"]]
        st.altair_chart(alt.Chart(ch).mark_bar().encode(y=alt.Y("forecaster:N", sort="-x", title=None, axis=alt.Axis(labelLimit=320)), x=alt.X("hit rate:Q", scale=alt.Scale(domain=[0, 1]), title="hit rate (share of months called correctly)"),
                                                              color=alt.Color("role:N", scale=alt.Scale(domain=["Benchmark", "Experimental model"], range=[DEEP, SKY]), legend=alt.Legend(orient="top", title=None)),
                                                              tooltip=["forecaster", "role", alt.Tooltip("hit rate:Q", format=".3f")]).properties(height=230), use_container_width=True)
        st.caption("Hit rate: share of months called correctly; a three-class guess scores about one third. Brier score: lower is better. Every forecaster is scored on the same months. "
                   "Benchmarks are simple rules; a model is only useful if it beats them. VALIDATED means the evaluation of a benchmark is reproducible; EXPERIMENTAL means the model has not beaten the benchmarks.")
    section("HISTORICAL · BACKTEST", f"confusion matrix, {dd.NAMES[forecaster]}")
    ev = store.table(conn, "evaluation_results", "WHERE series_id = ? AND forecaster_id = ? AND label_kind = ? AND period = ? AND metric LIKE 'cm_%'", (series, forecaster, kind, period))
    if not ev.empty:
        ev[["_", "actual", "predicted"]] = ev["metric"].str.split("_", expand=True)
        st.dataframe(ev.pivot(index="actual", columns="predicted", values="value").astype(int).reindex(index=config.CLASSES, columns=config.CLASSES), use_container_width=False)
        st.caption("Rows: observed direction. Columns: forecast direction.")
    x = dd.expansion() if series == config.PRIMARY_SERIES else None
    # opt-in: the view itself stays as specified (two tables); the expansion experiment is shown on request
    if x and st.checkbox(f"Show the expansion experiment ({x['candidates']} candidates, feature ablation, weekly fuel-cost study)", value=False):
        section("HISTORICAL · BACKTEST", f"expansion experiment: {x['candidates']} candidates on the same {x['months']} months")
        st.info(("No candidate met the promotion rule that was written before the run. The seasonal baseline remains the official forecast."
                 if not x["decision"]["changed"] else f"{x['decision']['official']} met the promotion rule that was written before the run.")
                + f" {x['confirmatory']} candidates were eligible for promotion; the others are exploratory. Protocol: evaluation/validation_protocol_v2.md.")
        with st.expander("Every candidate against the seasonal baseline"):
            st.dataframe(x["comparison"], use_container_width=True)
            st.caption("Negative difference in Brier score = better than the seasonal baseline. The interval is a paired block bootstrap; DM is a one-sided Diebold-Mariano test; Holm adjusts across the candidates eligible for promotion.")
        with st.expander("Promotion rule, condition by condition"):
            st.dataframe(x["promotion"], use_container_width=True)
        with st.expander("Feature-group ablation: what did more data add?"):
            st.dataframe(x["ablation"], use_container_width=True)
            st.caption("Each group is added to the same base features for each model class, on identical origins. A group adds value only if the interval of its difference to the same model without it lies below zero.")
        if x["weekly"] is not None:
            with st.expander("Weekly fuel-cost direction (a fuel target, not a freight-price forecast)"):
                st.dataframe(x["weekly"], use_container_width=True)
                st.caption(("The primary forecaster met its adoption rule; the weekly fuel-cost outlook is offered under that name." if x["weekly_adopted"] else "The adoption rule was not met; no weekly outlook is offered.")
                           + " No public weekly air-freight rate series is usable; see research/WEEKLY_TARGET_AUDIT.md.")

elif view == "Data Health":
    section("SNAPSHOT" if state["data_mode"] == "SNAPSHOT" else state["data_mode"], "sources of the pipeline")
    hs = pd.DataFrame(state["sources"])
    hs["freshness"] = [("—" if a is None else f"{a:.1f} days since the last successful run") for a in hs["age_days"]]
    hs["cadence"] = [f"published about every {c} day(s); checked every {k}" for c, k in zip(hs["expected_cadence_days"], hs["check_every_days"])]
    hs["availability"] = ["available" if s in ("HEALTHY", "STALE") else "unavailable" for s in hs["status"]]
    hs["checksum"] = [("" if not c else c[:12] + "…") for c in hs["checksum"]]
    show = hs[["name", "status", "data_mode", "last_successful_fetch", "last_attempted_fetch", "last_trigger", "cadence", "freshness", "latest_observation", "record_count", "validation", "checksum", "availability", "failure_reason"]]
    st.dataframe(show.rename(columns={"name": "source", "data_mode": "data mode", "last_successful_fetch": "last successful fetch", "last_attempted_fetch": "last attempted fetch", "last_trigger": "started by",
                                      "cadence": "expected cadence", "freshness": "actual freshness", "latest_observation": "latest observation", "record_count": "record count", "failure_reason": "failure reason"}),
                 use_container_width=True, hide_index=True)
    st.caption("Status is computed now from the ingestion run log and the clock: HEALTHY, STALE (last success older than the check interval allows), FAILED (the last attempt failed), NOT CONFIGURED (no run recorded). "
               "Data mode: SNAPSHOT (seeded or started by hand), AUTOMATED (the last successful run was started by a scheduler and is not stale). LIVE needs an hourly schedule, which no source has. "
               f"Scheduled runs recorded so far: {state['scheduled_runs']}.")
    section("SNAPSHOT", "schedules as defined (a definition is not evidence that anything ran)")
    st.dataframe(pd.DataFrame([{"sources": g, "workflow": v["workflow"], "cron": v["cron"], "meaning": v["meaning"]} for g, v in sources.GROUP_SCHEDULE.items()]), use_container_width=True, hide_index=True)
    section("SNAPSHOT", "append-only records")
    st.dataframe(pd.DataFrame([{"file": n, "state": "intact" if not p else "PROBLEM: " + "; ".join(p[:2])} for n, p in state["chains"].items()]), use_container_width=False, hide_index=True)
    section("RESEARCH", "sources examined and not connected")
    st.dataframe(pd.DataFrame(state["research"])[["source", "status", "data_type", "last_evidence", "notes"]], use_container_width=True, hide_index=True)
    section("HISTORICAL", "benchmark snapshot: data freshness")
    snap = store.table(conn, "source_files"); rows = []
    for s in config.BLS_SERIES:
        cal = store.table(conn, "releases", "WHERE series_id = ?", (s,)); f = snap[snap["file_name"] == config.BLS_SERIES[s][1]].iloc[0]
        rows.append({"lane": dd.series_label(s, technical=True), "latest month": cal["obs_month"].max()[:7], "latest release date": cal["first_release_date"].max(), "snapshot retrieved": f["retrieved_at"][:10]})
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    section("HISTORICAL", f"data-quality results, {dd.series_label(series)}")
    st.dataframe(store.table(conn, "data_quality_results", "WHERE series_id = ?", (series,))[["check_name", "value", "detail"]], use_container_width=True, hide_index=True)

else:
    section("HISTORICAL", "methodology")
    st.markdown(f"""
**What is forecast.** The direction of the month-on-month change of a BLS air-freight price index: *up* or *down* by more than {config.FLAT_BAND_PCT}%, otherwise *flat*.
The validated target is the index for air freight from Asia into the United States (BLS series {config.PRIMARY_SERIES}), final values after three revisions. {PROXY_STATEMENT}

**When.** The forecast of month *t* is issued on the day BLS first publishes month *t − 1* (about the middle of month *t*). It is a nowcast.

**With what.** Only values published by the issuance date: earlier values of the index and of seven related indexes as they stood then (every revision is stored with its publication date),
jet fuel and Brent prices at least eight days old, and the calendar month.

**How it is judged.** Walk-forward from January 2016: at every month each forecaster is refitted on the outcomes known at that date and scored on the next one. Three simple benchmarks and two models are scored on the same months.
{dd.BENCHMARK_SENTENCE}

**Leakage prevention.** Every stored value carries the date it became available. Features are built from an as-of view of the store; training uses only outcomes whose final value was published by the issuance date.
The Replay page shows this for any month, and the test suite recomputes forecasts on data cut at the issuance date.

**Data states on these pages.**
- HISTORICAL · BACKTEST — the validated replay of history from a fixed data snapshot.
- SNAPSHOT — data fetched by hand; as old as its retrieval date.
- AUTOMATED — a source that a scheduler has recently refreshed. LIVE is reserved for sources checked hourly; AirPulse has none.
- EXPERIMENTAL — the event layer and the two models. RESEARCH — sources examined and not connected.
- Kinds of value: Observed (published by the source), Forecast, Pending (outcome not yet published), Unavailable.

**What AirPulse is not.** It is not a forecast of South Asia → Europe rates, not a weekly forecast, and not a live service. The original proposal aimed at those; no public historical price series for that lane was obtained
(`research/target_feasibility_india_europe.md`).

**Technical identifiers.** """ + "; ".join(f"{dd.series_label(s)} = {s}" for s in config.BLS_SERIES) + ". Forecasters: " + "; ".join(f"{n} = {i}" for i, n in dd.NAMES.items()) + ".")
    st.caption("Full protocol: evaluation/validation_protocol.md. Leakage audit: evaluation/leakage_audit.md. Final report: docs/AirPulse_Final_Report.pdf.")
