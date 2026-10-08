"""Taxonomy and source-reliability loaders (REQ-NEWS-003, REQ-NEWS-008). Both are versioned YAML files in research/.
The loader validates them and compiles every pattern once."""
import re
import yaml
from src.news import config

REQUIRED_TYPE_KEYS = {"category", "feature_group", "direction", "base_severity", "affected_mode", "reversible", "effects", "patterns"}
EFFECT_KEYS = ("capacity", "demand", "supply", "diversion_pressure")
EFFECT_VALUES = {"INCREASE", "DECREASE", "UNKNOWN"}


class Taxonomy:
    def __init__(self, path=None):
        with open(path or config.TAXONOMY_PATH, encoding="utf-8") as f: raw = yaml.safe_load(f)
        self.version = str(raw["taxonomy_version"]); self.categories = raw["categories"]; self.statuses = raw["statuses"]
        frag = raw.get("fragments", {})
        self.context = {k: re.compile(v["re"]) for k, v in raw["context"].items()}
        self.negation_window = int(raw["context"]["negation"]["window_tokens"])
        self.types = {}
        for name, t in raw["event_types"].items():
            missing = REQUIRED_TYPE_KEYS - set(t)
            if missing: raise ValueError(f"taxonomy: {name} lacks {sorted(missing)}")
            if t["category"] not in self.categories: raise ValueError(f"taxonomy: {name} has unknown category {t['category']}")
            if t["direction"] not in (-1, 0, 1) or t["base_severity"] not in (1, 2, 3): raise ValueError(f"taxonomy: {name} has an invalid direction or severity")
            if set(t["effects"]) != set(EFFECT_KEYS) or not set(t["effects"].values()) <= EFFECT_VALUES: raise ValueError(f"taxonomy: {name} has invalid effects")
            pats = []
            for p in t["patterns"]:
                r = p["re"]
                for k, v in frag.items(): r = r.replace("{" + k + "}", v)
                pats.append((re.compile(r), float(p["conf"]), p["re"]))
            self.types[name] = {**t, "compiled": pats, "requires_mode": t.get("requires_mode"), "excludes_rx": re.compile(t["excludes"]) if t.get("excludes") else None}

    def feature_groups(self):
        return sorted({t["feature_group"] for t in self.types.values()})


class Reliability:
    def __init__(self, path=None):
        with open(path or config.RELIABILITY_PATH, encoding="utf-8") as f: raw = yaml.safe_load(f)
        self.version = str(raw["registry_version"]); self.tiers = {int(k): v for k, v in raw["tiers"].items()}
        self.default_tier = int(raw["default_tier"]); self.sources = raw.get("sources", {})
        for sid, s in self.sources.items():
            if int(s["tier"]) not in self.tiers: raise ValueError(f"reliability: {sid} has unknown tier {s['tier']}")

    def profile(self, source_id):
        """tier, weight and default mode of a source; an unlisted source gets the default tier and no default mode."""
        s = self.sources.get(source_id, {}); tier = int(s.get("tier", self.default_tier))
        return {"tier": tier, "weight": float(self.tiers[tier]["weight"]), "default_mode": s.get("default_mode"), "kind": s.get("kind", "unlisted source")}
