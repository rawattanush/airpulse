import { useMemo } from 'react'
import { Link, useOutletContext, useSearchParams } from 'react-router-dom'
import { useOutlook, useReplay } from '../lib/data.js'
import { outlookView } from '../lib/derive.js'
import { CONTEXT, DIR, fmtDay, fmtDayLong, fmtMonth, fmtMonthLong, fmtPeriod, num, pct, signed } from '../lib/format.js'
import { Dir, Loading, Next, Section } from '../components/bits.jsx'
import { OutcomeStrip, ProbBars } from '../components/charts.jsx'
import { Basis } from './Overview.jsx'

export default function Replay() {
  const core = useOutletContext()
  const replay = useReplay()
  const outlook = useOutlook()
  const [params, setParams] = useSearchParams()
  const months = replay?.months ?? []
  const wanted = params.get('month')
  const idx = useMemo(() => { const i = months.findIndex((m) => m.target_month === wanted); return i >= 0 ? i : months.length - 1 }, [months, wanted])
  if (!replay || !outlook) return <Loading what="the replay" />
  const b = months[idx]
  const go = (i) => setParams({ month: months[Math.max(0, Math.min(months.length - 1, i))].target_month }, { replace: true })
  const f = { ...b.outlook, t: b.target_month }
  const v = outlookView(f)
  const of = b.outcome_first_release, fin = b.outcome_final
  const scored = fin.label ?? null
  const result = scored ? (scored === f.p ? 'correct' : 'missed') : 'pending'
  const revised = b.available_then.filter((r) => r.revised)
  const years = [...new Set(months.map((m) => m.target_month.slice(0, 4)))]

  return (
    <>
      <header className="rp-head">
        <div className="rp-head-in">
          <p className="eyebrow">Operations · Replay</p>
          <h1>What did AirPulse know at that time?</h1>
          <div className="rp-pick">
            <button type="button" onClick={() => go(idx - 1)} disabled={idx === 0} aria-label="Earlier month">←</button>
            <label>
              <span className="sr">Month</span>
              <select value={b.target_month} onChange={(e) => setParams({ month: e.target.value }, { replace: true })}>
                {years.map((y) => <optgroup key={y} label={y}>{months.filter((m) => m.target_month.startsWith(y)).map((m) => <option key={m.target_month} value={m.target_month}>{fmtMonthLong(m.target_month)}</option>)}</optgroup>)}
              </select>
            </label>
            <button type="button" onClick={() => go(idx + 1)} disabled={idx === months.length - 1} aria-label="Later month">→</button>
          </div>
          <div className="rp-stamp">
            <div><span>Issuance date</span><b>{fmtDayLong(b.issuance_date)}</b></div>
            <div><span>Outlook for</span><b>{fmtMonthLong(b.target_month)}</b></div>
            <div><span>Outcome first published</span><b>{fmtDayLong(b.target_first_release)}</b></div>
          </div>
        </div>
      </header>

      <div className="page flush replay">
        <div className="rp-cols">
          <section className="rp-then" aria-labelledby="then-h">
            <p className="rp-label">Known on {fmtDay(b.issuance_date)}</p>
            <h2 id="then-h">Information available then</h2>
            <div className="tbl-wrap">
              <table className="tbl">
                <thead><tr><th>Published figure</th><th>Period</th><th>Published</th><th className="r">Value then</th></tr></thead>
                <tbody>
                  {b.available_then.map((r, i) => (
                    <tr key={i}><td>{r.input}</td><td>{fmtPeriod(r.period)}</td><td>{r.published === 'not yet published' ? <span className="dim">not yet published</span> : fmtDay(r.published)}</td><td className="r">{r.value == null ? '—' : num(r.value, r.value < 10 ? 3 : 1)}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
            <h3 className="rp-h3">Market signals at that date</h3>
            <dl className="kv">
              {b.signals.map((x) => <div key={x.id}><dt>{CONTEXT[x.id] ?? x.meaning}</dt><dd>{x.value == null ? '—' : `${signed(x.value, 1)}%`}</dd></div>)}
            </dl>
          </section>

          <section className="rp-issued" aria-labelledby="issued-h">
            <p className="rp-label">Issued on {fmtDay(b.issuance_date)}</p>
            <h2 id="issued-h">The outlook issued then</h2>
            <p className={`rp-word ${DIR[v.dir].cls}`}><i aria-hidden="true">{DIR[v.dir].glyph}</i>{DIR[v.dir].word}</p>
            <ProbBars f={f} />
            {v.closeCall && <p className="call-close">{v.tied.map((k) => DIR[k].word).join(' and ')} carried the same probability: a close call.</p>}
            <div className="rp-basis"><Basis f={f} /></div>
          </section>
        </div>

        <div className="rp-cut" role="separator"><span>Issuance cut-off · {fmtDay(b.issuance_date)} · nothing below this line was known</span></div>

        <section className="rp-later" aria-labelledby="later-h">
          <div className="rp-later-head">
            <p className="rp-label">Learned later</p>
            <h2 id="later-h">The outcome</h2>
          </div>
          <dl className="rp-outcome">
            <div>
              <dt>First release</dt>
              <dd>{of.label ? <><Dir d={of.label} /> <span className="num">{pct(of.pct_change)}</span></> : <span className="dim">Not yet published</span>}</dd>
              <dd className="fine">{of.label_date ? `Published ${fmtDay(of.label_date)}` : `Expected ${fmtDay(b.target_first_release)}`}</dd>
            </div>
            <div>
              <dt>Final figure</dt>
              <dd>{fin.label ? <><Dir d={fin.label} /> <span className="num">{pct(fin.pct_change)}</span></> : <span className="dim">Not yet final</span>}</dd>
              <dd className="fine">{fin.label_date ? `Final on ${fmtDay(fin.label_date)}` : 'BLS revises each month three times'}</dd>
            </div>
            <div>
              <dt>The outlook was</dt>
              <dd className={`rp-result ${result}`}>{result === 'correct' ? 'Correct' : result === 'missed' ? 'Missed' : 'Pending'}</dd>
              <dd className="fine">{result === 'pending' ? 'Scored when the final figure is published' : `Outlook ${DIR[f.p].word}; final outcome ${DIR[scored].word}`}</dd>
            </div>
          </dl>
          {revised.length > 0 && (
            <p className="fine rp-rev">
              Revised after issuance: {revised.map((r) => `${r.input} ${fmtPeriod(r.period)} from ${num(r.value)} to ${num(r.later)}`).join('; ')}. The outlook used the values as they stood on the issuance date.
            </p>
          )}
          <p className={`rp-leak ${b.leakage_check.passed ? 'ok' : 'bad'}`}>
            <b>{b.leakage_check.passed ? 'No later information was used.' : 'Check failed.'}</b>{' '}
            The newest figure available to this outlook was published {fmtDay(b.leakage_check.latest_input_publication)}, on or before the issuance date of {fmtDay(b.leakage_check.issuance_date)}.
          </p>
        </section>


        <Section title="Every outlook" id="all" aside="One square per month. Filled: correct. Hollow: missed. Hatched: awaiting the final figure. Select a square to replay that month.">
          <OutcomeStrip items={outlook.forecasts} to={(m) => `/replay?month=${m}`} current={b.target_month} />
          <p className="fine rp-more">Outlooks from {fmtMonth(months[0].target_month)} to {fmtMonth(months.at(-1).target_month)}. Each was produced from the data as published by its issuance date.</p>
        </Section>

        <nav className="next-row" aria-label="Continue">
          <Next to="/market/forecast" title="Forecast" note="The current outlook" />
          <Next to="/estimate" title="Shipment scenario" note="Test a rate movement of your own" />
          <Next to="/methodology#leakage" title="No hindsight" note="How later information is kept out" />
        </nav>
      </div>
    </>
  )
}
