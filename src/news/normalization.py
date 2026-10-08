"""Text and time normalisation (REQ-NEWS-002). Pure functions."""
import hashlib, html, re, unicodedata

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
_PUNCT = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-", "…": "...", " ": " "})
# "may" as a month must not be read as the modal verb
_MAY_MONTH = re.compile(r"\b(in|for|of|during|since|by|from|until|through|to|versus|vs|last|this|early|late|mid|end|and) may\b|\bmay (\d{1,4}\b|figures|data|volumes?|traffic|results|report|statistics|numbers|\d{4})|\bmay's\b")


def clean_title(raw):
    """Display form: HTML entities and tags removed, typographic punctuation made plain, whitespace collapsed."""
    t = html.unescape(html.unescape(raw or "")); t = _TAG.sub(" ", t).translate(_PUNCT)
    return _WS.sub(" ", unicodedata.normalize("NFKC", t)).strip()


def match_form(clean):
    """Form used for pattern matching: lower case, month 'may' disambiguated."""
    t = clean.lower()
    return _MAY_MONTH.sub(lambda m: m.group(0).replace("may", "maymonth"), t)


def text_hash(clean):
    """Hash of the normalised headline (case and punctuation insensitive); identifies re-posts of the same headline."""
    key = re.sub(r"[^a-z0-9 ]", "", clean.lower()); key = _WS.sub(" ", key).strip()
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def tokens(clean):
    return re.findall(r"[a-z0-9][a-z0-9'\-]*", clean.lower())
