// Air traffic in the public product: counts from official sources and nothing derived from them. These tests read the
// exported data and the pages, and fail if an expected level, a reading, a capacity figure, a source whose terms do not
// allow the use, or the word live finds its way back.
import test from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, readFileSync, readdirSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { sourceStatus } from '../src/lib/derive.js'

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')
const read = (p) => readFileSync(join(ROOT, p), 'utf8')
const data = (p) => JSON.parse(read(join('public', 'data', p)))
const av = data('aviation.json'), core = data('core.json')
const text = JSON.stringify(av)

test('only the two observation features are exported, each from a source the policy allows', () => {
  assert.equal(av.available, true)
  const allowed = new Set(core.registry.sources.map((s) => s.id))
  assert.deepEqual(av.sources.map((s) => s.id).sort(), ['hkia', 'usdot'].filter((id) => allowed.has(id)).sort())
  for (const s of av.sources) {
    assert.ok(allowed.has(s.id), `${s.id} is listed in the registry of the product`)
    assert.match(s.license_class, /^COMMERCIAL-SAFE/, `${s.id}: terms allow the use`)
    assert.ok(s.attribution.length > 20 && s.through && s.collected && s.registry.status)
    assert.ok(['HEALTHY', 'DEGRADED', 'STALE', 'FAILED', 'UNAVAILABLE'].includes(s.registry.status))
    if (s.registry.scheduled_runs === 0) assert.match(s.collected, /no scheduled run is on record/i)
  }
  assert.deepEqual(Object.keys(av).sort(), ['airport', 'available', 'generated_at', 'not_shown', 'route_window', 'routes', 'sources', 'statement'])
  assert.ok(core.export.features.includes('hong_kong_airport_activity') && core.export.features.includes('us_route_departures'))
})

test('nothing derived is in the data: no expected level, no reading, no capacity, no position picture, no experiment', () => {
  for (const banned of [/"expected"/, /"band"/, /"z"\s*:/, /"ratio"/, /"statement"\s*:\s*"[A-Z]{3}:/, /capacity_proxy/, /"positions"/, /"validation"/, /market_connection/, /south_asia/, /"corridors"/, /"flagged"/, /"capabilities"/,
    /eurocontrol/i, /EXPERIMENTAL|RESEARCH-ONLY|DATA-LIMITED/, /DEFICIT|SURPLUS/, /"mode"\s*:\s*"LIVE"/])
    assert.doesNotMatch(text, banned, `${banned} is in the public air-traffic data`)
  assert.match(av.statement, /Nothing here is an estimate of cargo capacity, an expected level, a cause or a statement about freight prices/)
})

test('Hong Kong: counts as archived; a day that was not archived is absent; cancelled flights are beside movements', () => {
  const a = av.airport
  assert.equal(a.iata, 'HKG'); assert.equal(a.series.length, Math.min(a.days_archived, 120)); assert.equal(a.series.at(-1).d, a.through); assert.equal(a.latest.day, a.through)
  for (const r of a.series) { assert.ok(Number.isInteger(r.m) && r.m >= 0 && r.c + r.p <= r.m && r.x >= 0, r.d); assert.match(r.d, /^\d{4}-\d{2}-\d{2}$/) }
  assert.equal(a.latest.movements, a.latest.arrivals + a.latest.departures)
  assert.equal(a.latest.movements, a.series.at(-1).m); assert.equal(a.latest.cancellations, a.series.at(-1).x)
  assert.ok(a.cancellations.total >= a.cancellations.largest && a.cancellations.days_with_any <= a.days_archived)
  assert.equal(new Set(a.series.map((r) => r.d)).size, a.series.length)
  assert.ok(a.cargo_first_stops.every((x) => x.last > 0 && Number.isInteger(x.previous)) && a.window_days > 0)
})

test('US routes: monthly counts as published, marked historical, with gaps left as gaps', () => {
  assert.ok(av.routes.length > 0 && av.routes.length <= av.route_window.routes)
  for (const r of av.routes) {
    assert.match(r.id, /^[A-Z0-9]{3}-[A-Z0-9]{3}$/); assert.equal(r.latest.month, av.route_window.through)
    assert.ok(r.series.every((p) => p.a === null || (Number.isInteger(p.a) && p.a >= 0)), `${r.id}: a count or a gap`)
    assert.ok(r.all_cargo_share === null || (r.all_cargo_share >= 0 && r.all_cargo_share <= 1))
    assert.deepEqual(Object.keys(r.series[0]).sort(), ['a', 'm'])
  }
  const sorted = [...av.routes].sort((x, y) => y.departures_last_12_months - x.departures_last_12_months)
  assert.deepEqual(av.routes.map((r) => r.id), sorted.map((r) => r.id), 'ordered by the count that is shown')
  const page = read('src/pages/AirTraffic.jsx'), route = read('src/pages/RoutePage.jsx')
  assert.match(page, /this is a historical record, not a current figure/); assert.match(route, /Historical record/); assert.match(route, /A count of flights is not cargo capacity/)
})

test('the pages show counts only and never the word live, an expected level or a reading of what is unusual', () => {
  for (const f of ['src/pages/AirTraffic.jsx', 'src/pages/RoutePage.jsx']) {
    const t = read(f).split('\n').filter((l) => !l.trim().startsWith('//')).join('\n')
    for (const banned of [/\blive\b/i, /unusual/i, /expected level|expected\b/i, /\bband\b/i, /anomal/i, /deficit|surplus/i, /experimental/i, /capacity proxy/i, /caused by/i, /prices will/i])
      assert.doesNotMatch(t.replace(/an expected level, a cause/g, ''), banned, `${f}: ${banned}`)
  }
  assert.equal(existsSync(join(ROOT, 'src', 'pages', 'AirportPage.jsx')), false)
  const pages = readdirSync(join(ROOT, 'src', 'pages'))
  for (const gone of ['Intelligence.jsx', 'Events.jsx', 'EventDetail.jsx', 'Drivers.jsx']) assert.equal(pages.includes(gone), false, `${gone} is not part of the product`)
  const main = read('src/main.jsx')
  assert.doesNotMatch(main, /path="\/intelligence"|events\/:id|airport\/:code/); assert.match(main, /path="\/operations\/route\/:id"/)
})

test('a source card works its state out again against the present', () => {
  const s = av.sources[0], t0 = new Date(av.generated_at)
  assert.equal(sourceStatus(s.registry, t0).status, s.registry.status)
  if (s.registry.status === 'HEALTHY') {
    const later = new Date(new Date(s.registry.last_success).getTime() + (s.registry.stale_after_days + 2) * 86400000)
    assert.equal(sourceStatus(s.registry, later).status, 'STALE')
  }
  assert.equal(sourceStatus({ status: 'UNAVAILABLE', error: '' }, new Date()).status, 'UNAVAILABLE')
  assert.match(read('src/pages/AirTraffic.jsx'), /sourceStatus\(s\.registry, now\)/)
})

test('the export refuses what the policy refuses, and withholds a feed that fails a check', () => {
  const ex = read('scripts/export_aviation.py'), main = read('scripts/export_data.py')
  assert.match(ex, /policy\.feature_refusal\(feature, pol\)/); assert.match(ex, /Withheld: the data held failed a check/)
  assert.doesNotMatch(ex, /AIRPULSE_COMMERCIAL|european_daily|hkg_operations|daily_scores|monthly_scores|load_positions/, 'nothing but counts is computed for the public file')
  assert.match(main, /policy\.publishable_sources\(POLICY\)/); assert.match(main, /not a production field/); assert.match(main, /sources listed that the policy refuses/)
  assert.doesNotMatch(main, /AIRPULSE_COMMERCIAL/)
  assert.equal(typeof av.not_shown, 'object')
  for (const k of Object.keys(av.not_shown)) assert.ok(av.not_shown[k].length > 10)
})
