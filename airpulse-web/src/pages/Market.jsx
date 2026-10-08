import { useState } from 'react'
import { Link, useOutletContext } from 'react-router-dom'
import { useLane, useMarket, useOutlook, useWeekly } from '../lib/data.js'
import { lastFuelChange, marketRead, outlookView, weeklyView, withChanges } from '../lib/derive.js'
import { DIR, fmtDay, fmtMonth, fmtMonthLong, monthName, monthOnly, num, pct, prob } from '../lib/format.js'
import { Dir, IndexNote, Loading, Next, Photo, Section, Seg, Tag } from '../components/bits.jsx'
import { C, TimeChart } from '../components/charts.jsx'

const RANGES = [{ value: 24, label: '2Y' }, { value: 60, label: '5Y' }, { value: 120, label: '10Y' }, { value: 0, label: 'All' }]

/** Plain-English reading of the published figures. Every clause is arithmetic on the index; nothing is forecast here. */
function reading(read, band) {
  const { last, high, run, fromHigh } = read
  const out = []
  const d = last.dir
  out.push(d === 'FLAT'
    ? `Air-freight price levels on this lane were stable in ${monthOnly(last.m)}: the index moved ${pct(last.mom)}, inside the ±${band}% band that counts as no change.`
    : `Air-freight price levels on this lane ${DIR[d].past} ${num(Math.abs(last.mom))}% in ${monthOnly(last.m)}${run > 1 ? `, the ${run === 2 ? 'second' : run === 3 ? 'third' : `${run}th`} ${DIR[d].word.toLowerCase()} month in a row` : ''}.`)
  if (last.yoy != null) out.push(Math.abs(last.yoy) < 1 ? 'They are close to where they stood a year ago.' : `They are ${num(Math.abs(last.yoy))}% ${last.yoy > 0 ? 'higher' : 'lower'} than a year ago${Math.abs(last.yoy) >= 10 ? ', a substantial move' : ''}.`)
  out.push(high.m === last.m ? 'This is the highest level on record.' : `The index stands ${num(Math.abs(fromHigh))}% below its record high of ${num(high.v)}, set in ${fmtMonthLong(high.m)}.`)
  if (!last.final) out.push(`${monthOnly(last.m)}'s figure is a first release. BLS revises each month three times, and a revision can change the direction.`)
  return out
}

export default function Market() {
  const core = useOutletContext()
  const [lane] = useLane(core)
  const market = useMarket(lane)
  const outlook = useOutlook()
  const weekly = useWeekly()
  const [range, setRange] = useState(60)
  if (!market) return <Loading />
  const full = withChanges(market.history)
  const read = marketRead(full)
  const { last, high, run } = read
  const rows = range ? full.slice(-range) : full
  const recent = full.slice(-12).reverse()
  const isPrimary = lane === core.primary
  const [from, to] = market.name.replace(' air freight', '').split(' → ')
  const d = last.dir
  const next = isPrimary && outlook ? outlook.forecasts.at(-1) : null, nv = next ? outlookView(next) : null
  const wv = isPrimary && weekly?.available ? weeklyView(weekly) : null
  const b = next?.basis, fuel = lastFuelChange(core.fuel.jet)

  return (
    <>
      <header className="mkt-head">
        <Photo name="sunset" alt="" eager sizes="(max-width: 860px) 100vw, 60vw" focus="60% 55%" />
        <div className="mkt-head-in">
          <p className="eyebrow">{isPrimary ? 'Air-freight market · public market proxy' : 'Air-freight market · tracked index'}</p>
          <h1 className="mkt-lane">{to ? <>{from} <span aria-hidden="true">→</span><span className="sr"> to </span> {to}</> : market.name}</h1>
          <div className="mkt-now">
            <div className="mkt-move">
              <p className="eyebrow mkt-when">Movement in {fmtMonthLong(last.m)}</p>
              <p className={`mkt-dir ${d ? DIR[d].cls : ''}`}>{d ? DIR[d].word : '—'}</p>
              <p className="mkt-chg"><b className="num">{pct(last.mom)}</b> vs previous month</p>
            </div>
            <div className="mkt-level">
              <p className="eyebrow">Market level</p>
              <p className="mkt-val num">{num(last.v)}</p>
              <p className="mkt-what">BLS air-freight price index<br /><b>An index level, not a freight quote.</b></p>
            </div>
          </div>
          <p className="mkt-as-of">
            {fmtMonthLong(last.m)} is the latest published month · {last.final ? 'final figure' : 'first release'} · published {fmtDay(last.rel)}
            {nv && <Link to="/market/forecast" className="mkt-next">AirPulse outlook for {fmtMonthLong(next.t)}: <b>{DIR[nv.dir].word}</b> · {prob(nv.p)}{nv.closeCall ? ' · close call' : ''} →</Link>}
          </p>
        </div>
      </header>

      <div className="page flush">
        {!isPrimary && (
          <p className="callout navy mkt-tracked"><Tag>Tracked index</Tag> AirPulse stores this index and shows its record. It issues no outlook for this lane; the validated target is <Link to="/market">Asia → US</Link>.</p>
        )}
        <dl className="mkt-stats">
          <div><dt>Three months</dt><dd className="num">{pct(last.q3)}</dd></div>
          <div><dt>Year over year</dt><dd className="num">{pct(last.yoy)}</dd></div>
          <div><dt>Historical high</dt><dd className="num">{num(high.v)} <span>{fmtMonth(high.m)}</span></dd></div>
          <div><dt>Current run</dt><dd>{run} {run === 1 ? 'month' : 'months'} <Dir d={d} /></dd></div>
        </dl>
        <IndexNote last={last} />

        <figure className="figure mkt-chart">
          <figcaption><b>Index level</b><Seg label="Range" value={range} onChange={setRange} options={RANGES} /></figcaption>
          <TimeChart rows={rows} height={420} label={`${market.name} price index`} series={[{ key: 'v', name: 'Index level', color: C.navy, width: 2, type: 'line' }, { key: 'v', name: 'area', color: C.sky, type: 'area' }]}
            yFmt={(v) => num(v, 0)} tipFmt={(v, k, r) => `${num(v)}${r.mom != null ? ` (${pct(r.mom)})` : ''}`} dots={[{ i: rows.length - 1, key: 'v', label: `${num(last.v)} · ${fmtMonth(last.m)}` }]} />
          <p className="caption">{market.title}. BLS import and export price index, monthly, not seasonally adjusted. Published values from {fmtMonth(rows[0].m)} to {fmtMonth(last.m)}.</p>
        </figure>

        <section className="mkt-means" aria-labelledby="means-h">
          <h2 id="means-h">What this means</h2>
          <div>
            {reading(read, core.flat_band_pct).map((s, i) => <p key={i} className={i === 0 ? 'lead' : ''}>{s}</p>)}
            <p className="fine">These statements describe the published index. They are not a forecast and not a statement about any carrier's rates.</p>
          </div>
        </section>

        {isPrimary && nv && (
          <section className="mkt-out" aria-labelledby="out-h">
            <h2 id="out-h">Outlooks</h2>
            <div className="mkt-out-rows">
              <Link to="/market/forecast" className="mkt-out-row">
                <span className="eyebrow">Monthly · air-freight price index</span>
                <span className="mkt-out-q">Where is the monthly market direction heading?</span>
                <span className="mkt-out-a"><Dir d={nv.dir} /> <b className="num">{prob(nv.p)}</b> <em>for {fmtMonthLong(next.t)}{nv.closeCall ? ' · close call' : ''}</em></span>
              </Link>
              {wv && (
                <Link to="/market/weekly" className="mkt-out-row">
                  <span className="eyebrow">Weekly · jet fuel cost <i>not a freight price</i></span>
                  <span className="mkt-out-q">What is the cost of jet fuel doing this week?</span>
                  <span className="mkt-out-a"><Dir d={wv.dir} /> <b className="num">{prob(wv.p)}</b> <em>issued {fmtDay(wv.issued)}</em></span>
                </Link>
              )}
            </div>
            {b && (
              <div className="mkt-ctx">
                <div>
                  <h3>Seasonality</h3>
                  <p>In the {b.years} {monthName(b.calendar_month - 1)}s from {b.first_year} to {b.last_year}, the index rose in {b.up}, was stable in {b.flat} and fell in {b.down}. <Link to="/market/trends">Every month of the year</Link></p>
                </div>
                <div>
                  <h3>Fuel context</h3>
                  <p>US Gulf Coast jet fuel averaged ${num(fuel.value, 2)} a gallon in {monthOnly(fuel.month)}: {pct(fuel.m1)} on the month, {pct(fuel.m3)} over three. <Link to="/market/fuel#fuel">Fuel</Link></p>
                </div>
              </div>
            )}
          </section>
        )}

        <Section title="Month by month" aside={`A move of more than ±${core.flat_band_pct}% counts as rising or falling. Anything inside that band is stable.`} id="monthly">
          <TimeChart rows={rows} height={190} label="Month-on-month change of the index, per cent" yFmt={(v) => `${v}%`} tipFmt={(v) => pct(v)}
            series={[{ key: 'mom', name: 'Change on the month', color: C.navy, colorNeg: C.sky, type: 'bar' }]} />
          <div className="tbl-wrap mkt-table">
            <table className="tbl">
              <thead><tr><th>Month</th><th className="r">Index level</th><th className="r">Change</th><th>Movement</th><th>Figure</th><th>First published</th></tr></thead>
              <tbody>
                {recent.map((r) => (
                  <tr key={r.m}><td>{fmtMonth(r.m)}</td><td className="r">{num(r.v)}</td><td className="r">{pct(r.mom)}</td><td><Dir d={r.dir} /></td><td>{r.final ? 'Final' : <span className="dim">First release</span>}</td><td>{fmtDay(r.rel)}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>

        <nav className="next-row" aria-label="Continue">
          {isPrimary && <Next to="/market/forecast" title="Forecast" note="Where AirPulse expects the market to go" />}
          <Next to={`/market/trends${isPrimary ? '' : `?lane=${lane}`}`} title="Trends" note="Seasonality, periods, year-over-year" />
          <Next to={`/market/history${isPrimary ? '' : `?lane=${lane}`}`} title="History" note="Highs, lows and turning points" />
          {!isPrimary && <Next to="/routes" title="All lanes" note="What is covered and what is not" />}
        </nav>
      </div>
    </>
  )
}
