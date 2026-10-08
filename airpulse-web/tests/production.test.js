// Production readiness of the customer application: every state it shows is read from the export, nothing about the data is
// typed into a page, a source that has aged is shown as aged whenever the page is opened, and the export publishes all or nothing.
import test from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, readFileSync, readdirSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { exportState, lateReason, needsAttention, registryNow, registryTime, sourceStatus } from '../src/lib/derive.js'

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')
const read = (p) => readFileSync(join(ROOT, p), 'utf8')
const data = (p) => JSON.parse(read(join('public', 'data', p)))
const core = data('core.json'), outlook = data('outlook.json')
const STATUSES = ['HEALTHY', 'DEGRADED', 'STALE', 'FAILED', 'UNAVAILABLE']
const DAY = 86400000
const at = (iso, days) => new Date(new Date(iso).getTime() + days * DAY)

test('a source ages in the browser: healthy at the export, stale once its limit has passed, without a new export', () => {
  const s = core.registry.sources.find((x) => x.status === 'HEALTHY' && x.production)
  const t0 = new Date(core.registry.generated_at)
  if (s) {                                                           // when every production source has failed there is none to age; the rule is still tested on the rows below
    assert.equal(sourceStatus(s, t0).status, 'HEALTHY')
    const later = sourceStatus(s, at(s.last_success, s.stale_after_days + 1))
    assert.equal(later.status, 'STALE'); assert.match(later.error, /Not checked for \d+ days/)
  }
  const fresh = { status: 'HEALTHY', last_success: '2026-10-01T00:00:00Z', latest_data: '2026-06', stale_after_days: 14, data_stale_after_days: 60, error: '' }
  assert.equal(sourceStatus(fresh, new Date('2026-10-02T00:00:00Z')).status, 'STALE', 'reached, but the newest data are older than the limit')
  assert.equal(sourceStatus({ ...fresh, latest_data: '2026-09-20' }, new Date('2026-10-02T00:00:00Z')).status, 'HEALTHY')
  assert.equal(sourceStatus({ ...fresh, status: 'DEGRADED', error: 'HTTP 503' }, new Date('2026-10-02T00:00:00Z')).status, 'DEGRADED')
  assert.equal(sourceStatus({ ...fresh, status: 'DEGRADED', error: 'HTTP 503' }, new Date('2026-11-02T00:00:00Z')).status, 'FAILED', 'a degraded source whose last success is past the limit has failed')
  for (const k of ['DISABLED', 'RESEARCH_ONLY', 'FAILED']) assert.equal(sourceStatus({ status: k, error: 'x' }, new Date('2030-01-01')).status, k)
  assert.equal(registryTime('2026-06'), Date.UTC(2026, 6, 1) - 1000, 'a month is read as its last moment'); assert.equal(registryTime(null), null); assert.equal(registryTime('not a date'), null)
  const years = at(core.registry.generated_at, 400)
  assert.equal(needsAttention(core, years).length, registryNow(core, years).filter((x) => x.production && x.status !== 'HEALTHY').length)
  assert.ok(needsAttention(core, years).length >= core.registry.sources.filter((x) => x.production && x.active).length, 'a year later every production source needs attention')
})

test('the export states its own age limit and the pages say when it has passed', () => {
  assert.ok(core.export.stale_after_days > 0 && core.export.expected_every_days > 0)
  assert.equal(exportState(core, new Date(core.generated_at)).stale, false)
  const old = exportState(core, at(core.generated_at, core.export.stale_after_days + 2))
  assert.equal(old.stale, true); assert.ok(old.days > core.export.stale_after_days)
  assert.equal(exportState({}, new Date()).stale, true, 'an export without a time is treated as stale, never as fresh')
  const bits = read('src/components/bits.jsx'), page = read('src/pages/DataPage.jsx')
  assert.match(bits, /Data delay\./); assert.match(page, /Data delay\./); assert.match(page, /registryNow\(core\)/)
  assert.match(core.export.content_hash, /^[0-9a-f]{64}$/, 'the logical content of the export is identified, so two exports of unchanged data can be compared')
})

test('the outlook advances by itself: forecasts issued since the evaluation follow the evaluated record, and a missing one is said', () => {
  const rows = outlook.forecasts
  for (const r of rows) assert.ok(r.src === 'evaluation' || r.src === 'operations', `${r.t}: every outlook says where it comes from`)
  assert.deepEqual(rows.map((r) => r.t), [...rows.map((r) => r.t)].sort(), 'in month order')
  assert.equal(new Set(rows.map((r) => r.t)).size, rows.length, 'one outlook per month')
  const seenOps = rows.findIndex((r) => r.src === 'operations')
  if (seenOps >= 0) assert.ok(rows.slice(seenOps).every((r) => r.src === 'operations'), 'operational outlooks only after the evaluated record')
  for (const r of rows.filter((x) => x.src === 'operations')) { assert.match(r.forecast_id, /\|\d{4}-\d{2}$/); assert.ok(r.generated_at && r.timing) }
  const c = outlook.current
  assert.equal(c.month_shown, rows.at(-1).t); assert.equal(c.is_current, c.month_shown === c.month_due)
  assert.match(read('src/pages/Forecast.jsx'), /Outlook not current\./)
  assert.equal(outlook.selection.later_tests.every((t) => typeof t.changed_the_outlook === 'boolean'), true)
  assert.ok(outlook.selection.approaches_validated >= 1 && outlook.selection.approaches_evaluated >= outlook.selection.approaches_validated)
  if (outlook.operational) assert.match(outlook.operational.forecast_id, /\|\d{4}-\d{2}$/)
  for (const f of ['tests/aviation.test.js', 'tests/global.test.js', 'tests/expansion.test.js', 'tests/data-contract.test.js']) assert.doesNotMatch(read(f), /engine_id, 'BL-/, `${f}: a test must not pin the forecaster that is official today`)
})

test('nothing is published half-written: the export stages, checks, then moves', () => {
  const ex = read('scripts/export_data.py')
  assert.match(ex, /OUT = PUBLISHED \+ "\.staging"/); assert.match(ex, /export incomplete, nothing published/); assert.match(ex, /export refused, nothing published/)
  assert.match(ex, /the last production run did not pass its gate/); assert.match(ex, /os\.replace\(os\.path\.join\(OUT, name\), dst\)/)
  assert.ok(ex.indexOf('os.replace(os.path.join(OUT, name), dst)') > ex.indexOf('export refused, nothing published'), 'the checks come before anything is moved into public/data')
  assert.match(ex, /selection\.select\(conn\)/); assert.doesNotMatch(ex, /OFFICIAL = ["']BL-/, 'the official forecaster is never typed')
  // one repository is hosted: its production workflow is beside this folder there, and in the engine's deploy/public here
  const wfPath = [join(ROOT, '..', '.github', 'workflows', 'production.yml'), join(process.env.AIRPULSE_ROOT || join(ROOT, '..', 'AirPlus'), 'deploy', 'public', 'production.yml')].find((p) => existsSync(p))
  assert.ok(wfPath, 'the production workflow is found'); const wf = readFileSync(wfPath, 'utf8')
  assert.match(wf, /cron:/); assert.match(wf, /scripts\/production_run\.py/); assert.match(wf, /npm run export/); assert.match(wf, /npm test/); assert.match(wf, /npm run build/); assert.match(wf, /deploy-pages/)
  assert.ok(wf.indexOf('scripts/production_run.py') < wf.indexOf('npm run export') && wf.indexOf('npm run build') < wf.indexOf('upload-pages-artifact') && wf.indexOf('upload-pages-artifact') < wf.indexOf('deploy-pages'), 'run, export, build, upload, deploy')
  assert.doesNotMatch(wf, /AIRPULSE_ENGINE_REPOSITORY|secrets\./, 'one repository, no secret')
  assert.ok(wf.indexOf('npm run export') < wf.indexOf('npm test') && wf.indexOf('npm test') < wf.indexOf('npm run build'), 'export, then tests, then build')
  for (const f of readdirSync(join(ROOT, 'src'), { recursive: true }).filter((f) => /\.(jsx?|json)$/.test(String(f)))) {
    assert.doesNotMatch(read(join('src', String(f))), /api[_-]?key|secret|token/i, `${f}: the browser holds no key`)
  }
})

test('the registry of the product lists only sources whose terms allow the use, each with one of five states', () => {
  const r = core.registry
  assert.ok(r.sources.length >= 10)
  for (const s of r.sources) {
    for (const k of ['id', 'name', 'authority', 'type', 'frequency', 'license', 'attribution', 'last_success', 'last_attempt', 'latest_data', 'status', 'error', 'coverage']) assert.ok(k in s, `${s.id}: ${k}`)
    assert.ok(STATUSES.includes(s.status), `${s.id}: ${s.status}`); assert.match(s.license, /^COMMERCIAL-SAFE/, `${s.id}: ${s.license}`); assert.ok(s.attribution.length > 10, `${s.id}: attribution`)
    if (s.status === 'HEALTHY') { assert.ok(s.last_success && s.stale_after_days > 0); assert.equal(s.error, '') }
    if (['STALE', 'DEGRADED', 'FAILED'].includes(s.status)) assert.ok(s.error.length > 0, `${s.id}: a source that is not healthy says why`)
    if (s.scheduled_runs === 0 && s.data_mode) assert.equal(s.data_mode, 'SNAPSHOT', `${s.id}: without a scheduled run nothing is called automated`)
  }
  assert.equal(r.summary.sources, r.sources.length); assert.equal(STATUSES.reduce((n, k) => n + r.summary[k], 0), r.sources.length)
  for (const banned of [/news_|eurocontrol|positions|gdelt|flight_lists|live_tracking|weekly_lane/]) assert.doesNotMatch(JSON.stringify(r.sources.map((s) => s.id)), banned, 'a source that may not be published is listed')
  assert.match(core.export.policy_audited, /^\d{4}-\d{2}-\d{2}$/); assert.ok(core.export.features.length >= 6)
})

test('no file of the product holds a field of a removed feature or an internal status word', () => {
  const dir = join(ROOT, 'public', 'data'); const files = readdirSync(dir, { recursive: true }).map(String).filter((f) => f.endsWith('.json'))
  assert.equal(files.includes('events.json'), false, 'the event record is not part of the product')
  for (const f of files) {
    const t = readFileSync(join(dir, f), 'utf8')
    for (const banned of [/EXPERIMENTAL/, /RESEARCH[-_ ]ONLY/, /DATA[-_ ]LIMITED/, /UNVERIFIED/, /NOT PREDICTIVE/, /"events"\s*:/, /"indicators"/, /second_pass/, /"watched"/, /data_groups/, /beyond_averaging/, /capacity_proxy/, /eurocontrol/])
      assert.doesNotMatch(t, banned, `${f} holds ${banned}`)
  }
  assert.equal('evidence' in outlook, false); assert.equal('events' in core, false); assert.equal('research' in core.state, false)
  assert.ok(Array.isArray(core.not_in_product) && core.not_in_product.length >= 8)
  for (const n of core.not_in_product) { assert.ok(['Removed', 'Needs a licence', 'Not validated', 'Not possible today'].includes(n.state), n.name); assert.ok(n.why.length > 30, `${n.name}: the reason is said`) }
})

test('the pages type no state, no count and no result of an experiment', () => {
  const pages = readdirSync(join(ROOT, 'src', 'pages')).filter((f) => f.endsWith('.jsx'))
  const typed = /\b(\d{2,}|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve) (known |listed |BLS |more )?(airports?|disruptions?|closures?|publications?|headlines?|forecasters?|indices|sources|scheduled runs|countries|alternatives|kinds of)\b/i
  for (const f of pages) {
    const text = read(join('src', 'pages', f)).split('\n').filter((l) => !l.trim().startsWith('//')).join('\n')
    assert.doesNotMatch(text, typed, `${f}: a count is typed into the page`)
    assert.doesNotMatch(text, /experimental|second pass|being watched|\bablation\b/i, `${f}: an internal status or a research result is on the page`)
    if (f !== 'DataPage.jsx') assert.doesNotMatch(text, /refresh is (run|started) by hand/i, `${f}: how a refresh was started is typed`)
  }
  assert.match(read('src/pages/Forecast.jsx'), /lateReason\(op\.trigger\)/); assert.match(read('src/pages/WeeklyFuel.jsx'), /lateReason\(v\.trigger\)/)
  assert.match(lateReason('schedule'), /scheduled run/); assert.match(lateReason('manual'), /started by a person/); assert.match(lateReason(undefined), /not recorded/)
  const data_ = read('src/pages/DataPage.jsx'), meth = read('src/pages/Methodology.jsx')
  for (const banned of [/Seven other/, /two publications/i, /following three releases/, /It has not run/, /Defined, never run/, />Healthy</, /Not connected/]) assert.doesNotMatch(data_, banned)
  assert.match(data_, /core\.counts\.lanes/); assert.match(data_, /core\.registry\.summary\.scheduled_runs/); assert.match(data_, /core\.schedule\.map/); assert.match(data_, /core\.status/)
  assert.match(meth, /core\.not_in_product\.map/); assert.match(meth, /core\.counts\.lanes/); assert.doesNotMatch(meth, /Eight BLS|three kinds/)
  assert.doesNotMatch(read('src/pages/Trends.jsx'), /2026/)
  assert.equal(core.counts.lanes, core.lanes.length); assert.equal(core.counts.lanes_with_outlook, core.lanes.filter((l) => l.primary).length)
  for (const s of core.schedule) { assert.match(s.cron, /^\S+ \S+ \S+ \S+ \S+$/); assert.match(s.file, /\.yml$/) }
  assert.ok(core.schedule.some((s) => /daily/.test(s.meaning)) && core.schedule.some((s) => /weekly/.test(s.meaning)) && core.schedule.some((s) => /monthly|month/.test(s.meaning)))
})

test('the newest run record is shown as recorded, and the outlook explains itself from stored fields only', () => {
  const run = core.status
  if (run) {
    assert.equal(typeof run.gate_passed, 'boolean'); assert.ok(run.runs_on_record >= run.scheduled_runs_on_record)
    if (run.run_id) { assert.match(run.run_id, /^\d{8}T\d{6}Z-[0-9a-f]{8}$/); assert.ok(['OK', 'DEGRADED', 'FAILED'].includes(run.status)); assert.ok(Array.isArray(run.sources_attempted) && typeof run.data_changed === 'boolean' && Number.isInteger(run.forecast_issued))
      const listed = new Set(core.registry.sources.map((s) => s.id)); for (const k of ['sources_attempted', 'sources_succeeded', 'sources_failed']) assert.ok(run[k].every((id) => listed.has(id)), `${k}: only sources of the product are named`) }
  }
  if (outlook.reliability) { assert.deepEqual(outlook.reliability.map((x) => x.dir).sort(), ['DOWN', 'FLAT', 'UP']); for (const x of outlook.reliability) assert.ok(x.given >= 0 && x.given <= 1 && x.happened >= 0 && x.happened <= 1) }
  const w = JSON.parse(read(join('public', 'data', 'weekly.json')))
  if (w.available && w.carry_forward) { assert.equal(typeof w.carry_forward.is_a_carry_forward, 'boolean'); assert.ok(w.carry_forward.weeks > 0) }
  if (outlook.reliability) { const sum = (k) => outlook.reliability.reduce((a, x) => a + x[k], 0); assert.ok(Math.abs(sum('given') - 1) < 1e-9 && Math.abs(sum('happened') - 1) < 1e-9, 'counted on the published record: the three shares add to one') }
  assert.match(read('src/pages/WeeklyFuel.jsx'), /cf\?\.is_a_carry_forward/)
})

test('no page promises a feature that is not in the product', () => {
  // typed copy is checked like data: the event layer, capacity statements and disruption signals were removed from the product
  const gone = /headline|trade[- ]press|disruption signal|capacity and disruption signal|event layer|event explorer|live tracking/i
  for (const f of readdirSync(join(ROOT, 'src'), { recursive: true }).filter((f) => /\.(jsx?|json)$/.test(String(f)))) {
    const t = read(join('src', String(f)))
    assert.doesNotMatch(t, gone, `${f}: names a feature that is not in the product`)
  }
  const landing = read('src/pages/Landing.jsx')
  assert.match(landing, /official counts of flights/); assert.match(landing, /states one monthly outlook with its full record/)
  const meth = read('src/pages/Methodology.jsx'); const toc = [...meth.matchAll(/\['([a-z-]+)', '[^']+'\]/g)].map((m) => m[1])
  assert.ok(toc.length >= 10, 'the contents list is read')
  for (const id of toc) assert.ok(meth.includes(`id="${id}"`), `the contents list links to #${id}, which exists`)
})
