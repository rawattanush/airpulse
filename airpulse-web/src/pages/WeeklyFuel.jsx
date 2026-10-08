import { useState } from 'react'
import { Link, useOutletContext } from 'react-router-dom'
import { useWeekly } from '../lib/data.js'
import { lateReason, strengthOf, weeklyView } from '../lib/derive.js'
import { DIR, fmtDay, fmtTime, fmtWeekday, num, prob, share, signed } from '../lib/format.js'
import { Dir, Empty, Loading, Next, PageHead, Section, SourceAlert, Tag } from '../components/bits.jsx'
import { C, ProbBars, TimeChart } from '../components/charts.jsx'

const usd = (v, d = 2) => (v == null ? '—' : `$${num(v, d)}`)

/** What the weekly outlook means, in terms of the fuel price and its band. */
function sentence(dir, band) {
  if (dir === 'UP') return `The average jet fuel price of the next weekly release is expected to be more than ${band}% above the average of the week just published.`
  if (dir === 'DOWN') return `The average jet fuel price of the next weekly release is expected to be more than ${band}% below the average of the week just published.`
  return `The average jet fuel price of the next weekly release is expected to stay within ±${band}% of the average of the week just published.`
}

export default function WeeklyFuel() {
  const core = useOutletContext()
  const w = useWeekly()
  const [all, setAll] = useState(false)
  if (!w) return <Loading what="the weekly fuel outlook" />

  if (!w.available) {
    return (
      <div className="page narrow">
        <PageHead kicker="Market · Weekly fuel" title="Weekly fuel-cost outlook" lede="A weekly outlook is offered only when it has passed the test set for it in advance." />
        <Empty title="Not offered">{w.reason}</Empty>
        <nav className="next-row" aria-label="Continue"><Next to="/market/forecast" title="Monthly outlook" note="The air-freight price index, month ahead" /></nav>
      </div>
    )
  }

  const v = weeklyView(w)
  const rec = w.record, st = w.state, cf = w.carry_forward
  const strength = strengthOf(rec.by_strength, v.p)
  const chart = w.windows.slice(-52)
  const desc = [...w.forecasts].reverse().filter((r) => r.s !== 'PENDING')
  const shown = all ? desc : desc.slice(0, 12)

  return (
    <div className="page">
      <PageHead kicker="Market · Weekly fuel" title="Jet fuel: the week ahead"
        lede="Where this week's average jet fuel price is heading against the week just published, given the latest published price.">
        <Tag>Fuel cost</Tag>
      </PageHead>

      <p className="wk-not">
        <b>This is not a freight-price forecast.</b> Weekly air-freight price forecasting is not yet supportable with public data: every weekly rate series is closed by subscription or by its terms.
        This page covers one cost input, jet fuel, where a weekly outlook has been tested and holds. The air-freight outlook is monthly. <Link to="/market/forecast">Monthly outlook</Link>
      </p>

      <SourceAlert core={core} />

      {cf?.is_a_carry_forward && (
        <p className="wk-carry">
          <b>What this outlook is: a carry-forward of the latest published price.</b> It tells you where the weekly average is heading given where the price already stands.
          It does not predict where the price goes next: over {num(cf.weeks, 0)} weeks, nothing forecast the coming week better than assuming the price stays where it last was. <Link to="/methodology#weekly">How it was tested</Link>
        </p>
      )}

      {st?.stale && (
        <p className="wk-stale" role="status">
          <b>Out of date.</b> The newest fuel release held is {fmtDay(st.latest_release)}, {st.days_since_latest_release} days ago. A release is expected every week; the outlook below is for a week that has passed.
        </p>
      )}

      <div className="fc-top">
        <div className="fc-call">
          <p className="eyebrow">AirPulse weekly fuel-cost outlook · US Gulf Coast jet fuel</p>
          <p className={`call-word ${DIR[v.dir].cls}`}><i aria-hidden="true">{DIR[v.dir].glyph}</i>{DIR[v.dir].word}</p>
          <p className="call-sub">{sentence(v.dir, w.band_pct)}</p>
          <ProbBars f={v.f} big />
          {strength && (
            <p className="fine fc-same">
              Signal strength: <b>{strength.label}</b>. Earlier outlooks at this probability level were right {strength.correct} times out of {strength.n} ({share(strength.correct, strength.n)}).
            </p>
          )}
        </div>
        <div className="fc-facts">
          <dl className="kv">
            <div><dt>Outlook probability</dt><dd>{prob(v.p)}</dd></div>
            <div><dt>Issued</dt><dd>{fmtWeekday(v.issued)}, {fmtDay(v.issued)} <span>release date</span></dd></div>
            <div><dt>Week just published</dt><dd>{fmtDay(v.ref[0])} – {fmtDay(v.ref[1])} <span>average {usd(v.refMean)}</span></dd></div>
            <div><dt>Forecast window</dt><dd>The next weekly release <span>prices from {fmtDay(v.issued)}</span></dd></div>
            <div><dt>Outcome published</dt><dd>{v.outcome ? fmtDay(v.outcome) : `about ${fmtDay(v.expected)}`}</dd></div>
            <div><dt>Status</dt><dd>{v.pending ? 'Pending' : <>Outcome: <Dir d={v.actual} /></>}</dd></div>
          </dl>
          {v.generated && (
            <p className="fine fc-late">
              Generated {fmtTime(v.generated)}{v.timing === 'LATE' ? `, ${v.days} days after the release. ${lateReason(v.trigger)} It uses only prices published by the release date.` : '.'}{' '}
              <Link to="/data">Data state</Link>
            </p>
          )}
        </div>
      </div>

      <Section title="Why" id="why" aside="The outlook rests on published prices only. It does not anticipate news.">
        <div className="wk-why">
          <div>
            <p>
              The latest published price, <b>{usd(v.lastPrice)}</b> a gallon, stands <b>{signed(v.gap, 1)}%</b> {v.gap >= 0 ? 'above' : 'below'} the average of the week just published ({usd(v.refMean)}).
            </p>
            <p>{w.method.text}</p>
            <p className="fine">A move of more than ±{w.band_pct}% between two weekly averages counts as rising or falling. Anything inside that band is stable.</p>
          </div>
          <figure className="figure">
            <figcaption><b>Weekly average jet fuel price</b><span>US Gulf Coast, USD per gallon · one point per weekly release, last 52</span></figcaption>
            <TimeChart rows={chart} xKey="i" xFmt={fmtDay} xTick={(x) => fmtDay(x).slice(0, -5)} tickEvery={(r, i) => i % 9 === 0} height={250} label="Weekly average jet fuel price, last 52 releases"
              series={[{ key: 'm', name: 'Weekly average', color: C.navy, width: 2, type: 'line' }]} yFmt={(x) => `$${num(x, 1)}`} tipFmt={(x) => usd(x)}
              dots={[{ i: chart.length - 1, key: 'm', label: `${usd(chart.at(-1).m)} · week to ${fmtDay(chart.at(-1).b)}` }]} />
          </figure>
        </div>
      </Section>

      <Section title="Historical record" id="record" aside={`Every weekly outlook from ${fmtDay(w.first_scored)} to ${fmtDay(w.last_scored)}, each made with the prices published by its release date and checked against the next release.`}>
        <div className="fc-basis">
          <div className="fc-record">
            <p className="fc-record-big"><b>{rec.correct}</b> of {rec.scored} weeks correct <span>{share(rec.correct, rec.scored)}</span></p>
            <p className="fine">Three directions are possible, so a guess would be right about one week in three. Two simple rules on the same weeks:</p>
            <ul className="wk-rules">
              {rec.simple_rules.map((r) => <li key={r.rule}><span>{r.rule}</span><b>{r.correct} of {r.scored}</b><em>{share(r.correct, r.scored)}</em></li>)}
            </ul>
            <p className="fine">{rec.not_scored_irregular} weeks with an irregular release (a holiday week, a missed release, a late-published day) are kept in the record and not scored.</p>
          </div>
          <div>
            <div className="tbl-wrap"><table className="tbl fc-periods">
              <thead><tr><th>Period</th><th className="r">Weeks</th><th className="r">Correct</th><th className="r">Share</th></tr></thead>
              <tbody>{rec.by_period.map((r) => <tr key={r.label}><td>{r.label}</td><td className="r">{r.scored}</td><td className="r">{r.correct}</td><td className="r">{share(r.correct, r.scored)}</td></tr>)}</tbody>
            </table></div>
            <div className="tbl-wrap"><table className="tbl wrap fc-periods wk-strength">
              <thead><tr><th>Signal strength</th><th>Outlook probability</th><th className="r">Weeks</th><th className="r">Correct</th><th className="r">Share</th></tr></thead>
              <tbody>{rec.by_strength.map((r) => <tr key={r.label}><td>{r.label}</td><td>{r.from === 0 ? `below ${prob(r.to)}` : r.to >= 1 ? `${prob(r.from)} and above` : `${prob(r.from)} to ${prob(r.to)}`}</td><td className="r">{r.n}</td><td className="r">{r.correct}</td><td className="r">{share(r.correct, r.n)}</td></tr>)}</tbody>
            </table></div>
          </div>
        </div>
        <div className="fc-bycall">
          {['UP', 'FLAT', 'DOWN'].map((k) => {
            const c = rec.by_call.find((x) => x.dir === k)
            return <p key={k}><Dir d={k} /> <span>called {c.n} times</span> <b>{c.n ? share(c.correct, c.n) : '—'}</b> <span>correct</span></p>
          })}
        </div>
      </Section>

      <Section title="Outlook against outcome" id="outcomes" aside="The most recent weeks. The change is the weekly average against the week before it.">
        <div className="tbl-wrap">
          <table className="tbl">
            <thead><tr><th>Issued</th><th>Outlook</th><th className="r">Probability</th><th>Week forecast</th><th className="r">Change</th><th>Outcome</th><th>Result</th></tr></thead>
            <tbody>
              {shown.map((r) => (
                <tr key={r.i}>
                  <td>{fmtDay(r.i)}</td><td><Dir d={r.p} /></td><td className="r">{prob(Math.max(r.d, r.f, r.u))}</td>
                  <td>{r.tw ? `${fmtDay(r.tw[0]).slice(0, -5)} – ${fmtDay(r.tw[1])}` : '—'}</td>
                  <td className="r">{r.pc == null ? '—' : `${signed(r.pc, 1)}%`}</td><td><Dir d={r.a} /></td>
                  <td>{r.s === 'IRREGULAR' ? <span className="dim">Not scored</span> : r.p === r.a ? 'Correct' : 'Missed'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!all && desc.length > shown.length && <button type="button" className="more" onClick={() => setAll(true)}>Show the last {desc.length} weeks</button>}
      </Section>


      <Section title="What this outlook is, and is not" id="limits" aside="Read before using it.">
        <ul className="wk-list">
          <li><b>A fuel cost, not a freight rate.</b> Jet fuel is one cost of flying freight. A rise in the fuel price is not a rise in freight rates.</li>
          <li><b>A carry-forward, not a prediction.</b> The outlook compares the latest price with the weekly average. It cannot see a supply shock before the price moves, and in testing nothing predicted the price beyond its latest level.</li>
          <li><b>One week, one direction.</b> It does not say how far the price will move, and it says nothing about the price a month from now.</li>
          <li><b>First-published prices.</b> {w.revisions.changed} of {num(w.revisions.of, 0)} daily prices were corrected after they first appeared. Outlook and outcome use the price as first published, so the record is what a reader would have seen.</li>
          <li><b>One market.</b> US Gulf Coast spot jet fuel, as published by the US Energy Information Administration. Fuel at other airports can move differently.</li>
        </ul>
      </Section>

      <nav className="next-row" aria-label="Continue">
        <Next to="/market/forecast" title="Monthly outlook" note="The air-freight price index, month ahead" />
        <Next to="/market/fuel" title="Fuel prices" note="Jet fuel and crude over time" />
        <Next to="/methodology#weekly" title="How it is tested" note="The weekly target and its rule" />
      </nav>
    </div>
  )
}
