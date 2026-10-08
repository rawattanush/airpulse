// What the customer application is allowed to hold. These tests read the exported data (public/data) and the source,
// and fail if a second forecast, a technical score, or an invented number has found its way in.
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')
const data = (p) => JSON.parse(readFileSync(join(ROOT, 'public', 'data', p), 'utf8'))
const walk = (dir, out = []) => { for (const f of readdirSync(dir)) { const p = join(dir, f); statSync(p).isDirectory() ? walk(p, out) : out.push(p) } return out }
const core = data('core.json'), outlook = data('outlook.json'), replay = data('replay.json')
const ORDER = ['DOWN', 'FLAT', 'UP']

test('one official forecast: the export holds one approach and names how it was selected', () => {
  const o = outlook.official
  assert.equal(typeof o.engine_id, 'string')
  assert.match(o.selection, /best record/)
  assert.equal(o.other_approaches_with_a_better_record, 0, 'the official approach must be the one the evaluation supports')
  assert.equal(outlook.lane, core.primary)
  assert.ok(o.hit_rate > o.chance_rate && o.hit_rate < 1)
  assert.ok(o.months_scored >= 100)
})

test('no other model and no technical score is in the customer data', () => {
  const files = walk(join(ROOT, 'public', 'data')).filter((f) => f.endsWith('.json'))
  const text = files.map((f) => readFileSync(f, 'utf8')).join('\n')
  for (const term of [/BL-MAJ|BL-PER|ML-LOGIT|ML-GBT/, /brier/i, /log_?loss/i, /LightGBM/i, /macro_f1/i, /confusion/i, /"forecasters"/, /params/])
    assert.equal(term.test(text), false, `customer data contains ${term}`)
  assert.equal(walk(join(ROOT, 'public', 'data')).some((f) => f.includes(`${join('data', 'series')}`)), false, 'the earlier per-series export (all forecasters) must be gone')
})

test('every outlook is a valid forecast and its explanation is the stored forecast', () => {
  assert.ok(outlook.forecasts.length >= 120)
  for (const f of outlook.forecasts) {
    const p = { DOWN: f.d, FLAT: f.f, UP: f.u }
    assert.ok(Math.abs(f.d + f.f + f.u - 1) < 1e-9, `${f.t}: probabilities sum to one`)
    const best = ORDER.reduce((a, k) => (p[k] > p[a] + 1e-12 ? k : a), 'DOWN')       // ties go to the first in the fixed order
    assert.equal(f.p, best, `${f.t}: the outlook is the most probable direction`)
    assert.ok(f.i < f.o, `${f.t}: issued before its outcome was published`)
    if (f.c != null) assert.equal(f.c, f.a === f.p ? 1 : 0)
    const b = f.basis
    assert.equal(b.kind, outlook.official.method)
    assert.equal(b.calendar_month, +f.t.slice(5, 7))
    assert.equal(b.down + b.flat + b.up, b.years)
    for (const [k, n] of [['d', b.down], ['f', b.flat], ['u', b.up]]) assert.ok(Math.abs((n + 1) / (b.years + 3) - f[k]) < 1e-9, `${f.t}: the seasonal record reproduces the probability`)
    assert.ok(b.last_year < +f.t.slice(0, 4), `${f.t}: only earlier years`)
  }
  const all = outlook.record.FINAL.find((r) => r.period === 'ALL')
  const scored = outlook.forecasts.filter((f) => f.c != null)
  assert.equal(all.months, scored.length); assert.equal(all.correct, scored.filter((f) => f.c === 1).length)
  assert.ok(Math.abs(all.hit_rate - all.correct / all.months) < 1e-9)
})

test('replay: nothing after the issuance date, and the same outlook as the forecast page', () => {
  assert.equal(replay.months.length, outlook.forecasts.length)
  const byMonth = Object.fromEntries(outlook.forecasts.map((f) => [f.t, f]))
  for (const b of replay.months) {
    const f = byMonth[b.target_month]
    assert.equal(b.outlook.p, f.p)
    for (const k of ['d', 'f', 'u']) assert.ok(Math.abs(b.outlook[k] - f[k]) < 1e-12, `${b.target_month}: replay and forecast page hold the same probability`)
    assert.equal(b.issuance_date, f.i)
    assert.equal(b.leakage_check.passed, true, b.target_month)
    assert.ok(b.leakage_check.latest_input_publication <= b.issuance_date)
    for (const r of b.available_then) if (r.published !== 'not yet published') assert.ok(r.published <= b.issuance_date, `${b.target_month}: ${r.input} published after issuance`)
    for (const o of [b.outcome_first_release, b.outcome_final]) if (o.label_date) assert.ok(o.label_date > b.issuance_date, `${b.target_month}: outcome known before issuance`)
    assert.equal(Object.keys(b).includes('forecasts'), false, 'the replay holds one outlook, not a list of forecasters')
  }
})

test('the data state is what the run records say', () => {
  const s = core.state
  assert.ok(['SNAPSHOT', 'AUTOMATED', 'LIVE'].includes(s.data_mode))
  if (s.scheduled_runs === 0) assert.equal(s.data_mode, 'SNAPSHOT', 'without a scheduled run the data are a snapshot')
  assert.equal(core.lanes.filter((l) => l.primary).length, 1)
  assert.equal(core.lanes.length, 8)
  assert.match(core.proxy_statement, /proxy/)
  for (const l of core.lanes) assert.equal('newest_forecast' in l || 'metrics' in l, false, 'lanes carry the published index only')
})

test('the source never shows an engine label, a model name or a technical score to a customer', () => {
  const src = walk(join(ROOT, 'src')).filter((f) => /\.(jsx|js)$/.test(f))
  const banned = [/LightGBM/i, /\bBrier\b/i, /logistic (regression|model)/i, /boosted trees/i, /majority class/i, /\bP\((UP|FLAT|DOWN)\)/, /\bModel [ABC]\b/, /log loss/i, /training rows/i, /feature matrix/i, /BL-(MAJ|PER|SEA)|ML-(LOGIT|GBT)/]
  for (const f of src) {
    const t = readFileSync(f, 'utf8')
    for (const b of banned) assert.equal(b.test(t), false, `${f} contains ${b}`)
  }
  const pages = src.filter((f) => f.includes(`${join('src', 'pages')}`)).map((f) => readFileSync(f, 'utf8')).join('\n')
  assert.equal(/setFid|Forecaster|forecasters/.test(pages), false, 'no page lets a customer choose between forecasters')
})

test('the estimate page shows no route-level number of its own', () => {
  const t = readFileSync(join(ROOT, 'src', 'pages', 'Estimate.jsx'), 'utf8')
  assert.match(t, /Not yet available/); assert.match(t, /Scenario only/); assert.match(t, /Not an AirPulse forecast/)
  assert.equal(/useOutlook|useMarket|useCore\(|outlook\.|latest_value/.test(t), false, 'the calculator takes no AirPulse output as its movement')
  assert.equal(/useState\('[0-9]/.test(t), false, 'no pre-filled rate, weight or movement')
})
