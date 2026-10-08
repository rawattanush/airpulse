"""MOD-01 Ingestion, build step: snapshot -> canonical store, in one all-or-nothing operation.
The store is built in a temporary file and moved into place only on success, so a failed build
leaves any existing store unchanged (REQ-REL-001)."""
import datetime, hashlib, os
from src import config
from src.database import store
from src.ingestion import loaders
from src.preprocessing import labels as lab
from src.validation import checks


def snapshot_hash(snapshot_dir=None):
    """SHA-256 over the names and checksums of every snapshot file the system reads."""
    d = snapshot_dir or config.SNAPSHOT_DIR
    h = hashlib.sha256()
    for _, f in sorted(list(config.BLS_SERIES.values()) + list(config.FUEL_SERIES.values()), key=lambda x: x[1]):
        h.update(f.encode()); h.update(loaders.verify_file(os.path.join(d, f))["sha256"].encode())
    return h.hexdigest()


def build_store(db_path=None, snapshot_dir=None):
    """Verify, parse, validate and load every configured series; derive calendar and labels. Returns row counts."""
    db_path = db_path or config.DB_PATH; snapshot_dir = snapshot_dir or config.SNAPSHOT_DIR
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    tmp = db_path + ".building"
    if os.path.exists(tmp): os.remove(tmp)
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = store.connect(tmp)
    try:
        store.create_schema(conn)
        counts = {}
        with conn:
            def add_file(fname):
                meta = loaders.verify_file(os.path.join(snapshot_dir, fname))
                cur = conn.execute("INSERT INTO source_files(file_name, source_id, url, sha256, retrieved_at) VALUES (?,?,?,?,?)",
                                   (fname, meta["source_id"], meta["url"], meta["sha256"], meta["retrieved_at"]))
                return cur.lastrowid

            for sid, (title, fname) in config.BLS_SERIES.items():
                fid = add_file(fname)
                records, vints, withdrawn = loaders.parse_vintage_matrix(os.path.join(snapshot_dir, fname))
                conn.execute("INSERT INTO series VALUES (?,?,?,?,?)", (sid, title, "BLS_INDEX", "monthly from 2005-12", fid))
                conn.executemany("INSERT INTO observations VALUES (?,?,?,?,?)", [(sid, o, v, x, fid) for o, v, x in records])
                conn.executemany("INSERT INTO vintages VALUES (?,?)", [(sid, v) for v in vints])
                for name, value, detail in checks.check_bls(records, vints, withdrawn, config.MONTHLY_ERA_START):
                    conn.execute("INSERT INTO data_quality_results(series_id, check_name, value, detail, created_at) VALUES (?,?,?,?,?)", (sid, name, value, detail, now))
                cal = lab.release_calendar(records, vints, config.REVISION_RELEASES, config.MONTHLY_ERA_START)
                conn.executemany("INSERT INTO releases VALUES (?,?,?,?,?)",
                                 [(sid, r.obs_month, r.first_release_date, int(r.first_release_observed), r.final_date) for r in cal.itertuples()])
                lb = lab.build_labels(records, cal, config.FLAT_BAND_PCT)
                conn.executemany("INSERT INTO labels VALUES (?,?,?,?,?,?)",
                                 [(sid, r.target_month, r.kind, r.pct_change, r.label, r.label_date) for r in lb.astype(object).where(lb.notna(), None).itertuples()])
                counts[sid] = len(records)
            for sid, (title, fname) in config.FUEL_SERIES.items():
                fid = add_file(fname)
                records, info = loaders.parse_fuel(os.path.join(snapshot_dir, fname), config.FUEL_AVAILABILITY_LAG_DAYS)
                conn.execute("INSERT INTO series VALUES (?,?,?,?,?)", (sid, title, "FUEL", "daily (business days)", fid))
                conn.executemany("INSERT INTO observations VALUES (?,?,?,?,?)", [(sid, o, a, x, fid) for o, a, x in records])
                for name, value, detail in checks.check_fuel(records, info):
                    conn.execute("INSERT INTO data_quality_results(series_id, check_name, value, detail, created_at) VALUES (?,?,?,?,?)", (sid, name, value, detail, now))
                counts[sid] = len(records)
        conn.close()
    except Exception:
        conn.close()
        if os.path.exists(tmp): os.remove(tmp)
        raise
    os.replace(tmp, db_path)
    return counts
