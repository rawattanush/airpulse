"""Deterministic event parser, version P1.0 (REQ-NEWS-005, REQ-NEWS-006). No model, no network, no randomness.

For one headline it returns the mentions found and, separately, every candidate it rejected with the reason,
so that the handling of negation, reversal and speculation can be audited.

Decision order for a pattern match (first rule that applies wins):
  1. RETROSPECTIVE   the headline looks back at an old event                      -> rejected
  2. MODE            the type needs an air context and the headline has none      -> rejected
  0. CONTRAST        the match straddles a contrast word (but, while, despite)     -> rejected
  2b. EXCLUDED       the type's own exclusion pattern matches (e.g. oil prices)   -> rejected
  3. NEGATED         a negation cue stands just before, or inside, the match      -> rejected
  4. POTENTIAL_END   reversal cue and hypothetical cue together ("could reopen")  -> rejected
  5. ENDED           reversal cue, for types marked reversible                    -> status ENDED
  6. POTENTIAL       hypothetical cue in the same clause, or a question           -> status POTENTIAL
  7. otherwise                                                                    -> status ACTIVE

Cues are looked for in the clause that contains the match, not in the whole headline, so that
"oil prices rose after the attack, analysts warn of more" does not turn the price rise into a potential event."""
import re
from src.news import config, entities
from src.news.normalization import clean_title, match_form, text_hash

_CLAUSE_SPLIT = re.compile(r"\s[-|]\s|[;:]\s|,\s(?=(?:but|while|as|analysts?|experts?|says?|said)\b)|\s(?=(?:but|while)\s)")
_SURCHARGE_UP = re.compile(r"\b(rais\w+|increas\w+|hik\w+|introduc\w+|impos\w+|higher|ris(e|es|ing)|rose|up)\b")
_SURCHARGE_DOWN = re.compile(r"\b(cuts?|cutting|reduc\w+|lower\w*|drop\w*|scrap\w*|remov\w+|fall\w*|fell|down)\b")


def _clause(text, start, end):
    """(clause_start, clause_end) of the clause containing the span."""
    a, b = 0, len(text)
    for m in _CLAUSE_SPLIT.finditer(text):
        if m.end() <= start: a = m.end()
        elif m.start() >= end: b = m.start(); break
    return a, b


def parse_title(title_raw, source_id, taxonomy, reliability):
    """Returns (mentions, rejected, clean). Each mention is a dict; see the keys at the end of the function."""
    clean = clean_title(title_raw); text = match_form(clean); prof = reliability.profile(source_id); ctx = taxonomy.context
    ents = entities.extract(clean, prof["default_mode"])
    has_air = bool(ctx["air_cue"].search(text)) or prof["default_mode"] == "AIR"
    retrospective = bool(ctx["retrospective"].search(text))
    found, rejected = {}, []
    for name, t in taxonomy.types.items():
        for rx, conf, src in t["compiled"]:
            matches = list(rx.finditer(text))
            if not matches: continue
            m = next((x for x in matches if not ctx["contrast"].search(x.group(0))), None)
            if m is None:                                                     # the only matches straddle a contrast: the two halves are about different things
                rejected.append({"event_type": name, "reason": "CONTRAST", "pattern": src}); break
            a, b = _clause(text, m.start(), m.end()); clause = text[a:b]
            before = text[a:m.start()].split()[-taxonomy.negation_window:]
            reason = None
            if retrospective: reason = "RETROSPECTIVE"
            elif t["requires_mode"] == "AIR" and not has_air: reason = "MODE"
            elif t["excludes_rx"] is not None and t["excludes_rx"].search(text): reason = "EXCLUDED"
            elif ctx["negation"].search(" ".join(before)) or ctx["negation"].search(m.group(0)): reason = "NEGATED"
            rev = bool(ctx["reversal"].search(clause)) and t["reversible"]; hyp = bool(ctx["hypothetical"].search(clause))
            if reason is None and rev and hyp: reason = "POTENTIAL_END"
            if reason:
                rejected.append({"event_type": name, "reason": reason, "pattern": src}); break      # one decision per type and headline
            status = "ENDED" if rev else "POTENTIAL" if hyp else "ACTIVE"
            sev = t["base_severity"] + (1 if ctx["intensifier"].search(clause) else 0) - (1 if ctx["downtoner"].search(clause) else 0)
            direction = t["direction"]
            if name == "FUEL_SURCHARGE_CHANGE":
                up, down = bool(_SURCHARGE_UP.search(clause)), bool(_SURCHARGE_DOWN.search(clause))
                direction = 1 if up and not down else -1 if down and not up else 0
            duration = "LONG" if ctx["duration_long"].search(clause) else "SHORT" if ctx["duration_short"].search(clause) else "UNKNOWN"
            found[name] = {"event_type": name, "parent_category": t["category"], "feature_group": t["feature_group"], "status": status, "direction": direction,
                           "severity": max(1, min(3, sev)), "pattern_conf": conf, "pattern": src, "matched_text": m.group(0), "duration_class": duration,
                           "affected_mode": t["affected_mode"], "effects": t["effects"]}
            break                                                                                    # first matching pattern of a type decides
    located = ents["geographic_scope"] != "UNKNOWN" or ents["airlines"] or ents["carriers"]
    mentions = []
    for name, f in found.items():
        conf = f["pattern_conf"] - (0.0 if located else 0.10) - (0.15 if f["status"] == "POTENTIAL" else 0.0) - (0.10 if len(found) > 2 else 0.0)
        mentions.append({**f, "extraction_confidence": round(max(0.30, conf), 2), "source_tier": prof["tier"], "source_reliability": prof["weight"],
                         "source_type": prof["kind"], **{k: ents[k] for k in ("geographic_scope", "countries", "regions", "airports", "ports", "airlines", "carriers", "chokepoints")},
                         "raw_text_hash": text_hash(clean), "parser_version": config.PARSER_VERSION, "taxonomy_version": taxonomy.version})
    return mentions, rejected, clean
