// Derivations for display: arithmetic and counting on published values and on stored forecasts.
// No forecasting logic lives here; the outlook is read from the engine's export as it was issued.

export const MONTHLY_FROM = '2005-12' // the indices are quarterly before this month
const shift = (ym, k) => { const d = new Date(Date.UTC(+ym.slice(0, 4), +ym.slice(5, 7) - 1 + k, 1)); return d.toISOString().slice(0, 7) }

/** Monthly rows with their changes. A month BLS did not publish leaves a gap, not a two-month change. */
export function withChanges(history) {
  const rows = history.filter((r) => r.m >= MONTHLY_FROM)
  const at = Object.fromEntries(rows.map((r) => [r.m, r]))
  const ch = (r, k) => { const b = at[shift(r.m, -k)]; return b ? (r.v / b.v - 1) * 100 : null }
  // Month-on-month change and direction: final where BLS has finished revising, otherwise the first release.
  return rows.map((r) => ({ ...r, mom: r.pf ?? r.pr ?? ch(r, 1), dir: r.lf ?? r.lr ?? null, final: r.lf != null, yoy: ch(r, 12), q3: ch(r, 3) }))
}

/** The state of the market at the latest published month. */
export function marketRead(rows) {
  const last = rows.at(-1)
  const high = rows.reduce((a, b) => (b.v > a.v ? b : a))
  const low = rows.reduce((a, b) => (b.v < a.v ? b : a))
  let run = 0
  for (let i = rows.length - 1; i >= 0 && rows[i].dir === last.dir && last.dir; i--) run++
  const year = rows.slice(-12)
  return { last, high, low, run, fromHigh: (last.v / high.v - 1) * 100, yearHigh: year.reduce((a, b) => (b.v > a.v ? b : a)), yearLow: year.reduce((a, b) => (b.v < a.v ? b : a)) }
}

/** Local highs and lows: the highest (lowest) month within `window` months on either side, at least `gap` months apart. */
export function turningPoints(rows, window = 12) {
  const out = []
  rows.forEach((r, i) => {
    const seg = rows.slice(Math.max(0, i - window), i + window + 1)
    if (i < window / 2 || i > rows.length - 2) return
    if (seg.every((s) => s.v <= r.v)) out.push({ ...r, i, kind: 'high' })
    else if (seg.every((s) => s.v >= r.v)) out.push({ ...r, i, kind: 'low' })
  })
  // An unbroken plateau would repeat; keep the first month of each.
  return out.filter((p, k) => k === 0 || p.kind !== out[k - 1].kind || p.i - out[k - 1].i > 2)
}

/** Largest monthly moves on record. */
export function extremes(rows, n = 5) {
  const ch = rows.filter((r) => r.mom != null)
  return { rises: [...ch].sort((a, b) => b.mom - a.mom).slice(0, n), falls: [...ch].sort((a, b) => a.mom - b.mom).slice(0, n) }
}

/** Longest unbroken run of one direction. */
export function longestRun(rows, dir) {
  let best = null, cur = null
  for (const r of rows) {
    if (r.dir === dir) { cur = cur ? { ...cur, to: r.m, n: cur.n + 1 } : { from: r.m, to: r.m, n: 1 }; if (!best || cur.n > best.n) best = cur } else cur = null
  }
  return best
}

/** Year by year: the level at the end of the year, its change over the year, and the count of rising, stable and falling months. */
export function byYear(rows) {
  const years = {}
  for (const r of rows) (years[r.m.slice(0, 4)] ??= []).push(r)
  const ys = Object.keys(years).sort()
  return ys.map((y, k) => {
    const rs = years[y], end = rs.at(-1), prev = k ? years[ys[k - 1]].at(-1) : null
    const c = (d) => rs.filter((r) => r.dir === d).length
    return { year: y, months: rs.length, end: end.v, endMonth: end.m, change: prev ? (end.v / prev.v - 1) * 100 : null, hi: Math.max(...rs.map((r) => r.v)), lo: Math.min(...rs.map((r) => r.v)), up: c('UP'), flat: c('FLAT'), down: c('DOWN') }
  })
}

// ---- the outlook, as issued
const P = (f) => ({ DOWN: f.d, FLAT: f.f, UP: f.u })

/** The official outlook in display terms: the call, its probability, and whether another direction carries the same probability. */
export function outlookView(f) {
  if (!f || !f.p) return null
  const ps = P(f), p = ps[f.p]
  const others = Object.entries(ps).filter(([k]) => k !== f.p).sort((a, b) => b[1] - a[1])
  const tied = others.filter(([, v]) => Math.abs(v - p) < 1e-9).map(([k]) => k)
  return { dir: f.p, p, tied, closeCall: tied.length > 0, runnerUp: others[0][0], runnerUpP: others[0][1], pending: f.s === 'PENDING', probs: ps }
}

/** How the calls turned out, by the direction that was called. Counting only; scored months only. */
export function recordByCall(forecasts) {
  const out = { UP: { n: 0, correct: 0 }, FLAT: { n: 0, correct: 0 }, DOWN: { n: 0, correct: 0 } }
  for (const f of forecasts) if (f.c === 0 || f.c === 1) { out[f.p].n++; out[f.p].correct += f.c }
  return out
}

/** Calls and outcomes per year, for the history view. */
export function recordByYear(forecasts) {
  const y = {}
  for (const f of forecasts) {
    const k = f.t.slice(0, 4); y[k] ??= { year: k, n: 0, correct: 0, pending: 0 }
    if (f.c === 0 || f.c === 1) { y[k].n++; y[k].correct += f.c } else y[k].pending++
  }
  return Object.values(y).sort((a, b) => a.year.localeCompare(b.year))
}

export function lastFuelChange(fuel) {
  const m = fuel.monthly
  const a = m[m.length - 1], b = m[m.length - 2], c = m[m.length - 4], d = m[m.length - 13]
  return { month: a.m, value: a.v, m1: (a.v / b.v - 1) * 100, m3: c ? (a.v / c.v - 1) * 100 : null, y1: d ? (a.v / d.v - 1) * 100 : null }
}

/** The weekly fuel-cost outlook in view: the operational forecast when one has been issued, otherwise the newest of the record. */
export function weeklyView(w) {
  const c = w.current, last = w.forecasts.at(-1)
  if (c) {
    const f = { d: c.d, f: c.f, u: c.u, p: c.p }
    return { f, dir: c.p, p: Math.max(c.d, c.f, c.u), issued: c.issued_at, ref: c.reference_window, refMean: c.reference_mean, lastPrice: c.last_price, gap: c.gap_pct,
      pending: c.status === 'PENDING', expected: c.expected_outcome, outcome: null, actual: null, generated: c.generated_at, timing: c.timing, days: c.days_after_issuance, trigger: c.trigger }
  }
  const f = { d: last.d, f: last.f, u: last.u, p: last.p }
  return { f, dir: last.p, p: Math.max(last.d, last.f, last.u), issued: last.i, ref: last.rw, refMean: last.rm, lastPrice: last.lp, gap: last.gap,
    pending: last.s === 'PENDING', expected: null, outcome: last.o, actual: last.a, generated: null, timing: null, days: null }
}

/** The band of the record that an outlook probability falls in. Counting only. */
export function strengthOf(bands, p) {
  return bands.find((b) => p >= b.from && (p < b.to || b.to >= 1)) ?? null
}

// ---- sources: the engine's registry, with the status worked out again against the present
const DAY = 86400000
/** A time of the registry as milliseconds: a timestamp, a day, or a month (read as its last moment, as the engine does). */
export function registryTime(s) {
  if (!s || typeof s !== 'string') return null
  if (/^\d{4}-\d{2}$/.test(s)) { const [y, m] = s.split('-').map(Number); return Date.UTC(m === 12 ? y + 1 : y, m % 12, 1) - 1000 }
  const t = new Date(/^\d{4}-\d{2}-\d{2}$/.test(s) ? `${s}T00:00:00Z` : s).getTime()
  return Number.isFinite(t) ? t : null
}
/** Status of a source now. The engine worked it out when the pages were exported; a source that was healthy then is stale once its
 *  limit has passed. The same rule is applied here to the same fields, so nothing can stay "healthy" by not being looked at. */
export function sourceStatus(r, now = new Date()) {
  if (!r) return { status: 'FAILED', error: 'Not in the registry.' }
  if (r.status === 'DISABLED' || r.status === 'RESEARCH_ONLY' || r.status === 'FAILED' || r.status === 'UNAVAILABLE') return { status: r.status, error: r.error ?? '' }
  const age = (s) => { const t = registryTime(s); return t == null ? null : (now.getTime() - t) / DAY }
  const fetched = age(r.last_success), data = age(r.latest_data)
  const unchecked = fetched != null && r.stale_after_days != null && fetched > r.stale_after_days
  if (r.status === 'DEGRADED') return unchecked ? { status: 'FAILED', error: `${r.error}; last success ${Math.floor(fetched)} days ago` } : { status: 'DEGRADED', error: r.error ?? '' }
  if (unchecked) return { status: 'STALE', error: `Not checked for ${Math.floor(fetched)} days. The limit is ${r.stale_after_days} days.` }
  if (data != null && r.data_stale_after_days != null && data > r.data_stale_after_days) return { status: 'STALE', error: `The newest data are ${Math.floor(data)} days old. The limit is ${r.data_stale_after_days} days.` }
  return { status: r.status, error: r.error ?? '' }
}
/** Every source of the registry with its status now. */
export function registryNow(core, now = new Date()) {
  return (core?.registry?.sources ?? []).map((r) => ({ ...r, ...sourceStatus(r, now), status_at_export: r.status }))
}
/** Production sources that are not healthy now. A page that shows an outlook names them, so a failed or stale source cannot look fresh. */
export function needsAttention(core, now = new Date()) {
  return registryNow(core, now).filter((x) => x.production && x.status !== 'HEALTHY')
}
/** Why an outlook was generated late, said from what started the run that issued it: never typed. */
export function lateReason(trigger) {
  if (trigger === 'schedule') return 'It was issued by a scheduled run that came after the release.'
  if (trigger === 'manual' || trigger === 'manual-dispatch') return 'The run that issued it was started by a person, after the release.'
  return 'What started the run that issued it is not recorded.'
}
/** How old the export itself is, and whether that is past the limit the engine set for it. */
export function exportState(core, now = new Date()) {
  const t = registryTime(core?.generated_at), limit = core?.export?.stale_after_days
  if (t == null) return { days: null, stale: true }
  const days = (now.getTime() - t) / DAY
  return { days, stale: limit != null && days > limit, limit }
}

// Freshness of an air-traffic feed. The same bounds as the engine (hours since the newest observation): live up to 15 minutes,
// recent up to 48 hours, delayed up to 14 days, stale beyond. It is worked out when the page is opened, so data that has aged
// since the export is never called recent. A fixed historical record has no freshness: it is historical.
export const FEED_BOUNDS = [['LIVE', 0.25], ['RECENT', 48], ['DELAYED', 336]]
export function feedMode(source, now = new Date()) {
  if (!source) return { mode: 'UNAVAILABLE', hours: null }
  if (source.mode === 'HISTORICAL') return { mode: 'HISTORICAL', hours: null }
  const t = source.newest_observation ? new Date(source.newest_observation).getTime() : NaN
  if (!Number.isFinite(t)) return { mode: 'UNAVAILABLE', hours: null }
  const raw = (now.getTime() - t) / 3.6e6
  if (raw < -1) return { mode: 'UNAVAILABLE', hours: null } // an observation dated after the present cannot be given a freshness
  const hours = Math.max(raw, 0)
  for (const [mode, limit] of FEED_BOUNDS) if (hours <= limit) return { mode, hours }
  return { mode: 'STALE', hours }
}
export function ageText(hours) {
  if (hours == null) return null
  if (hours < 1) return `${Math.max(Math.round(hours * 60), 0)} minutes`
  if (hours < 48) return `${Math.floor(hours)} h ${Math.round((hours - Math.floor(hours)) * 60)} min`
  return `${Math.floor(hours / 24)} days`
}
const FEED_WORD = { LIVE: 'Live data', RECENT: 'Recent data', DELAYED: 'Data delayed', STALE: 'Stale data', UNAVAILABLE: 'Unavailable', HISTORICAL: 'Historical record' }
/** One line that states how fresh a feed is: "Recent data · last observed 18 h 40 min ago", "Historical record · through 2026-08-31 · not live". */
export function feedLine(source, now = new Date()) {
  const m = feedMode(source, now)
  if (m.mode === 'HISTORICAL') return `${FEED_WORD.HISTORICAL} · through ${source.through} · not live`
  if (m.mode === 'UNAVAILABLE') return FEED_WORD.UNAVAILABLE
  return `${FEED_WORD[m.mode]} · ${m.mode === 'LIVE' ? 'updated' : 'last observed'} ${ageText(m.hours)} ago`
}
export const bandTone = (b) => ({ NORMAL: 'normal', ELEVATED: 'elevated', UNUSUAL: 'unusual', EXTREME: 'extreme' }[b] ?? 'none')
