import { useState } from 'react'
import { Link, useOutletContext } from 'react-router-dom'
import { useOutlook, useReplay } from '../lib/data.js'
import { lateReason, outlookView, recordByCall } from '../lib/derive.js'
import { CONTEXT, DIR, fmtDay, fmtMonth, fmtMonthLong, fmtPeriod, num, prob, share, signed } from '../lib/format.js'
import { Dir, Loading, Next, PageHead, Section, SourceAlert } from '../components/bits.jsx'
import { C, DIRC, Legend, OutcomeStrip, ProbBars, ProbTimeline } from '../components/charts.jsx'
import { Basis, outlookSentence } from './Overview.jsx'

export default function Forecast() {
  const core = useOutletContext()
  const outlook = useOutlook()
  const replay = useReplay()
  const [all, setAll] = useState(false)
  if (!outlook) return <Loading what="the forecast" />
  const fcs = outlook.forecasts
  const f = fcs.at(-1), v = outlookView(f), o = outlook.official
  const month = fmtMonthLong(f.t)
  const rec = outlook.record.FINAL ?? []
  const overall = rec.find((r) => r.period === 'ALL')
  const byCall = recordByCall(fcs)
  const bundle = replay?.months.at(-1)
  const desc = [...fcs].reverse()
  const shown = all ? desc : desc.slice(0, 14)
  const pending = fcs.filter((x) => x.s === 'PENDING').length
  const op = outlook.operational
  const due = outlook.current && !outlook.current.is_current ? outlook.current : null   // a newer month is due and no forecast for it is on record
  const rel = outlook.reliability                                    // how the probabilities shown have held, per direction
  const flat = rel?.find((x) => x.dir === 'FLAT')
  const stableGap = flat ? flat.given - flat.happened : 0

  return (
    <div className="page">
      <PageHead kicker="Market · Monthly outlook" title="Where is the market heading?"
        lede={`One outlook for each month: rising, stable or falling, with its probability. A move of more than ±${outlook.flat_band_pct}% counts as rising or falling.`} />

      <SourceAlert core={core} />
      {due && (
        <p className="src-alert" role="status"><b>Outlook not current.</b> An outlook for {fmtMonth(due.month_due)} is due and none is on record. The outlook below is the last one issued, for {fmtMonth(due.month_shown)}; it is shown as history, not as the current outlook.</p>
      )}

      <div className="fc-top">
        <div className="fc-call">
          <p className="eyebrow">AirPulse outlook · {outlook.lane_name.replace(' air freight', '')}</p>
          <p className={`call-word ${DIR[v.dir].cls}`}><i aria-hidden="true">{DIR[v.dir].glyph}</i>{DIR[v.dir].word}</p>
          <p className="call-sub">{outlookSentence(v.dir, outlook.flat_band_pct, month)}</p>
          <ProbBars f={f} big />
          {v.closeCall && <p className="call-close">{v.tied.map((k) => DIR[k].word).join(' and ')} and {DIR[v.dir].word} carry the same probability. The outlook names {DIR[v.dir].word} by a fixed rule; read it as an even call between them.</p>}
          {byCall[v.dir].n > 0 && <p className="fine fc-same">Earlier “{DIR[v.dir].word}” outlooks were correct {byCall[v.dir].correct} times out of {byCall[v.dir].n}. <a href="#history">The record by direction</a></p>}
        </div>
        <div className="fc-facts">
          <dl className="kv">
          <div><dt>Outlook probability</dt><dd>{prob(v.p)}</dd></div>
          <div><dt>Forecast period</dt><dd>{month}</dd></div>
          <div><dt>Issuance date</dt><dd>{fmtDay(f.i)}</dd></div>
          <div><dt>Outcome published</dt><dd>{fmtDay(f.o)}</dd></div>
          <div><dt>Status</dt><dd>{f.s === 'PENDING' ? 'Pending' : <>Outcome: <Dir d={f.a} /></>}</dd></div>
          <div><dt>Market</dt><dd>Asia → US <span>public market proxy</span></dd></div>
          </dl>
          {op && op.target_period === f.t && (
            <p className="fine fc-late">
              Generated {fmtDay(op.generated_at)} from data as published by the issuance date{op.timing === 'LATE' ? `, ${op.days_after_issuance} days after it. ${lateReason(op.trigger)}` : '.'} <Link to="/data">Data state</Link>
            </p>
          )}
        </div>
      </div>

      <Section title="How this outlook is formed" id="basis" aside="One approach, chosen because it has the best validated record on this market. Customers are not asked to pick between models.">
        <div className="fc-basis">
          <div className="fc-basis-why"><Basis f={f} /></div>
          <div className="fc-record">
            <p className="eyebrow">Its record</p>
            {overall && <p className="fc-record-big"><b>{overall.correct}</b> of {overall.months} months correct <span>{share(overall.correct, overall.months)}</span></p>}
            <p className="fine">Checked against the final published figure, {o.evaluation_period.replace(' to ', ' to ')}. Picking one of three directions at random would be right about {Math.round(o.chance_rate * 100)}% of the time.</p>
            <table className="tbl fc-periods">
              <thead><tr><th>Period</th><th className="r">Months</th><th className="r">Correct</th><th className="r">Share</th></tr></thead>
              <tbody>{rec.filter((r) => r.period !== 'ALL').map((r) => <tr key={r.period}><td>{r.label}</td><td className="r">{r.months}</td><td className="r">{r.correct}</td><td className="r">{share(r.correct, r.months)}</td></tr>)}</tbody>
            </table>
          </div>
        </div>
      </Section>

      {rel && (
        <Section title="How far to trust the probabilities" id="calibration" aside="For each direction: the probability the outlook gave it on average over its scored months, and how often it then happened.">
          <div className="fc-cal">
            <div className="tbl-wrap"><table className="tbl wrap">
              <thead><tr><th>Direction</th><th className="r">Probability given, on average</th><th className="r">How often it happened</th><th className="r">Difference</th></tr></thead>
              <tbody>{['UP', 'FLAT', 'DOWN'].map((k) => { const c = rel.find((x) => x.dir === k); return <tr key={k}><td><Dir d={k} /></td><td className="r">{prob(c.given)}</td><td className="r">{prob(c.happened)}</td><td className="r">{signed((c.happened - c.given) * 100, 0)} pts</td></tr> })}</tbody>
            </table></div>
            <div>
              {stableGap > 0.05
                ? <p><b>Read the probability for “Stable” as too high.</b> The outlook gave “Stable” {prob(flat.given)} on average and it happened {prob(flat.happened)} of the time. The seasonal record still carries calmer years.</p>
                : <p>The probabilities given have been close to how often each direction happened.</p>}
            </div>
          </div>
        </Section>
      )}

      <Section title="Forecast history" id="history" aside={`The probabilities issued for every month since ${fmtMonth(fcs[0].t)}, with the result beneath each one.`}>
        <ProbTimeline items={fcs} height={240} />
        <Legend items={[{ name: 'Rising', color: DIRC.UP, shape: 'box' }, { name: 'Stable', color: DIRC.FLAT, shape: 'box' }, { name: 'Falling', color: DIRC.DOWN, shape: 'box' }, { name: 'Outlook correct', color: C.navy, shape: 'box' }, { name: 'Outlook missed', color: C.navy, shape: 'ring' }]} />
        <div className="fc-bycall" id="record">
          {['UP', 'FLAT', 'DOWN'].map((k) => (
            <p key={k}><Dir d={k} /> <span>called {byCall[k].n} times</span> <b>{byCall[k].n ? share(byCall[k].correct, byCall[k].n) : '—'}</b> <span>correct</span></p>
          ))}
        </div>
      </Section>

      <Section title="Forecast against outcome" id="outcomes" aside={`${fcs.length} outlooks; ${pending} still await a final figure. BLS revises each value in the ${outlook.revision_releases} releases after the first.`}>
        <OutcomeStrip items={fcs} to={(m) => `/replay?month=${m}`} />
        <div className="tbl-wrap fc-table">
          <table className="tbl">
            <thead><tr><th>Month</th><th>Issuance date</th><th>Outlook</th><th className="r">Probability</th><th>First release</th><th>Final figure</th><th>Result</th></tr></thead>
            <tbody>
              {shown.map((r) => (
                <tr key={r.t}>
                  <td><Link to={`/replay?month=${r.t}`}>{fmtMonth(r.t)}</Link></td>
                  <td>{fmtDay(r.i)}</td><td><Dir d={r.p} /></td><td className="r">{prob(outlookView(r)?.p)}</td>
                  <td><Dir d={r.ar} /></td><td><Dir d={r.a} /></td>
                  <td>{r.c === 1 ? 'Correct' : r.c === 0 ? 'Missed' : <span className="dim">Pending</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!all && <button type="button" className="more" onClick={() => setAll(true)}>Show all {fcs.length} months</button>}
      </Section>

      {bundle && (
        <Section title="Information available at issuance" id="known" aside={`What was public on ${fmtDay(bundle.issuance_date)}. Nothing published later is used.`}>
          <div className="fc-known">
            <div className="tbl-wrap">
              <table className="tbl">
                <thead><tr><th>Published figure</th><th>Period</th><th>Published</th><th className="r">Value</th></tr></thead>
                <tbody>
                  {bundle.available_then.map((r, i) => (
                    <tr key={i}><td>{r.input}</td><td>{fmtPeriod(r.period)}</td><td>{r.published === 'not yet published' ? <span className="dim">not yet published</span> : fmtDay(r.published)}</td><td className="r">{r.value == null ? '—' : num(r.value, r.value < 10 ? 3 : 1)}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div>
              <h3>Market signals at that date</h3>
              <dl className="kv">
                {bundle.signals.map((x) => <div key={x.id}><dt>{CONTEXT[x.id] ?? x.meaning}</dt><dd>{x.value == null ? '—' : `${signed(x.value, 1)}%`}</dd></div>)}
              </dl>
              <p className="fine">Changes as they stood on the issuance date. Shown as context; the outlook itself rests on the seasonal record.</p>
              <Link className="text-link" to={`/replay?month=${bundle.target_month}`}>Reconstruct this outlook in Replay</Link>
            </div>
          </div>
        </Section>
      )}

      <nav className="next-row" aria-label="Continue">
        <Next to="/market/fuel" title="Fuel prices" note="Jet fuel and crude oil, as published" />
        <Next to="/replay" title="Replay" note="What AirPulse knew at any issuance" />
        <Next to="/estimate" title="Shipment scenario" note="Test a rate movement of your own" />
      </nav>
    </div>
  )
}
