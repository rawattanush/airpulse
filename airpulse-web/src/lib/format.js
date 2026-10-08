// Formatting and customer language. No numbers originate here: every value shown comes from the exported data.
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const MONTH = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']

export const monthShort = (i) => MON[i]
export const monthName = (i) => MONTH[i]
export const fmtMonth = (ym) => (ym ? `${MON[+ym.slice(5, 7) - 1]} ${ym.slice(0, 4)}` : '—')
export const fmtMonthLong = (ym) => (ym ? `${MONTH[+ym.slice(5, 7) - 1]} ${ym.slice(0, 4)}` : '—')
export const monthOnly = (ym) => (ym ? MONTH[+ym.slice(5, 7) - 1] : '—')
export const fmtDay = (d) => (d ? `${+d.slice(8, 10)} ${MON[+d.slice(5, 7) - 1]} ${d.slice(0, 4)}` : '—')
export const fmtWeekday = (d) => (d ? ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'][new Date(`${d.slice(0, 10)}T00:00:00Z`).getUTCDay()] : '—')
export const fmtDayLong = (d) => (d ? `${+d.slice(8, 10)} ${MONTH[+d.slice(5, 7) - 1]} ${d.slice(0, 4)}` : '—')
export const fmtPeriod = (p) => (!p ? '—' : p.length === 7 ? fmtMonth(p) : fmtDay(p)) // a month (2026-08) or a day (2026-09-08)
export const fmtTime = (ts) => (ts ? `${fmtDay(ts)}, ${ts.slice(11, 16)} UTC` : '—')
export const num = (v, d = 1) => (v == null ? '—' : v.toLocaleString('en-GB', { minimumFractionDigits: d, maximumFractionDigits: d }))
export const int = (v) => (v == null ? '—' : v.toLocaleString('en-GB'))
export const signed = (v, d = 1) => (v == null ? '—' : `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toFixed(d)}`)
export const pct = (v, d = 1) => (v == null ? '—' : `${signed(v, d)}%`)
export const prob = (v) => (v == null ? '—' : `${Math.round(v * 100)}%`)
export const share = (a, b) => (b ? `${Math.round((a / b) * 100)}%` : '—')

// The three directions in customer words. The engine's own labels (UP / FLAT / DOWN) never reach the screen.
export const DIR = {
  UP: { word: 'Rising', past: 'rose', verb: 'rise', glyph: '↑', cls: 'up' },
  FLAT: { word: 'Stable', past: 'held', verb: 'hold', glyph: '→', cls: 'flat' },
  DOWN: { word: 'Falling', past: 'fell', verb: 'fall', glyph: '↓', cls: 'down' },
}
export const dirWord = (d) => (d ? DIR[d].word : '—')

// Market context at issuance (the engine's meaning strings, shortened for customers).
export const CONTEXT = {
  own_chg_1: 'Index, latest published month',
  own_chg_3m: 'Index, latest three months',
  peers_chg_1: 'Other air-freight indices, latest month',
  jet_chg_1m: 'Jet fuel, one month',
  jet_chg_3m: 'Jet fuel, three months',
  brent_chg_1m: 'Brent crude, one month',
}

export const CURRENCIES = [
  { code: 'USD', label: 'US dollar' }, { code: 'EUR', label: 'Euro' }, { code: 'INR', label: 'Indian rupee' }, { code: 'GBP', label: 'Pound sterling' },
]
export function money(v, code, digits = 2) {
  if (v == null || !Number.isFinite(v)) return '—'
  try { return new Intl.NumberFormat(code === 'INR' ? 'en-IN' : 'en-GB', { style: 'currency', currency: code, minimumFractionDigits: digits, maximumFractionDigits: digits }).format(v) } catch { return `${code} ${v.toFixed(digits)}` }
}
