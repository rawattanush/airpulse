"""The daily spot prices read at the Energy Information Administration itself: one spreadsheet per series, whole history.

Pure functions: nothing here opens a connection or a file. The spreadsheet is turned into the two-column file the engine has
always read (observation_date, value); values are never altered. The Administration's table names a commercial data vendor
as the source of these prices; whether that limits reuse is an open question recorded in the production policy (KI-107)."""
import io

URL = "https://www.eia.gov/dnav/pet/hist_xls/{series}d.xls"
SHEET = "Data 1"
# series of the product: the Administration's own source keys
SERIES = {"EER_EPJK_PF4_RGC_DPG": "U.S. Gulf Coast Kerosene-Type Jet Fuel Spot Price FOB (Dollars per Gallon)",
          "RBRTE": "Europe Brent Spot Price FOB (Dollars per Barrel)"}


class SpreadsheetError(Exception):
    """A spreadsheet that does not have the expected form. Nothing is guessed."""


def url(series): return URL.format(series=series)


def parse_xls(body, series):
    """Spreadsheet bytes -> [(observation date 'YYYY-MM-DD', value)] in file order. The sheet must name the series asked for."""
    import xlrd
    try:
        wb = xlrd.open_workbook(file_contents=body); sh = wb.sheet_by_name(SHEET)
    except Exception as e:
        raise SpreadsheetError(f"cannot open the sheet {SHEET!r} ({type(e).__name__}: {e})")
    keys = [str(sh.cell_value(i, 1)).strip() for i in range(min(sh.nrows, 6)) if str(sh.cell_value(i, 0)).strip() == "Sourcekey"]
    if keys != [series]: raise SpreadsheetError(f"the sheet holds the series {keys or 'none'}, not {series}")
    rows = []
    for i in range(sh.nrows):
        d, v = sh.cell(i, 0), sh.cell(i, 1)
        if d.ctype != xlrd.XL_CELL_DATE: continue
        if v.ctype != xlrd.XL_CELL_NUMBER: continue                                            # a day without a price is not an observation
        rows.append((xlrd.xldate_as_datetime(d.value, wb.datemode).strftime("%Y-%m-%d"), float(v.value)))
    if not rows: raise SpreadsheetError("no observation in the sheet")
    return rows


def csv_text(series, rows):
    """The file the engine reads. A price is written with the shortest decimal form that reads back to the same number."""
    buf = io.StringIO(); buf.write(f"observation_date,{series}\n")
    for d, v in rows: buf.write(f"{d},{v!r}\n")
    return buf.getvalue()
