// What the third pass changed for a customer: the weekly fuel outlook says what it is, a source that needs attention is named
// wherever an outlook is shown, and the refresh command reports the state of every production source without hiding a failure.
import test from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { execFileSync } from 'node:child_process'
import { needsAttention } from '../src/lib/derive.js'

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')
const read = (p) => readFileSync(join(ROOT, p), 'utf8')
const data = (p) => JSON.parse(read(join('public', 'data', p)))
const core = data('core.json'), weekly = data('weekly.json')
const venv = [join(ROOT, '..', 'AirPlus', '.venv', 'Scripts', 'python.exe'), join(ROOT, '..', '.venv', 'Scripts', 'python.exe')].find((p) => existsSync(p)) ?? '', venvPosix = [join(ROOT, '..', 'AirPlus', '.venv', 'bin', 'python'), join(ROOT, '..', '.venv', 'bin', 'python')].find((p) => existsSync(p)) ?? ''
const py = process.env.AIRPULSE_PYTHON || (existsSync(venv) ? venv : existsSync(venvPosix) ? venvPosix : 'python')

test('a production source that is not healthy is named wherever an outlook is shown', () => {
  const src = (name, status, production = true) => ({ name, status, production })
  const reg = (...sources) => ({ registry: { sources } })
  assert.deepEqual(needsAttention(reg(src('a', 'HEALTHY'), src('b', 'HEALTHY', false))), [])
  assert.deepEqual(needsAttention(reg(src('a', 'FAILED'), src('b', 'STALE'), src('c', 'FAILED', false), src('d', 'HEALTHY'), src('e', 'DEGRADED'))).map((x) => x.name), ['a', 'b', 'e'])
  assert.deepEqual(needsAttention(undefined), []); assert.deepEqual(needsAttention({}), [])
  const asExported = new Date(core.registry.generated_at)            // at the moment of the export the page agrees with the engine
  assert.equal(needsAttention(core, asExported).length, core.registry.sources.filter((x) => x.production && x.status !== 'HEALTHY').length)
  for (const f of ['src/pages/Overview.jsx', 'src/pages/Forecast.jsx', 'src/pages/WeeklyFuel.jsx']) assert.match(read(f), /<SourceAlert core=\{core\} \/>/, f)
  const bits = read('src/components/bits.jsx'), shell = read('src/components/Shell.jsx')
  assert.match(bits, /export function SourceAlert/); assert.match(bits, /may be out of date/)
  assert.match(bits, /if \(!bad\.length && !ex\.stale\) return null/); assert.match(shell, /needsAttention\(core\)/); assert.match(shell, /attention > 0 &&/)
})

test('the refresh report covers every production source and does not hide a failed one', () => {
  const code = [
    'import contextlib, io, json, sys',
    `sys.path.insert(0, ${JSON.stringify(join(ROOT, 'scripts'))})`,
    'import refresh',
    'core, weekly, snap = refresh.load("core.json"), refresh.load("weekly.json"), refresh.snapshot()',
    'a, b = io.StringIO(), io.StringIO()',
    'with contextlib.redirect_stdout(a): clean = refresh.report(core, weekly, snap, snap, [])',
    'bad = json.loads(json.dumps(core)); s = next(x for x in bad["registry"]["sources"] if x["production"]); s["status"] = "FAILED"; s["error"] = "HTTP 503"',
    'with contextlib.redirect_stdout(b): warn = refresh.report(bad, weekly, snap, snap, ["engine refresh"])',
    'print(json.dumps({"clean": clean, "warn": warn, "name": s["name"], "table": a.getvalue(), "failed": b.getvalue()}))',
  ].join('\n')
  const out = JSON.parse(execFileSync(py, ['-c', code], { encoding: 'utf8' }).trim().split('\n').at(-1))
  for (const h of ['SOURCE', 'LATEST DATA', 'LAST FETCH', 'EXPECTED UPDATE', 'STALE?', 'MONTHLY FORECAST UPDATED?', 'WEEKLY FUEL UPDATED?', 'EXPORT UPDATED?', '== warnings']) assert.ok(out.table.includes(h), h)
  for (const s of core.registry.sources.filter((x) => x.production)) assert.ok(out.table.includes(s.name.slice(0, 58)), `${s.name} is in the table`)
  assert.match(out.table, /EXPORT UPDATED\?\s+no/, 'nothing changed between two identical snapshots, and the report says so')
  assert.equal(out.clean.length, core.registry.sources.filter((x) => x.production && x.status !== 'HEALTHY').length + (weekly.state?.stale ? 1 : 0) + (core.state.records_intact ? 0 : 1))
  assert.ok(out.warn.some((w) => w.includes(out.name) && w.includes('FAILED') && w.includes('HTTP 503')), 'the failed source is a warning, with its reason')
  assert.ok(out.warn.some((w) => w.startsWith('step failed: engine refresh')))
  assert.match(out.failed, /WARNING/); assert.match(out.failed, new RegExp(`${out.name.slice(0, 20).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}.*FAILED`))
  const script = read('scripts/refresh.py')
  assert.match(script, /return 2 if warn else 0/, 'warnings change the exit code')
  assert.match(script, /failures\.append\("engine run/, 'a source that failed is recorded and the export still runs, so the pages show the failed source')
  assert.match(script, /if code == 1:\s*\n\s*print\("\\nFAILED: the engine's validation gate did not pass\. Nothing is exported/, 'a failed validation gate stops before the export: nothing new is published')
  assert.doesNotMatch(script, /src\.ops\.cli", "run"\], ROOT\) != 0:\s*\n\s*(print|return)/, 'a failed engine step does not end the run before the export')
})

