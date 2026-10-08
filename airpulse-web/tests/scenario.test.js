import test from 'node:test'
import assert from 'node:assert/strict'
import { parseAmount, scenario } from '../src/lib/scenario.js'

test('the scenario is baseline × (1 + movement), and nothing else', () => {
  const r = scenario({ rate: 650, weight: 500, movementPct: 5 })
  assert.equal(r.ok, true)
  assert.equal(r.scenarioRate, 682.5)
  assert.equal(r.rateDifference, 32.5)
  assert.equal(r.baselineCost, 325000)
  assert.equal(r.scenarioCost, 341250)
  assert.equal(r.difference, 16250)
})

test('a falling scenario and a fractional rate', () => {
  const r = scenario({ rate: 4.35, weight: 1200.5, movementPct: -3.5 })
  assert.equal(r.scenarioRate, 4.2)                     // 4.35 × 0.965 = 4.19775, to the cent
  assert.equal(r.baselineCost, 5222.18)
  assert.equal(r.scenarioCost, 5042.1)
  assert.ok(r.difference < 0)
})

test('without a weight there is a scenario rate and no shipment cost', () => {
  const r = scenario({ rate: 100, weight: null, movementPct: 10 })
  assert.equal(r.scenarioRate, 110)
  assert.equal(r.scenarioCost, null)
  assert.equal(r.baselineCost, null)
})

test('no number is produced from missing or impossible input', () => {
  assert.equal(scenario({ rate: null, weight: 500, movementPct: 5 }).ok, false)
  assert.equal(scenario({ rate: 650, weight: 500, movementPct: null }).ok, false)   // the movement is the user's: there is no default
  assert.equal(scenario({ rate: 0, weight: 500, movementPct: 5 }).ok, false)
  assert.equal(scenario({ rate: -5, weight: 500, movementPct: 5 }).ok, false)
  assert.equal(scenario({ rate: 650, weight: 0, movementPct: 5 }).ok, false)
  assert.equal(scenario({ rate: 650, weight: 500, movementPct: -100 }).ok, false)
  assert.equal(scenario({ rate: 650, weight: 500, movementPct: 900 }).ok, false)
  assert.equal(scenario({ rate: 650, weight: 500, movementPct: 0 }).scenarioRate, 650)
})

test('typed amounts are read strictly', () => {
  assert.equal(parseAmount('650'), 650)
  assert.equal(parseAmount(' 1,250.75 '), 1250.75)
  assert.equal(parseAmount('-3.5'), -3.5)
  assert.equal(parseAmount('.5'), 0.5)
  for (const bad of ['', 'abc', '12kg', '1e3', '5%', '--2', null, undefined, NaN, Infinity]) assert.equal(parseAmount(bad), null, String(bad))
})
