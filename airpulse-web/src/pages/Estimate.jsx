import { useState } from 'react'
import { Link, useOutletContext } from 'react-router-dom'
import { CURRENCIES, money, num } from '../lib/format.js'
import { parseAmount, scenario } from '../lib/scenario.js'
import { Banner, Field, Next, Section, Tag } from '../components/bits.jsx'

const PRESETS = [-10, -5, 2, 5, 10]
const PIPELINE = [
  ['Historical lane rates', 'Rates per kilogram for the lane, over several years, with their dates'],
  ['Route normalisation', 'Airport pairs mapped to comparable lanes'],
  ['Carrier and service normalisation', 'Spot against contract, express against deferred, surcharges'],
  ['Baseline rate', 'What the lane costs today'],
  ['Market relationship', 'How the lane has moved with the market index, tested on history'],
  ['Fuel, capacity, disruption', 'Kept only if they improve the estimate in testing'],
  ['Validated range', 'A prediction interval checked against outcomes'],
  ['Estimated rate per kilogram', 'With its range'],
  ['Shipment cost', 'Rate × chargeable weight'],
]

export default function Estimate() {
  useOutletContext()
  const [origin, setOrigin] = useState('')
  const [dest, setDest] = useState('')
  const [weight, setWeight] = useState('')
  const [cur, setCur] = useState('USD')
  const [rate, setRate] = useState('')
  const [move, setMove] = useState('')

  const r = parseAmount(rate), w = weight.trim() === '' ? null : parseAmount(weight), m = move.trim() === '' ? null : parseAmount(move.replace('%', ''))
  const badWeight = weight.trim() !== '' && w == null, badRate = rate.trim() !== '' && r == null, badMove = move.trim() !== '' && m == null
  const res = !badWeight && !badRate && !badMove ? scenario({ rate: r, weight: w, movementPct: m }) : { ok: false, problems: ['Enter numbers only, for example 650 or 12.5.'] }
  const started = rate.trim() !== '' || move.trim() !== ''
  const lane = origin.trim() && dest.trim() ? `${origin.trim()} → ${dest.trim()}` : 'this route'

  return (
    <>
      <Banner photo="loading" alt="A cargo pallet being loaded into a freighter at dusk" kicker="Operations · Estimate" title="Estimate your shipment"
        lede="What AirPulse can tell you about the cost of a shipment today, what it cannot, and a calculator for scenarios of your own." focus="50% 60%" />
      <div className="page flush est">
        <div className="est-grid">
          <form className="est-form" onSubmit={(e) => e.preventDefault()} aria-label="Your shipment">
            <h2>Your shipment</h2>
            <div className="est-two">
              <Field label="Origin" id="e-origin"><input id="e-origin" value={origin} onChange={(e) => setOrigin(e.target.value)} autoComplete="off" placeholder="City or airport" /></Field>
              <Field label="Destination" id="e-dest"><input id="e-dest" value={dest} onChange={(e) => setDest(e.target.value)} autoComplete="off" placeholder="City or airport" /></Field>
            </div>
            <div className="est-two">
              <Field label="Chargeable weight (kg)" id="e-weight"><input id="e-weight" inputMode="decimal" value={weight} onChange={(e) => setWeight(e.target.value)} aria-invalid={badWeight} autoComplete="off" /></Field>
              <Field label="Currency" id="e-cur" hint="The currency your rate is quoted in. Nothing is converted.">
                <select id="e-cur" value={cur} onChange={(e) => setCur(e.target.value)} aria-describedby="e-cur-hint">{CURRENCIES.map((c) => <option key={c.code} value={c.code}>{c.code} · {c.label}</option>)}</select>
              </Field>
            </div>
            <Field label="Current known rate (per kg)" id="e-rate" hint="A rate you already have: a quote, a contract rate, your last invoice."><input id="e-rate" inputMode="decimal" value={rate} onChange={(e) => setRate(e.target.value)} aria-invalid={badRate} aria-describedby="e-rate-hint" autoComplete="off" /></Field>
          </form>

          <section className="est-status" aria-labelledby="est-status-h">
            <p className="eyebrow">Route-level estimation</p>
            <h2 id="est-status-h">Not yet available{origin.trim() && dest.trim() ? <> for <span>{lane}</span></> : ' for this route'}.</h2>
            <p>AirPulse currently provides market-direction intelligence using a public air-freight price index. Validated route-level freight estimates require historical lane-rate data, which AirPulse does not have.</p>
            <p>So there is no AirPulse rate per kilogram here, no range and no shipment cost. Showing one would be inventing it.</p>
            <p className="fine">What exists today: the monthly <Link to="/market/forecast">market outlook</Link> for the Asia → US proxy. It is a direction for a market index, not a statement about your lane.</p>
          </section>
        </div>

        <section className="calc" aria-labelledby="calc-h">
          <div className="calc-head">
            <p className="calc-flag"><Tag tone="solid">Scenario only</Tag><Tag>Not an AirPulse forecast</Tag></p>
            <h2 id="calc-h">Scenario calculator</h2>
            <p>Test a rate movement of your own choosing against the rate you entered. The movement is your assumption; AirPulse does not supply it and does not predict it.</p>
          </div>
          <div className="calc-body">
            <div className="calc-in">
              <p className="eyebrow" id="move-l">Your scenario: the rate moves by</p>
              <div className="calc-presets" role="group" aria-labelledby="move-l">
                {PRESETS.map((p) => <button key={p} type="button" aria-pressed={m === p} onClick={() => setMove(String(p))}>{p > 0 ? '+' : '−'}{Math.abs(p)}%</button>)}
              </div>
              <Field label="Or enter a movement (%)" id="e-move"><input id="e-move" inputMode="decimal" value={move} onChange={(e) => setMove(e.target.value)} aria-invalid={badMove} autoComplete="off" placeholder="e.g. 5 or -3.5" /></Field>
              <p className="calc-formula num">scenario rate = current rate × (1 + movement)</p>
            </div>
            <div className="calc-out" role="status" aria-live="polite">
              {res.ok ? (
                <>
                  <dl>
                    <div className="main"><dt>Scenario rate</dt><dd>{money(res.scenarioRate, cur)}<span>/kg</span></dd><dd className="sub">{money(r, cur)}/kg {m >= 0 ? '+' : '−'} {num(Math.abs(m), Number.isInteger(m) ? 0 : 2)}% · {res.rateDifference >= 0 ? '+' : '−'}{money(Math.abs(res.rateDifference), cur)}/kg</dd></div>
                    {res.scenarioCost != null ? (
                      <>
                        <div><dt>Shipment at the current rate</dt><dd>{money(res.baselineCost, cur)}</dd><dd className="sub">{num(w, Number.isInteger(w) ? 0 : 2)} kg × {money(r, cur)}</dd></div>
                        <div className="main"><dt>Shipment in this scenario</dt><dd>{money(res.scenarioCost, cur)}</dd><dd className="sub">{res.difference >= 0 ? '+' : '−'}{money(Math.abs(res.difference), cur)} against the current rate</dd></div>
                      </>
                    ) : <div><dt>Shipment cost</dt><dd className="dim">Enter a chargeable weight</dd></div>}
                  </dl>
                  <p className="calc-warn"><b>A scenario, not a forecast.</b> This is your rate multiplied by a movement you chose. It says nothing about what the rate{origin.trim() && dest.trim() ? ` for ${lane}` : ''} will do.</p>
                </>
              ) : (
                <div className="calc-wait">
                  <p>{started ? res.problems[0] : 'Enter your current rate and choose a movement to see the scenario.'}</p>
                </div>
              )}
            </div>
          </div>
        </section>

        <Section title="What a real estimate will need" id="roadmap" aside="The path from market direction to a rate for your lane. None of this is built; each step has to be validated before a number is shown.">
          <ol className="pipe">
            {PIPELINE.map(([t, d], i) => <li key={t}><span>{String(i + 1).padStart(2, '0')}</span><div><h3>{t}</h3><p>{d}</p></div></li>)}
          </ol>
          <div className="est-fx">
            <h3>Currency is a separate question</h3>
            <p>A rate estimated in one currency and shown in another carries two uncertainties: the freight rate and the exchange rate. AirPulse will keep them apart: first the freight estimate, then the conversion, each with its own range. Neither exists today, which is why the calculator above converts nothing.</p>
            <p className="pipe-fx num"><span>Estimated freight rate</span><i>→</i><span>Exchange-rate conversion</span><i>→</i><span>Local-currency estimate</span></p>
          </div>
        </Section>

        <nav className="next-row" aria-label="Continue">
          <Next to="/market/forecast" title="Market outlook" note="What AirPulse can say today" />
          <Next to="/routes" title="Routes" note="What is covered, lane by lane" />
          <Next to="/methodology#limitations" title="Limitations" note="What every number here does not mean" />
        </nav>
      </div>
    </>
  )
}
