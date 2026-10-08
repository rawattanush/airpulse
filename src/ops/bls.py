"""The air freight price indexes read at the Bureau of Labor Statistics itself: the archived monthly releases and the public data interface.

One code path for the benchmark snapshot (scripts/build_bls_vintages.py) and for the operational adapter (src.ops.adapters.fetch_bls).
Pure functions: nothing here opens a connection or a file.

What a release publishes, and what a column of the vintage matrix holds for the release that first publishes month m (CL-024, rule 3):
    (a) month m      the index printed for it
    (b) month m-1    the index printed for it in the same table: its first revision
    (c) m-3, older   the values of the Bureau's database, final after the three releases that follow a first publication
    (d) month m-2    its second revision is not printed as an index. The same table prints the monthly percent changes
                     m-3 -> m-2 and m-2 -> m-1. Among the one-decimal values consistent with both: the single one if there is
                     one; else the value carried from the release before if it is among them; else the consistent value nearest
                     to the midpoint of the two implied values. With no consistent value the carried value is kept and flagged.
    (f) a release that prints no table (10 February 2026, after the lapse in appropriations of 2025: the database was updated,
        no detailed release was issued) adds a column in which nothing new is on record. A month first made known that way
        enters the history with the next printed release, as that table prints it.
    (e) only for a release read while it is the newest one: what it made known is read from the database at that time.
No value published after a release enters that release's column."""
import html as _html, re

ARCHIVE_LIST = "https://www.bls.gov/bls/news-release/ximpim.htm"
RELEASE_URL = "https://www.bls.gov/news.release/archives/ximpim_{mm}{dd}{yyyy}.htm"
API = "https://api.bls.gov/publicAPI/v1/timeseries/data/"            # version 1: no key; 25 queries a day, 25 series and 10 years a query
API_YEARS = 10
REVISION_RELEASES = 3
# series of the product -> (group heading, region row under it; None = the heading's own row), as the release table prints them
ROWS = {"IV131": ("Import Air Freight", None), "IV1311": ("Import Air Freight", "Europe"),
        "IC131": ("Inbound Air Freight", None), "IC1311": ("Inbound Air Freight", "Europe"), "IC1312": ("Inbound Air Freight", "Asia"),
        "IS231": ("Outbound Air Freight", None), "IS2311": ("Outbound Air Freight", "Europe"), "IS2312": ("Outbound Air Freight", "Asia")}
MONTHS = {m: i + 1 for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"))}


class ReleaseError(Exception):
    """A release page or an interface answer that does not have the expected form. Nothing is guessed."""


def bls_id(series): return "EIU" + series


def shift(month, k):
    """'YYYY-MM-01' moved by k months."""
    y, m = int(month[:4]), int(month[5:7]); n = y * 12 + (m - 1) + k
    return f"{n // 12:04d}-{n % 12 + 1:02d}-01"


def releases(list_html):
    """Archive list page -> [(release date 'YYYY-MM-DD', address)] in date order."""
    found = {f"{y}-{m}-{d}": RELEASE_URL.format(mm=m, dd=d, yyyy=y) for m, d, y in re.findall(r'/news\.release/archives/ximpim_(\d{2})(\d{2})(\d{4})\.htm', list_html)}
    if not found: raise ReleaseError("no archived release found on the list page")
    return sorted(found.items())


def _text(fragment):
    return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def _month(label):
    """'Aug. 2026', 'May 2026', 'Sept. 2026', 'August 2026' -> 'YYYY-MM-01'."""
    m = re.match(r"([A-Za-z]{3})[a-z]*\.?\s+(\d{4})$", label.strip())
    if not m or m.group(1).lower() not in MONTHS: raise ReleaseError(f"month label not understood: {label!r}")
    return f"{int(m.group(2)):04d}-{MONTHS[m.group(1).lower()]:02d}-01"


def _number(cell):
    s = re.sub(r"\([^)]*\)", "", cell).replace(",", "").replace("−", "-").strip()
    if s in ("", "-", "–", "—", "NA", "N.A."): return None
    try: return float(s)
    except ValueError: raise ReleaseError(f"cell is not a number: {cell!r}")


def table_fragment(page_html):
    """The table of transportation services of a release page, as markup. Raises when the page has none."""
    for m in re.finditer(r"(?is)<table\b.*?</table>", page_html):
        if "selected transportation services" in m.group(0) and "Inbound Air Freight" in m.group(0): return m.group(0)
    raise ReleaseError("the release has no table of transportation services with the air freight indexes")


def parse_release(page_html):
    """Release page (or its table fragment) -> {"month", "previous_month", "changes": [(from, to) x4], "series": {id: {"previous", "current", "monthly": [x4]}}}.
    Index columns: the month before and the month of the release. Monthly percent changes: the four pairs the table prints."""
    tab = table_fragment(page_html)
    head = re.search(r"(?is)<thead\b.*?</thead>", tab)
    if not head: raise ReleaseError("table without a header")
    labels = [_text(c) for c in re.findall(r"(?is)<th\b[^>]*>(.*?)</th>", head.group(0))]
    idx = [l for l in labels if re.fullmatch(r"[A-Za-z]{3,9}\.?\s+\d{4}", l)]
    pairs = [l for l in labels if re.fullmatch(r"[A-Za-z]{3,9}\.?\s+\d{4}\s+to\s+[A-Za-z]{3,9}\.?\s+\d{4}", l)]
    if len(idx) != 2 or len(pairs) != 5: raise ReleaseError(f"header not understood: {len(idx)} index columns, {len(pairs)} change columns")
    prev, cur = _month(idx[0]), _month(idx[1])
    changes = [tuple(_month(x) for x in re.split(r"\s+to\s+", p)) for p in pairs[1:]]            # pairs[0] is the annual change
    if prev != shift(cur, -1) or changes != [(shift(cur, -k - 1), shift(cur, -k)) for k in (3, 2, 1, 0)]: raise ReleaseError(f"months of the header are not consecutive: {idx}, {pairs}")
    body = re.search(r"(?is)<tbody\b.*?</tbody>", tab)
    rows, group = {}, None
    for tr in re.findall(r"(?is)<tr\b.*?</tr>", body.group(0) if body else tab):
        th = re.search(r"(?is)<th\b[^>]*>(.*?)</th>", tr)
        if not th: continue
        label = _text(th.group(1)); level = re.search(r'class="sub(\d)"', th.group(1)); cells = [_text(c) for c in re.findall(r"(?is)<td\b[^>]*>(.*?)</td>", tr)]
        if level and level.group(1) == "1": group = label
        if len(cells) != 8: continue
        region = None if (level and level.group(1) == "1") else re.sub(r"\s*\(.*$", "", label).strip()
        rows[(group, region)] = cells
    out = {}
    for sid, key in ROWS.items():
        if key not in rows: raise ReleaseError(f"row of {sid} {key} not found in the table")
        c = rows[key]; out[sid] = {"previous": _number(c[1]), "current": _number(c[2]), "monthly": [_number(x) for x in c[4:8]]}
    return {"month": cur, "previous_month": prev, "changes": changes, "series": out}


def api_request(series, start_year, end_year):
    """Body of one request to the interface for the product's series over at most API_YEARS years."""
    if end_year - start_year + 1 > API_YEARS: raise ReleaseError("more years than one request may ask for")
    return {"seriesid": [bls_id(s) for s in series], "startyear": str(start_year), "endyear": str(end_year)}


def parse_api(answer):
    """Interface answer (parsed JSON) -> {series: {'YYYY-MM-01': value}}. Monthly periods only; annual averages are not asked for."""
    if answer.get("status") != "REQUEST_SUCCEEDED": raise ReleaseError(f"interface answered {answer.get('status')}: {'; '.join(answer.get('message') or [])[:200]}")
    out = {}
    for s in answer["Results"]["series"]:
        sid = s["seriesID"][3:] if s["seriesID"].startswith("EIU") else s["seriesID"]; vals = {}
        for d in s["data"]:
            if not re.fullmatch(r"M(0[1-9]|1[0-2])", d["period"]): continue
            v = d["value"].strip()
            if v in ("", "-"): continue
            vals[f"{int(d['year']):04d}-{d['period'][1:]}-01"] = float(v)
        out[sid] = vals
    return out


def _pct(a, b): return 100.0 * (b / a - 1.0)


def consistent(low, high, carried, change_in, change_out, tol=0.05 + 1e-9):
    """One-decimal values x with: the printed change from the month before (`low` -> x) and to the month after (x -> `high`)
    both reproduced to the printed decimal. A change that is not printed puts no condition. Returns the sorted candidates."""
    if (change_in is None or low is None) and (change_out is None or high is None): return None
    spans = []
    if change_in is not None and low is not None: spans.append((low * (1 + (change_in - 0.06) / 100.0), low * (1 + (change_in + 0.06) / 100.0)))
    if change_out is not None and high is not None: spans.append((high / (1 + (change_out + 0.06) / 100.0), high / (1 + (change_out - 0.06) / 100.0)))
    lo = max(min(s) for s in spans); hi = min(max(s) for s in spans); out = []
    k = int(lo * 10) - 1
    while k / 10.0 <= hi + 0.11:
        x = round(k / 10.0, 1); k += 1
        if x <= 0: continue
        if change_in is not None and low is not None and abs(_pct(low, x) - change_in) > tol: continue
        if change_out is not None and high is not None and abs(_pct(x, high) - change_out) > tol: continue
        out.append(x)
    return out


def second_revision(low, high, carried, change_in, change_out):
    """Rule (d). Returns (value, how): how is one of
    'd1 single consistent value', 'd2 carried, consistent', 'd3 nearest consistent value', 'd4 carried, no consistent value', 'd0 carried, no change printed'."""
    cand = consistent(low, high, carried, change_in, change_out)
    if cand is None: return carried, "d0 carried, no change printed"
    if len(cand) == 1: return cand[0], "d1 single consistent value"
    if carried is not None and any(abs(c - carried) < 1e-9 for c in cand): return carried, "d2 carried, consistent"
    if not cand: return carried, "d4 carried, no consistent value"
    implied = []
    if change_in is not None and low is not None: implied.append(low * (1 + change_in / 100.0))
    if change_out is not None and high is not None: implied.append(high / (1 + change_out / 100.0))
    mid = sum(implied) / len(implied)
    return min(cand, key=lambda c: (abs(c - mid), c)), "d3 nearest consistent value"


def column(release, series, final, previous=None):
    """The column of one release for one series: ({month: value}, [(month, rule)]) for the cells rules (a), (b) and (d) produced.
    release: parse_release(...); final: {month: database value}; previous: the column of the release before, or None for the first."""
    r = release["series"][series]; m = release["month"]; m1, m2, m3 = shift(m, -1), shift(m, -2), shift(m, -3); how = []
    col = {k: v for k, v in final.items() if k <= m3}                                             # (c)
    if previous is None:
        if m2 in final: col[m2] = final[m2]; how.append((m2, "c first release of the span: database value"))
    else:
        for k, v in previous.items():                                                           # a month the table does not print keeps what was known
            if k > m3 and k not in col: col[k] = v
        carried = previous.get(m2)
        v, rule = second_revision(col.get(m3), r["previous"], carried, r["monthly"][1], r["monthly"][2])
        if v is not None: col[m2] = v
        how.append((m2, rule))
    if r["previous"] is not None: col[m1] = r["previous"]; how.append((m1, "b first revision, printed"))
    if r["current"] is not None: col[m] = r["current"]; how.append((m, "a first publication, printed"))
    return col, how


def column_without_table(previous):
    """Rule (f): the column of a release that prints no table repeats what was known."""
    return dict(previous or {}), [("", "f no table printed: nothing new on record")]


def column_from_database(previous, database, release_date):
    """Rule (e), for a release without a table read while it is the newest: the months after those already final in the column
    before are what the database shows now. Months dated after the release are not taken."""
    known = sorted(previous); floor = shift(known[-1], -REVISION_RELEASES + 1) if known else "0000-00-00"
    col = dict(previous); how = []
    for k in sorted(database):
        if k >= floor and k < release_date[:8] + "01" and database[k] != previous.get(k): col[k] = database[k]; how.append((k, "e database value read while the release was the newest"))
    return col, how


def matrix_text(series, dates, columns):
    """Vintage matrix as the engine reads it: rows = observation months, one column per release, empty where nothing was published."""
    seen = sorted({k for c in columns for k in c}); months = []; k = seen[0]
    while k <= seen[-1]: months.append(k); k = shift(k, 1)                                     # every month from the first to the last, as the stored matrices have always had
    lines = ["observation_date," + ",".join(f"{series}_{d.replace('-', '')}" for d in dates)]
    for mth in months: lines.append(mth + "," + ",".join(("" if mth not in c else f"{c[mth]:.1f}") for c in columns))
    return "\n".join(lines) + "\n"
