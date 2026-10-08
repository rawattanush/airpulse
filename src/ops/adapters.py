"""Source adapters of the operational pipeline. Each adapter fetches one source, validates the response against the
file already held, stores the raw response once, and returns one run record. An adapter never raises for a source
problem: the problem is returned in the record (result FAILED), and the files already held are left untouched.

Idempotent: a response whose content is already held produces result UNCHANGED and writes no data file.
Bounded retries: at most ops.config.HTTP_ATTEMPTS requests per URL, with fixed pauses."""
import datetime, gzip, hashlib, io, json, os, re, time, urllib.error, urllib.request
import pandas as pd
from src.ingestion import loaders
from src.ops import bls, config, eia


class FetchError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message); self.status = status


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def http_get(url, timeout=None, attempts=None, backoff=None, sleep=time.sleep, opener=urllib.request.urlopen, data=None):
    """(status, body). Retries on network errors, HTTP 429 and 5xx; any other HTTP error fails at once.
    Every request names its client (config.http_headers): a publisher can see who asks and can reach the operator."""
    attempts = attempts or config.HTTP_ATTEMPTS; backoff = backoff or config.HTTP_BACKOFF; last = None
    headers = {**config.http_headers(), **({"Content-Type": "application/json"} if data is not None else {})}
    for k in range(attempts):
        try:
            with opener(urllib.request.Request(url, data=data, headers=headers), timeout=timeout or config.HTTP_TIMEOUT) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            last = FetchError(f"HTTP {e.code} from {url.split('?')[0]}", e.code)
            if e.code != 429 and e.code < 500: raise last
        except Exception as e:
            last = FetchError(f"{type(e).__name__}: {e}")
        if k < attempts - 1: sleep(backoff[min(k, len(backoff) - 1)])
    raise last


def _sha(b): return hashlib.sha256(b).hexdigest()


def _read_current(path):
    """(bytes, sidecar) of a held file, or (None, None)."""
    if not os.path.exists(path): return None, None
    with open(path, "rb") as f: body = f.read()
    with open(path + ".meta.json", encoding="utf-8") as f: meta = json.load(f)
    return body, meta


def _store_raw(raw_dir, source_id, retrieved_at, body, suffix):
    """Write the raw response once, compressed, named by time and content. Returns the path relative to the repository."""
    d = os.path.join(raw_dir, source_id); os.makedirs(d, exist_ok=True)
    name = f"{retrieved_at.replace(':', '').replace('-', '')}_{_sha(body)[:12]}{suffix}.gz"; path = os.path.join(d, name)
    if not os.path.exists(path):
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as g: g.write(body)      # mtime 0: the same response always gives the same file
        with open(path, "wb") as f: f.write(buf.getvalue())
    return os.path.relpath(path, config.ROOT).replace(os.sep, "/")


def _replace_current(path, body, meta):
    """Put a verified file and its sidecar in place; the old pair stays until both new files are written."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".new", "wb") as f: f.write(body)
    with open(path + ".meta.json.new", "w", encoding="utf-8") as f: json.dump(meta, f, indent=1)
    os.replace(path + ".new", path); os.replace(path + ".meta.json.new", path + ".meta.json")


def _record(source_id, cfg, started, **kw):
    base = {"source": source_id, "group": cfg["group"], "retrieved_at": started, "url": cfg["url"], "http_status": None, "result": "FAILED", "error": "",
            "record_count": None, "latest_observation": None, "checksum": None, "validation": "", "raw_snapshot": None, "new_records": 0,
            "schema_version": config.RUN_SCHEMA_VERSION, "pipeline_version": config.PIPELINE_VERSION}
    base.update(kw); return base


def _fuel_frame(body):
    df = pd.read_csv(io.BytesIO(body)); df.columns = ["d", "v"]
    df["d"] = pd.to_datetime(df["d"]); df["v"] = pd.to_numeric(df["v"], errors="coerce")
    return df


def fetch_eia(source_id, cfg, current_dir=None, raw_dir=None, get=http_get, now=utc_now):
    """Daily price series, whole history in one spreadsheet of the Energy Information Administration. The spreadsheet is kept
    as fetched (dated, so the releases can be told apart later) and turned into the two-column file the engine reads.
    Accepted only if it names the series asked for, parses, is in date order without duplicate dates, has no fewer
    observations than the file held, and does not end earlier."""
    current_dir = current_dir or config.CURRENT_DIR; raw_dir = raw_dir or config.RAW_DIR
    started = now(); path = os.path.join(current_dir, cfg["file"]); old_body, old_meta = _read_current(path)
    try: status, raw_body = get(cfg["url"])
    except FetchError as e: return _record(source_id, cfg, started, http_status=e.status, error=str(e), checksum=old_meta["sha256"] if old_meta else None)
    try:
        body = eia.csv_text(cfg["series"], eia.parse_xls(raw_body, cfg["series"])).encode("utf-8"); sha = _sha(body)
        df = _fuel_frame(body); good = df.dropna(subset=["v"])
        problems = []
        if len(good) == 0: problems.append("no observation")
        if not df["d"].is_monotonic_increasing: problems.append("dates not in order")
        if df["d"].duplicated().any(): problems.append("duplicate dates")
        if (good["v"] <= 0).any(): problems.append("non-positive price")
        if len(good) and good["d"].max() > pd.Timestamp(started[:10]): problems.append("observation dated after the fetch")
        revised = 0
        if old_body is not None:
            old = _fuel_frame(old_body).dropna(subset=["v"])
            if len(good) < len(old): problems.append(f"fewer observations than held ({len(good)} < {len(old)})")
            if len(good) and len(old) and good["d"].max() < old["d"].max(): problems.append("series ends earlier than the file held")
            j = old.merge(good, on="d", how="left", suffixes=("_old", "_new")); revised = int(((j["v_new"] != j["v_old"]) & j["v_new"].notna()).sum())
    except Exception as e:
        return _record(source_id, cfg, started, http_status=status, error=f"response cannot be parsed ({type(e).__name__}: {e})", checksum=old_meta["sha256"] if old_meta else None)
    latest = good["d"].max().strftime("%Y-%m-%d") if len(good) else None
    if problems:
        return _record(source_id, cfg, started, http_status=status, error="validation failed: " + "; ".join(problems), validation="FAILED: " + "; ".join(problems), checksum=old_meta["sha256"] if old_meta else None)
    val = f"passed: {len(good)} observations to {latest}; {revised} earlier values differ from the file held"
    if old_meta and sha == old_meta["sha256"]:
        return _record(source_id, cfg, started, http_status=status, result="UNCHANGED", record_count=int(len(good)), latest_observation=latest, checksum=sha, validation=val)
    raw = _store_raw(raw_dir, source_id, started, raw_body, ".xls")
    new_n = int(len(good) - (len(_fuel_frame(old_body).dropna(subset=["v"])) if old_body is not None else 0))
    _replace_current(path, body, {"source_id": cfg["registry_id"], "url": cfg["url"], "retrieved_at": started, "sha256": sha, "http_status": status, "bytes": len(body),
                                  "note": f"operational refresh ({config.PIPELINE_VERSION}): spreadsheet {_sha(raw_body)[:16]} kept as {raw} and written as observation_date,value; previous file {old_meta['sha256'][:16] if old_meta else 'none'}"})
    return _record(source_id, cfg, started, http_status=status, result="UPDATED", record_count=int(len(good)), latest_observation=latest, checksum=sha, validation=val, raw_snapshot=raw, new_records=new_n, revised_values=revised)


def _columns(matrix_text):
    """Stored vintage matrix -> (series, release dates, [{month: value} per column])."""
    lines = matrix_text.strip().splitlines(); head = lines[0].split(",")[1:]; series = head[0].rsplit("_", 1)[0]
    dates = [f"{c[-8:-4]}-{c[-4:-2]}-{c[-2:]}" for c in head]; cols = [dict() for _ in head]
    for ln in lines[1:]:
        p = ln.split(",")
        for j, v in enumerate(p[1:]):
            if v not in ("", "."): cols[j][p[0]] = float(v)
    return series, dates, cols


def fetch_bls(source_id, cfg, current_dir=None, raw_dir=None, get=http_get, post=None, now=utc_now, sleep=time.sleep):
    """Monthly index with every release as its own column, read at the Bureau of Labor Statistics. Asks the Bureau's list
    of archived releases, reads only releases newer than the newest one held, and adds one column per release by the rule
    of src.ops.bls. Stored columns are never touched. The month whose second revision a release does not print is read
    from the Bureau's database when the release is still the newest one (the database then shows exactly what that release
    made known); for a release read later it is inferred as src.ops.bls.second_revision describes."""
    current_dir = current_dir or config.CURRENT_DIR; raw_dir = raw_dir or config.RAW_DIR; post = post or (lambda u, b: get(u, data=b))
    started = now(); series = cfg["series"]; path = os.path.join(current_dir, cfg["file"]); old_body, old_meta = _read_current(path)
    if old_body is None: return _record(source_id, cfg, started, error="no stored vintage matrix to extend; run `python -m src.ops.cli init` first")
    text = old_body.decode("utf-8"); _, held, cols = _columns(text)
    try:
        status, listing = get(bls.ARCHIVE_LIST); listed = bls.releases(listing.decode("utf-8", "replace"))
    except (FetchError, bls.ReleaseError) as e: return _record(source_id, cfg, started, http_status=getattr(e, "status", None), error=str(e), checksum=old_meta["sha256"])
    dates = [d for d, _ in listed]; new = [(d, u) for d, u in listed if d > held[-1]]; missing = sorted(set(d for d in dates if held[0] <= d <= held[-1]) - set(held))
    future = [d for d, _ in new if d > started[:10]]
    if future: return _record(source_id, cfg, started, http_status=200, error=f"validation failed: release dated after the fetch ({future[0]})", validation="FAILED: release dated after the fetch", checksum=old_meta["sha256"])
    note = f"{len(held)} releases held to {held[-1]}; the Bureau lists {len(dates)} to {dates[-1]}" + (f"; {len(missing)} earlier releases at the source are not in the stored matrix: {missing[:3]}" if missing else "")
    if not new:
        return _record(source_id, cfg, started, http_status=200, result="UNCHANGED", record_count=len(held), latest_observation=held[-1], checksum=old_meta["sha256"], validation="passed: " + note)
    raws, rules = [], []
    try:
        parsed = []
        for d, u in new:
            sleep(config.REQUEST_PAUSE); status, page = get(u); text_ = page.decode("utf-8", "replace")
            try: tab = bls.table_fragment(text_)
            except bls.ReleaseError: tab = None                                           # a release the Bureau lists without a table (rule f, or rule e while it is the newest)
            parsed.append((d, bls.parse_release(tab) if tab else None)); raws.append(_store_raw(raw_dir, source_id, started, (tab or text_).encode("utf-8"), f"_{d}.htm"))
        year = int(new[-1][0][:4]); sleep(config.REQUEST_PAUSE)
        status, ans = post(bls.API, json.dumps(bls.api_request([series], year - 1, year)).encode("utf-8"))
        raws.append(_store_raw(raw_dir, source_id, started, ans, "_database.json")); base = bls.parse_api(json.loads(ans)).get(series, {})
        for i, (d, rel) in enumerate(parsed):
            if rel is None:
                col, how = bls.column_from_database(cols[-1], base, d) if (i == len(parsed) - 1 and d == dates[-1]) else bls.column_without_table(cols[-1])
                cols.append(col); held.append(d); rules += [f"{d} {k[:7]}: {w}" for k, w in how]; continue
            m = rel["month"]; final = {**cols[-1], **{k: v for k, v in base.items() if k <= bls.shift(m, -bls.REVISION_RELEASES)}}
            col, how = bls.column(rel, series, final, cols[-1]); r = rel["series"][series]; m1, m2 = bls.shift(m, -1), bls.shift(m, -2)
            newest = i == len(parsed) - 1 and d == dates[-1] and base.get(m) == r["current"] and base.get(m1) == r["previous"]
            if newest and m2 in base:
                col[m2] = base[m2]; how = [(k, "e database value read while the release was the newest" if k == m2 else w) for k, w in how]
            cols.append(col); held.append(d); rules += [f"{d} {k[:7]}: {w}" for k, w in how]
        merged = bls.matrix_text(series, held, cols).encode("utf-8")
        tmp = path + ".check"
        with open(tmp, "wb") as fh: fh.write(merged)
        try: records, vints, _ = loaders.parse_vintage_matrix(tmp)                    # the validated parser must accept the merged file
        finally: os.remove(tmp)
        n_old = len(text.strip().splitlines()[0].split(",")) - 1
        if _columns(merged.decode("utf-8"))[2][:n_old] != _columns(text)[2]: raise FetchError("stored columns changed during the merge")
    except Exception as e:
        return _record(source_id, cfg, started, http_status=getattr(e, "status", None), error=f"{type(e).__name__}: {e}", checksum=old_meta["sha256"], validation="FAILED")
    sha = _sha(merged); added = [d for d, _ in new]
    _replace_current(path, merged, {"source_id": cfg["registry_id"], "url": f"{bls.ARCHIVE_LIST} (each of {len(vints)} archived releases); {bls.API} (series {bls.bls_id(series)})",
                                    "retrieved_at": started, "sha256": sha, "http_status": 200, "bytes": len(merged),
                                    "note": f"operational refresh ({config.PIPELINE_VERSION}): releases {', '.join(added)} appended to the matrix {old_meta['sha256'][:16]}; stored columns unchanged; cells: {'; '.join(rules)}; raw answers {'; '.join(raws)}"})
    return _record(source_id, cfg, started, http_status=200, result="UPDATED", record_count=len(vints), latest_observation=vints[-1], checksum=sha,
                   validation=f"passed: {len(added)} new release(s) {', '.join(added)}; {len(records)} revision-log rows", raw_snapshot="; ".join(raws), new_records=len(added))


def fetch_news(source_id, cfg, now=utc_now, archive_dir=None):
    """Headline metadata of one publication, through the event layer's own incremental adapter (append-only archive)."""
    from src.news import ingestion
    started = now()
    try:
        r = ingestion.ingest([cfg["series"]], archive_dir=archive_dir, log=lambda *a: None)[cfg["series"]]
        recs = ingestion.read_archive(archive_dir, sources=[cfg["series"]]); h = ingestion.verify_archive(archive_dir)
    except Exception as e:
        return _record(source_id, cfg, started, error=f"{type(e).__name__}: {e}")
    return _record(source_id, cfg, started, http_status=200, result="UPDATED" if r["new"] else "UNCHANGED", record_count=len(recs), new_records=int(r["new"]),
                   latest_observation=recs[-1]["published_utc"] if recs else None, checksum=h, validation=f"passed: archive matches its manifest; {r['fetched']} fetched, {r['new']} new")


ADAPTERS = {"eia_series": fetch_eia, "bls_releases": fetch_bls, "news_wordpress": fetch_news}
