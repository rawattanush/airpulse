// The weekly fuel-cost outlook, the evidence behind the monthly outlook, and the quality fields of every source.
// These tests read the exported data and the source. They fail if the weekly outlook could be mistaken for a freight forecast,
// if a forecast is not a valid probability distribution, if an engine label reaches a customer, or if a source lacks a quality field.
import test from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { execFileSync } from 'node:child_process'
import { fmtWeekday } from '../src/lib/format.js'

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')
const read = (p) => readFileSync(join(ROOT, p), 'utf8')
const data = (p) => JSON.parse(read(join('public', 'data', p)))
const core = data('core.json'), outlook = data('outlook.json'), weekly = data('weekly.json')
const DIRS = ['DOWN', 'FLAT', 'UP']
const near = (a, b, tol = 1e-9) => Math.abs(a - b) <= tol

// The weekly fuel-cost outlook left the product with the licence repair: its release windows and its record existed only through a
// relay service whose terms forbid keeping the data. These tests replace the tests of its figures: they fail if any of it is still shown.
test('the weekly fuel-cost outlook is not offered, and the product says why', () => {
  assert.equal(weekly.available, false)
  assert.deepEqual(Object.keys(weekly).sort(), ['available', 'reason'], 'no figure of the earlier weekly record is carried')
  assert.ok(weekly.reason.length > 60)
  const off = core.not_in_product.find((n) => /Weekly fuel-cost outlook/.test(n.name))
  assert.ok(off, 'listed among what is not in the product'); assert.equal(off.state, 'Needs a licence'); assert.equal(off.why, weekly.reason)
  assert.ok(!core.export.features.includes('weekly_fuel_outlook'))
  assert.equal(core.through.weekly_fuel_release, null); assert.equal(core.export.datasets.weekly_fuel_vintages, null)
})

test('no page leads to a weekly outlook or states one', () => {
  assert.doesNotMatch(read('src/components/Shell.jsx'), /to: '\/market\/weekly'/, 'not in the navigation')
  assert.doesNotMatch(read('src/pages/Overview.jsx'), /\/market\/weekly/)
  const page = read('src/pages/WeeklyFuel.jsx')
  assert.match(page, /if \(!w\.available\)/); assert.match(page, /Not offered/); assert.match(page, /\{w\.reason\}/)       // a deep link shows the reason, never a figure
  assert.match(read('src/pages/Market.jsx'), /weekly\?\.available \? weeklyView\(weekly\) : null/)
  assert.match(read('src/pages/Methodology.jsx'), /\{weekly\?\.available && \(/)
  assert.match(read('src/pages/DataPage.jsx'), /The weekly fuel-cost outlook is not offered either/)
  assert.equal(fmtWeekday('2026-09-30'), 'Wednesday'); assert.equal(fmtWeekday(null), '—')
})

test('what the product is, in the words asked of it: an official benchmark, not a quote, no 7 to 14 day rate forecast', () => {
  const m = read('src/pages/Methodology.jsx')
  assert.match(m, /An official benchmark, not a shipment quote/); assert.match(m, /price index of the U\.S\. Bureau of Labor Statistics/); assert.match(m, /no live quote for a lane/)
  assert.match(m, /does not claim a validated forecast of a commercial lane rate over the next 7 to 14 days/)
})

test('fuel is shown under neutral names and every source says where it stands', () => {
  assert.deepEqual(Object.keys(core.fuel).sort(), ['brent', 'jet'])
  for (const k of ['jet', 'brent']) { assert.ok(core.fuel[k].latest_date && core.fuel[k].latest_value > 0 && core.fuel[k].monthly.length > 100); assert.match(core.fuel[k].series, /^[A-Z0-9_]+$/) }
  for (const s of core.registry.sources) { assert.ok(['CLEARED', 'PENDING_CONFIRMATION'].includes(s.licence_status), `${s.id}: ${s.licence_status}`); assert.equal(s.awaiting === null, s.licence_status === 'CLEARED') }
  assert.match(read('src/pages/DataPage.jsx'), /x\.awaiting && <span className="obs-why">Awaiting/)
})

test('nothing of the retired access path reaches the exported data or the pages', () => {
  const retired = new RegExp(['stlouis' + 'fed', '\\b(?:AL)?' + 'FR' + 'ED' + '\\b', 'alfr' + 'ed_', '\\bfr' + 'ed_', 'DJFUEL' + 'USGULF', 'DCOIL' + 'BRENTEU'].join('|'))
  for (const f of ['public/data/core.json', 'public/data/outlook.json', 'public/data/weekly.json', 'public/data/replay.json', 'src/pages/FuelPrices.jsx', 'src/pages/DataPage.jsx', 'src/pages/Methodology.jsx', 'src/pages/Overview.jsx', 'src/pages/Market.jsx', 'src/components/Shell.jsx', 'scripts/export_data.py'])
    assert.doesNotMatch(read(f), retired, f)
})

test('no engine label of the expansion reaches the customer data or the pages', () => {
  const banned = [/W-(GAP|MAJ|PER|SEA|LOGIT|GBT)/, /RLOGIT|SEATREND|SEA-SHRUNK|SEA-RECENT|PLATT|\bFTL\b|ENS-EQ/, /\bbrier\b/i, /log_?loss/i, /LightGBM/i, /random forest/i, /isotonic/i]
  for (const f of ['public/data/weekly.json', 'public/data/outlook.json', 'public/data/core.json', 'src/pages/WeeklyFuel.jsx', 'src/pages/Forecast.jsx', 'src/pages/Methodology.jsx', 'src/pages/Market.jsx', 'src/pages/Overview.jsx']) {
    const t = read(f)
    for (const b of banned) assert.equal(b.test(t), false, `${f} contains ${b}`)
  }
})

test('overview wording: outlook probability, historical record, no single-direction record', () => {
  const t = read('src/pages/Overview.jsx')
  assert.match(t, /Outlook probability/); assert.match(t, /Historical record/)
  assert.doesNotMatch(t, /Model probability/i); assert.doesNotMatch(t, /Record, all outlooks/); assert.doesNotMatch(t, /recordByCall/)
  assert.match(t, /index through/); assert.match(t, /fuel through/)
  for (const f of ['src/pages/Forecast.jsx', 'src/pages/Landing.jsx', 'src/pages/Methodology.jsx']) assert.doesNotMatch(read(f), /Model probability/i)
  assert.match(read('src/pages/Forecast.jsx'), /recordByCall/, 'the record by direction stays on the forecast page')
})

test('a source that needs attention is counted on the data page', () => {
  assert.match(read('src/pages/DataPage.jsx'), /sources need'\} attention|source needs/)
})

test('the export refuses an invalid forecast', () => {
  const venv = [join(ROOT, '..', 'AirPlus', '.venv', 'Scripts', 'python.exe'), join(ROOT, '..', '.venv', 'Scripts', 'python.exe'), join(ROOT, '..', '.venv', 'bin', 'python')].find((p) => existsSync(p)) ?? ''
  const py = process.env.AIRPULSE_PYTHON || (existsSync(venv) ? venv : 'python')     // the guard needs only the standard library
  const run = (args) => { try { execFileSync(py, [join(ROOT, 'scripts', 'guards.py'), ...args], { stdio: 'pipe' }); return 0 } catch (e) { return e.status } }
  assert.equal(run(['0.2', '0.3', '0.5', 'UP']), 0)
  assert.notEqual(run(['0.2', '0.3', '0.6', 'UP']), 0, 'probabilities that do not sum to one')
  assert.notEqual(run(['-0.1', '0.6', '0.5', 'UP']), 0, 'a negative probability')
  assert.notEqual(run(['0.2', '0.3', '0.5', 'SIDEWAYS']), 0, 'a direction that does not exist')
  assert.notEqual(run(['nan', '0.5', '0.5', 'UP']), 0, 'a probability that is not a number')
})
