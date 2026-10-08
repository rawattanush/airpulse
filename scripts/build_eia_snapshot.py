"""The benchmark's fuel input, rebuilt from the Energy Information Administration's own spreadsheets (CL-024, rule 5).

    python scripts/build_eia_snapshot.py            # research/data_samples/SRC-01_eia_<key>.csv, SRC-08_eia_<key>.csv with sidecars

The spreadsheets are the ones retrieved from the Administration on 2026-10-03 for the first data audit and held since, so
the benchmark's fuel input keeps the date it had. Offline and deterministic; the conversion is src.ops.eia."""
import hashlib, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from src import config                                               # noqa: E402
from src.ingestion import loaders                                    # noqa: E402
from src.ops import eia                                              # noqa: E402

HELD = {s: (f[:6], f[:-4] + ".xls") for s, (_, f) in config.FUEL_SERIES.items()}      # the spreadsheet beside each file, under the same name
sha = lambda b: hashlib.sha256(b).hexdigest()
P = lambda n: os.path.join(config.SNAPSHOT_DIR, n)


def build():
    for series, (rid, xls) in HELD.items():
        meta = loaders.verify_file(P(xls))                                                      # the spreadsheet is the one retrieved then, unchanged
        rows = eia.parse_xls(open(P(xls), "rb").read(), series); body = eia.csv_text(series, rows).encode("utf-8"); out = P(config.FUEL_SERIES[series][1])
        with open(out, "wb") as f: f.write(body)
        with open(out + ".meta.json", "w", encoding="utf-8", newline="\n") as f:
            json.dump({"source_id": rid, "url": meta["url"], "retrieved_at": meta["retrieved_at"], "sha256": sha(body), "http_status": meta.get("http_status", 200), "bytes": len(body),
                       "note": f"Written as observation_date,value from the Energy Information Administration's spreadsheet {xls} (sha256 {meta['sha256'][:16]}): python scripts/build_eia_snapshot.py. Values unmodified."}, f, indent=1)
        print(f"{series}: {len(rows)} observations, {rows[0][0]} to {rows[-1][0]} -> {os.path.basename(out)}")


if __name__ == "__main__":
    build()
