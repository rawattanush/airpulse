import { Link, useOutletContext } from 'react-router-dom'
import { useMarket, useOutlook } from '../lib/data.js'
import { lastFuelChange, marketRead, outlookView, withChanges } from '../lib/derive.js'
import { DIR, fmtDay, fmtMonth, fmtMonthLong, fmtTime, monthName, monthOnly, num, pct, prob } from '../lib/format.js'
import { Loading, Next, SourceAlert } from '../components/bits.jsx'
import { C, DIRC, ProbBars, TimeChart } from '../components/charts.jsx'

const MODE = { SNAPSHOT: 'Snapshot data', AUTOMATED: 'Automated data', LIVE: 'Live data' }

/** The sentence that says what the outlook means, in terms of the index and its band. */
export function outlookSentence(dir, band, month) {
  if (dir === 'UP') return `The Asia → US air-freight price index is expected to rise by more than ${band}% in ${month}.`
  if (dir === 'DOWN') return `The Asia → US air-freight price index is expected to fall by more than ${band}% in ${month}.`
  return `The Asia → US air-freight price index is expected to stay within ±${band}% of the previous month in ${month}.`
}

/** Why the outlook is what it is. The official approach is the seasonal record, so the reason is a count of earlier years. */
export function Basis({ f }) {
  const b = f.basis
  if (!b) return <p>The outlook comes from the approach with the best validated record on this market. <Link to="/methodology#forecasting">How it is formed</Link></p>
  const m = monthName(b.calendar_month - 1), t = b.up + b.flat + b.down || 1
  return (
    <>
      <p>
        The outlook rests on the seasonal record. In the {b.years} {m}s from {b.first_year} to {b.last_year}, the index rose in <b>{b.up}</b>, was stable in <b>{b.flat}</b> and fell in <b>{b.down}</b>.
      </p>
      <div className="basis-bar" role="img" aria-label={`${m}: rising ${b.up} years, stable ${b.flat}, falling ${b.down}`}>
        {[['UP', b.up], ['FLAT', b.flat], ['DOWN', b.down]].map(([k, n]) => n > 0 && <span key={k} style={{ flexGrow: n, background: DIRC[k] }}>{DIR[k].word} {n}</span>)}
      </div>
      <p className="fine">{t} earlier {m}s whose final figure was published by the issuance date. <Link to="/methodology#forecasting">How the outlook is formed</Link></p>
    </>
  )
}

export default function Overview() {
  const core = useOutletContext()
  const outlook = useOutlook()
  const market = useMarket(core.primary)
  if (!outlook || !market) return <Loading what="today's briefing" />
  const rows = withChanges(market.history)
  const { last, run } = marketRead(rows)
  const chart = rows.slice(-36)
  const f = outlook.forecasts.at(-1), v = outlookView(f), o = outlook.official
  const fuel = lastFuelChange(core.fuel.jet)
  const month = fmtMonthLong(f.t)

  return (
    <div className="page brief">
      <SourceAlert core={core} />
      <p className="dateline"><span>Market briefing</span><span>Outlook for {month}</span><span>Issuance date {fmtDay(f.i)}</span></p>

      <div className="brief-top">
        <div className="brief-call">
          <p className="eyebrow">AirPulse outlook</p>
          <h1 className={`call-word ${DIR[v.dir].cls}`}><i aria-hidden="true">{DIR[v.dir].glyph}</i>{DIR[v.dir].word}</h1>
          <p className="call-sub">{outlookSentence(v.dir, outlook.flat_band_pct, month)}</p>
          {v.closeCall && <p className="call-close">{v.tied.map((k) => DIR[k].word).join(' and ')} carries the same probability. Read this as a close call.</p>}
        </div>
        <div className="brief-prob">
          <p className="eyebrow">Outlook probability</p>
          <p className="big-num">{prob(v.p)}</p>
          <ProbBars f={f} />
          <dl className="kv">
            <div><dt>Forecast period</dt><dd>{month}</dd></div>
            <div><dt>Outcome published</dt><dd>{fmtDay(f.o)}</dd></div>
            <div><dt>Historical record</dt><dd>{o.hit_rate ? `${Math.round(o.hit_rate * 100)}% correct` : '—'} <span>of {o.months_scored} months</span> <Link className="kv-more" to="/market/forecast#history">by direction</Link></dd></div>
          </dl>
        </div>
      </div>

      <figure className="figure brief-chart">
        <figcaption>
          <b>Asia → US air-freight price index</b>
          <span>Index level, not a freight quote · last three years</span>
        </figcaption>
        <TimeChart rows={chart} height={280} label="Asia to US air-freight price index, last 36 months"
          series={[{ key: 'v', name: 'Index level', color: C.navy, width: 2.2, type: 'line' }]} yFmt={(x) => num(x, 0)} tipFmt={(x) => num(x)}
          dots={[{ i: chart.length - 1, key: 'v', label: `${num(last.v)} · ${fmtMonth(last.m)}` }]} />
      </figure>

      <section className="brief-row" aria-labelledby="changed-h">
        <h2 id="changed-h">What changed?</h2>
        <ol className="changed">
          <li>
            <span className="changed-n">1</span>
            <div>
              <h3>The market index {DIR[last.dir]?.past ?? 'moved'} {num(Math.abs(last.mom))}% in {monthOnly(last.m)}</h3>
              <p>To a level of {num(last.v)}{run > 1 ? `, the ${ordinal(run)} ${DIR[last.dir].word.toLowerCase()} month in a row` : ''}. Against a year earlier: {pct(last.yoy)}. {last.final ? '' : 'A first release; it can still be revised.'}</p>
              <Link to="/market">Market</Link>
            </div>
          </li>
          <li>
            <span className="changed-n">2</span>
            <div>
              <h3>Jet fuel {fuel.m1 > 0 ? 'rose' : 'fell'} {num(Math.abs(fuel.m1))}% on the month</h3>
              <p>US Gulf Coast jet fuel averaged ${num(fuel.value, 2)} a gallon in {monthOnly(fuel.month)}; {pct(fuel.m3)} over three months.</p>
              <Link to="/market/fuel">Fuel prices</Link>
            </div>
          </li>
        </ol>
      </section>

      <section className="brief-row" aria-labelledby="why-h">
        <h2 id="why-h">Why?</h2>
        <div className="why">
          <div className="why-main"><Basis f={f} /></div>
          <div className="why-side">
            <p className="eyebrow">Around the market</p>
            <p>
              The index {DIR[last.dir]?.past ?? 'moved'} {num(Math.abs(last.mom))}% in {monthOnly(last.m)} and jet fuel {fuel.m1 > 0 ? 'rose' : 'fell'} {num(Math.abs(fuel.m1))}%.
            </p>
            <p className="fine">Context for a reader. These are not inputs of the outlook.</p>
          </div>
        </div>
      </section>

      <nav className="next-row" aria-label="Go deeper">
        <Next to="/market/forecast" title="View forecast" note="Probabilities, record, what was known" />
        <Next to="/operations" title="Air traffic" note="Flights counted at Hong Kong and on US routes" />
        <Next to="/replay" title="Replay history" note="What AirPulse knew on any past date" />
      </nav>

      <p className="brief-state">
        <i className={core.state.data_mode.toLowerCase()} aria-hidden="true" />
        {MODE[core.state.data_mode]} · last data refresh {fmtTime(core.state.latest_ingestion)} · index through {fmtMonth(last.m)} · fuel through {fmtDay(core.fuel.jet.latest_date)} · a public market proxy for the Asia → US lane, not a freight quote.{' '}
        <Link to="/data">Data state</Link>
      </p>
    </div>
  )
}

function ordinal(n) {
  const s = ['th', 'st', 'nd', 'rd'], v = n % 100
  return n + (s[(v - 20) % 10] || s[v] || s[0])
}
