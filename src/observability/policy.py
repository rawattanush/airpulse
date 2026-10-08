"""The production policy: which sources and which features may reach the public product.

    config/production_sources.yaml   the policy, kept by hand: licence class with the evidence it rests on, rights, production status

The export of the customer application asks this module before it writes anything. A source is REFUSED when its licence
class is not one of the commercial-safe classes, when commercial use, public display or derived data is not allowed, when
it is not enabled, or when its production status is not PRODUCTION. A feature is refused when its status is not
PRODUCTION READY or when one of its sources is refused. An unknown licence is a refusal, never a pass.

This module names no source and no feature: it reads the policy. Like the registry, it imports no layer.

    python -m src.observability.policy            # print what may be published and what is refused, with the reason
    python -m src.observability.policy --check    # exit 1 if the policy is inconsistent"""
import os, sys
import yaml
from src.observability import registry, sources

POLICY = os.path.join(sources.ROOT, "config", "production_sources.yaml")
SAFE = ("COMMERCIAL-SAFE", "COMMERCIAL-SAFE-WITH-ATTRIBUTION", "COMMERCIAL-SAFE-WITH-LIMITS")
CLASSES = SAFE + ("NON-COMMERCIAL", "RESEARCH-ONLY", "LICENSE-REQUIRED", "UNKNOWN", "BLOCKED")
SOURCE_STATUS = ("PRODUCTION", "RESEARCH", "DISABLED", "BLOCKED")
LICENCE_STATUS = ("CLEARED", "PENDING_CONFIRMATION", "RESEARCH_ONLY", "RETIRED", "NOT_CONNECTED")
PRODUCTION_FIELDS = ("purpose", "lag", "automation_allowed", "attribution", "evidence", "evidence_url", "evidence_date")     # what a production source must state besides FIELDS
FEATURE_STATUS = ("PRODUCTION READY", "BLOCKED", "NEEDS VALIDATION", "NEEDS LICENCE", "REMOVE FROM PUBLIC PRODUCT")
FIELDS = ("id", "name", "authority", "url", "data_type", "frequency", "coverage", "license_class", "commercial_allowed", "public_display_allowed", "storage_allowed", "derived_data_allowed",
          "api_required", "credentials_required", "stale_after", "enabled", "production_status", "licence_status")
PUBLIC_STATUS = ("HEALTHY", "DEGRADED", "STALE", "FAILED", "UNAVAILABLE")      # the only states a production data set is shown with


def load(path=None):
    with open(path or POLICY, encoding="utf-8") as f: doc = yaml.safe_load(f)
    return {"audited": str(doc.get("audited")), "sources": {s["id"]: s for s in doc.get("sources", [])}, "features": {f["id"]: f for f in doc.get("features", [])}, "retired": list(doc.get("retired") or [])}


def refusal(entry):
    """Why a source may not be published; None when it may. The first reason found is returned."""
    if entry is None: return "not in the production policy"
    if entry.get("license_class") not in SAFE: return f"licence class {entry.get('license_class')}"
    for k, word in (("commercial_allowed", "commercial use is not allowed"), ("public_display_allowed", "public display is not allowed"), ("derived_data_allowed", "derived data are not allowed"), ("enabled", "switched off")):
        if entry.get(k) is not True: return word
    if entry.get("production_status") != "PRODUCTION": return f"production status {entry.get('production_status')}"
    return None


def pending(policy=None):
    """Production sources whose licence is not CLEARED, with the open question: {id: reason}. Nothing is deployed while this is not empty."""
    policy = policy or load()
    return {i: str(s.get("pending") or f"licence status {s.get('licence_status')}") for i, s in policy["sources"].items() if s.get("production_status") == "PRODUCTION" and s.get("enabled") and s.get("licence_status") != "CLEARED"}


def publishable_sources(policy=None):
    policy = policy or load()
    return sorted(i for i, s in policy["sources"].items() if refusal(s) is None)


def feature_refusal(feature, policy=None):
    """Why a feature may not be in the public product; None when it may."""
    policy = policy or load(); f = policy["features"].get(feature) if isinstance(feature, str) else feature
    if f is None: return "not in the production policy"
    if f.get("status") != "PRODUCTION READY": return f"status {f.get('status')}"
    for s in f.get("sources") or []:
        why = refusal(policy["sources"].get(s))
        if why: return f"source {s}: {why}"
    return None


def public_features(policy=None):
    policy = policy or load()
    return [i for i in policy["features"] if feature_refusal(i, policy) is None]


def public_status(row):
    """The state a production data set is shown with: one of PUBLIC_STATUS. A set that was never fetched is UNAVAILABLE, not failed."""
    if row is None or row.get("status") in ("DISABLED", "RESEARCH_ONLY"): return "UNAVAILABLE"
    if row.get("status") == "FAILED" and not row.get("last_success"): return "UNAVAILABLE"
    return row["status"]


def check(path=None):
    """Problems of the policy: a missing field, an unknown class or status, a production entry without evidence or with a
    refusal, a declared source without a policy entry (or the reverse), a name or address that differs from the declaration,
    a feature that is PRODUCTION READY while one of its sources is refused."""
    policy = load(path); problems = []; decl = {d["id"]: d for d in registry.declared()[1]}
    for i, s in policy["sources"].items():
        for k in FIELDS:
            if k not in s: problems.append(f"{i}: field {k} missing")
        if s.get("license_class") not in CLASSES: problems.append(f"{i}: licence class {s.get('license_class')}")
        if s.get("production_status") not in SOURCE_STATUS: problems.append(f"{i}: production status {s.get('production_status')}")
        if not s.get("evidence") or not s.get("evidence_date"): problems.append(f"{i}: no evidence for its licence class")
        if s.get("production_status") == "PRODUCTION" and refusal(s): problems.append(f"{i}: marked PRODUCTION and refused ({refusal(s)})")
        if s.get("licence_status") not in LICENCE_STATUS: problems.append(f"{i}: licence status {s.get('licence_status')}")
        if s.get("production_status") == "PRODUCTION":
            for k in PRODUCTION_FIELDS:
                if s.get(k) in (None, ""): problems.append(f"{i}: a production source needs {k}")
            if s.get("licence_status") not in ("CLEARED", "PENDING_CONFIRMATION"): problems.append(f"{i}: marked PRODUCTION with licence status {s.get('licence_status')}")
            if s.get("automation_allowed") is not True: problems.append(f"{i}: a production source is fetched by a scheduler and automated retrieval is not stated as allowed")
        elif s.get("licence_status") in ("CLEARED", "PENDING_CONFIRMATION"): problems.append(f"{i}: licence status {s.get('licence_status')} on a source that is not in production")
        if (s.get("licence_status") == "PENDING_CONFIRMATION") != bool(s.get("pending")): problems.append(f"{i}: a pending licence names its open question, and only a pending one does")
        d = decl.get(i)
        if d is None: problems.append(f"{i}: in the policy and not declared in config/sources.yaml"); continue
        if d["name"] != s["name"] or d["url"] != s["url"]: problems.append(f"{i}: name or address differs from the declaration")
        if bool(d["active"]) != bool(s["enabled"]): problems.append(f"{i}: enabled here and active in the declaration differ")
    for i in decl:
        if i not in policy["sources"]: problems.append(f"{i}: declared and not in the production policy")
    for i, f in policy["features"].items():
        if f.get("status") not in FEATURE_STATUS: problems.append(f"feature {i}: status {f.get('status')}")
        for s in f.get("sources") or []:
            if s not in policy["sources"]: problems.append(f"feature {i}: source {s} is not in the policy")
        if f.get("status") == "PRODUCTION READY":
            why = feature_refusal(f, policy)
            if why: problems.append(f"feature {i}: PRODUCTION READY and refused ({why})")
            for k in ("validation", "wording", "pages", "artifacts", "kind"):
                if k not in f: problems.append(f"feature {i}: field {k} missing")
        elif not f.get("reason"): problems.append(f"feature {i}: no reason for {f.get('status')}")
    return problems


def main(argv):
    problems = check()
    for p in problems: print("POLICY PROBLEM:", p)
    if "--check" in argv: return 1 if problems else 0
    policy = load()
    for i, s in policy["sources"].items(): print(f"{'PUBLISH' if refusal(s) is None else 'REFUSE ':8} {i:30} {s['license_class']:34} {s['licence_status']:22} {refusal(s) or ''}")
    for i, why in pending(policy).items(): print(f"NOT DEPLOYABLE: {i}: {why[:110]}")
    for i, f in policy["features"].items(): print(f"{'PUBLIC ' if feature_refusal(f, policy) is None else 'NOT PUBLIC':10} {i:32} {f['status']:28} {(feature_refusal(f, policy) or '')[:60]}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
