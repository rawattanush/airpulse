import test from 'node:test'
import assert from 'node:assert/strict'
import { byYear, longestRun, marketRead, outlookView, recordByCall, recordByYear, turningPoints, withChanges } from '../src/lib/derive.js'
import { DIR, fmtPeriod, money, pct, prob } from '../src/lib/format.js'

const hist = (pairs) => pairs.map(([m, v, extra]) => ({ m, v, rel: null, pf: null, lf: null, pr: null, lr: null, ...extra }))

test('changes are taken against the calendar month they name; a missing month leaves a gap', () => {
  const rows = withChanges(hist([['2025-08', 100], ['2025-09', 110], ['2025-11', 121]]))   // October was not published
  assert.equal(rows[1].mom.toFixed(6), '10.000000')
  assert.equal(rows[2].mom, null)                       // not a two-month change passed off as one
  assert.equal(rows[2].yoy, null)
})

test('the published change and direction win over arithmetic; final over first release', () => {
  const rows = withChanges(hist([['2026-01', 100], ['2026-02', 103, { pr: 3.1, lr: 'UP' }], ['2026-03', 103.2, { pr: 0.2, lr: 'FLAT', pf: 0.6, lf: 'UP' }]]))
  assert.deepEqual([rows[1].mom, rows[1].dir, rows[1].final], [3.1, 'UP', false])
  assert.deepEqual([rows[2].mom, rows[2].dir, rows[2].final], [0.6, 'UP', true])
})

test('quarterly history before December 2005 is left out', () => {
  assert.equal(withChanges(hist([['2005-09', 90], ['2005-12', 100], ['2006-01', 101]])).length, 2)
})

test('market read: record high, distance from it, current run', () => {
  const rows = withChanges(hist([['2026-01', 100, { lr: 'UP' }], ['2026-02', 120, { lr: 'UP' }], ['2026-03', 110, { lr: 'DOWN' }], ['2026-04', 112, { lr: 'UP' }], ['2026-05', 114, { lr: 'UP' }]]))
  const r = marketRead(rows)
  assert.equal(r.high.m, '2026-02'); assert.equal(r.low.m, '2026-01'); assert.equal(r.run, 2)
  assert.equal(r.fromHigh.toFixed(1), '-5.0')
  assert.deepEqual(longestRun(rows, 'UP'), { from: '2026-01', to: '2026-02', n: 2 })
})

test('the outlook view reports a tie as a close call and never invents a probability', () => {
  const tie = outlookView({ d: 5 / 19, f: 7 / 19, u: 7 / 19, p: 'FLAT', s: 'PENDING' })
  assert.equal(tie.dir, 'FLAT'); assert.equal(tie.closeCall, true); assert.deepEqual(tie.tied, ['UP']); assert.equal(tie.p, 7 / 19); assert.equal(tie.pending, true)
  const clear = outlookView({ d: 0.2, f: 0.1, u: 0.7, p: 'UP', s: 'SCORED' })
  assert.equal(clear.closeCall, false); assert.equal(clear.runnerUp, 'DOWN'); assert.equal(clear.p, 0.7)
  assert.equal(outlookView({ d: null, f: null, u: null, p: null }), null)
  assert.equal(outlookView(undefined), null)
})

test('the record is counted from scored outlooks only', () => {
  const fc = [{ t: '2025-01', p: 'UP', c: 1 }, { t: '2025-02', p: 'UP', c: 0 }, { t: '2025-03', p: 'FLAT', c: 0 }, { t: '2026-01', p: 'DOWN', c: 1 }, { t: '2026-02', p: 'UP', c: null }]
  assert.deepEqual(recordByCall(fc), { UP: { n: 2, correct: 1 }, FLAT: { n: 1, correct: 0 }, DOWN: { n: 1, correct: 1 } })
  assert.deepEqual(recordByYear(fc), [{ year: '2025', n: 3, correct: 1, pending: 0 }, { year: '2026', n: 1, correct: 1, pending: 1 }])
})

test('turning points are local extremes; years are summarised from their own months', () => {
  const v = [100, 104, 110, 106, 101, 97, 99, 103, 108, 112, 109, 105]
  const rows = withChanges(hist(v.map((x, i) => [`2024-${String(i + 1).padStart(2, '0')}`, x])))
  const tp = turningPoints(rows, 3)
  assert.deepEqual(tp.map((p) => [p.m, p.kind]), [['2024-03', 'high'], ['2024-06', 'low'], ['2024-10', 'high']])
  const y = byYear(rows)
  assert.equal(y.length, 1); assert.equal(y[0].end, 105); assert.equal(y[0].hi, 112); assert.equal(y[0].lo, 97); assert.equal(y[0].change, null)
})

test('customer wording and formats', () => {
  assert.deepEqual([DIR.UP.word, DIR.FLAT.word, DIR.DOWN.word], ['Rising', 'Stable', 'Falling'])
  assert.equal(prob(7 / 19), '37%'); assert.equal(pct(2.74), '+2.7%'); assert.equal(pct(-4.81), '−4.8%'); assert.equal(pct(null), '—')
  assert.equal(fmtPeriod('2026-08'), 'Aug 2026'); assert.equal(fmtPeriod('2026-09-08'), '8 Sep 2026')
  assert.match(money(682.5, 'INR'), /682\.50/); assert.match(money(341250, 'USD'), /341,250\.00/); assert.equal(money(null, 'USD'), '—')
})
