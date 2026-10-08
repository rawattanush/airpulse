"""Append-only record files (JSON Lines) with a hash chain.

Used for the ingestion run log, the operational forecast ledger and the forecast outcomes. A record is never
rewritten: `append` only adds a line. Every line carries the hash of the line before it, so an edited, removed or
reordered line is detected by `verify`. No network, no clock except the caller's."""
import hashlib, json, os

GENESIS = "0" * 64


def _digest(prev, body):
    return hashlib.sha256((prev + json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))).encode("utf-8")).hexdigest()


def read(path):
    """All records of a file, in order. A missing file is an empty list."""
    if not os.path.exists(path): return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def append(path, body):
    """Add one record. Returns the stored record (body plus seq, prev and hash)."""
    recs = read(path); prev = recs[-1]["hash"] if recs else GENESIS
    rec = {**body, "seq": len(recs) + 1, "prev": prev}
    rec["hash"] = _digest(prev, {k: v for k, v in rec.items() if k != "hash"})
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(rec, sort_keys=True, ensure_ascii=False) + "\n")
    return rec


def verify(path):
    """Problems found in the chain; an empty list means the file is intact."""
    problems, prev = [], GENESIS
    for i, rec in enumerate(read(path), start=1):
        if rec.get("seq") != i: problems.append(f"record {i}: sequence number {rec.get('seq')}")
        if rec.get("prev") != prev: problems.append(f"record {i}: does not follow the record before it")
        if rec.get("hash") != _digest(rec.get("prev", ""), {k: v for k, v in rec.items() if k != "hash"}): problems.append(f"record {i}: content does not match its hash")
        prev = rec.get("hash", "")
    return problems
