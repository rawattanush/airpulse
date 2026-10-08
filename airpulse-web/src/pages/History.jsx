import { useState } from 'react'
import { Link, useOutletContext } from 'react-router-dom'
import { useLane, useMarket, useOutlook } from '../lib/data.js'
import { byYear, extremes, longestRun, marketRead, recordByYear, turningPoints, withChanges } from '../lib/derive.js'
import { fmtDay, fmtMonth, fmtMonthLong, num, pct } from '../lib/format.js'
import { Dir, Loading, Next, PageHead, Section, Tag } from '../components/bits.jsx'
import { DIRC } from '../components/charts.jsx'

const shift = (ym, k) => { const d = new Date(Date.UTC(+ym.slice(0, 4), +ym.slice(5, 7) - 1 + k, 1)); return d.toISOString().slice(0, 7) }

export default function History() {
  const core = useOutletContext()
  const [lane] = useLane(core)
  const market = useMarket(lane)
  const outlook = useOutlook()
  const [all, setAll] = useState(false)
  if (!market) return <Loading />
  const full = withChanges(market.history)
  const { high, low } = marketRead(full)
  const ext = extremes(full, 1)
  const up = longestRun(full, 'UP'), down = longestRun(full, 'DOWN')
  const have = new Set(full.map((r) => r.m)); const gaps = []
  for (let m = full[0].m; m < full.at(-1).m; m = shift(m, 1)) if (!have.has(m)) gaps.push(m)
  const tp = turningPoints(full, 18)
  const years = byYear(full).filter((y) => y.year >= '2006').reverse()
  const isPrimary = lane === core.primary
  const rec = isPrimary && outlook ? Object.fromEntries(recordByYear(outlook.forecasts).map((y) => [y.year, y])) : {}

  const marks = [
    { m: high.m, title: 'Record high', text: `The index reached ${num(high.v)}, the highest level since monthly publication began.` },
    { m: low.m, title: 'Record low', text: `The lowest level of the monthly record: ${num(low.v)}.` },
    { m: ext.rises[0].m, title: 'Largest monthly rise', text: `${pct(ext.rises[0].mom)} in a single month, to ${num(ext.rises[0].v)}.` },
    { m: ext.falls[0].m, title: 'Largest monthly fall', text: `${pct(ext.falls[0].mom)} in a single month, to ${num(ext.falls[0].v)}.` },
    up && { m: up.to, title: 'Longest rising run', text: `${up.n} rising months in a row, from ${fmtMonth(up.from)} to ${fmtMonth(up.to)}.` },
    down && { m: down.to, title: 'Longest falling run', text: `${down.n} falling months in a row, from ${fmtMonth(down.from)} to ${fmtMonth(down.to)}.` },
    ...gaps.map((g) => ({ m: g, title: 'A month without a figure', text: `BLS published no value for ${fmtMonthLong(g)}. AirPulse leaves the gap; it does not fill it in.` })),
  ].filter(Boolean).sort((a, b) => a.m.localeCompare(b.m))

  const desc = [...full].reverse()
  const shown = all ? desc : desc.slice(0, 24)

  return (
    <div className="page">
      <PageHead kicker="Market · History" title="How this market has behaved" lede={`${market.name}, monthly since ${fmtMonth(full[0].m)}: its extremes, its turning points and each year in turn.`}>
        {!isPrimary && <Tag>Tracked index</Tag>}
      </PageHead>

      <section className="hist-marks" aria-labelledby="marks-h">
        <h2 id="marks-h">The marks of the record</h2>
        <ol className="tl">
          {marks.map((k, i) => (
            <li key={i}>
              <time dateTime={k.m}>{fmtMonth(k.m)}</time>
              <div><h3>{k.title}</h3><p>{k.text}</p></div>
            </li>
          ))}
        </ol>
      </section>

      <Section title="Turning points" id="turns" aside="The highest and lowest months within eighteen months on either side: where the market changed direction for a sustained period.">
        <div className="tbl-wrap">
          <table className="tbl">
            <thead><tr><th>Month</th><th>Turn</th><th className="r">Index level</th><th className="r">Since the previous turn</th><th className="r">Months</th></tr></thead>
            <tbody>
              {tp.map((p, k) => {
                const prev = tp[k - 1]
                return (
                  <tr key={p.m}>
                    <td>{fmtMonth(p.m)}</td>
                    <td><span className={`turn ${p.kind}`}>{p.kind === 'high' ? 'High' : 'Low'}</span></td>
                    <td className="r">{num(p.v)}</td>
                    <td className="r">{prev ? pct((p.v / prev.v - 1) * 100) : '—'}</td>
                    <td className="r">{prev ? p.i - prev.i : '—'}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </Section>

      <Section title="Year by year" id="years" aside={isPrimary ? 'The level at the end of each year, how the months split, and how the AirPulse outlook fared in that year.' : 'The level at the end of each year and how the months split.'}>
        <div className="tbl-wrap">
          <table className="tbl hist-years">
            <thead><tr><th>Year</th><th className="r">Year-end level</th><th className="r">Change over the year</th><th>Rising · stable · falling months</th>{isPrimary && <th className="r">Outlook correct</th>}</tr></thead>
            <tbody>
              {years.map((y) => {
                const t = y.up + y.flat + y.down || 1, r = rec[y.year]
                return (
                  <tr key={y.year}>
                    <td>{y.year}{y.months < 12 && <span className="dim"> · {y.months} mo</span>}</td>
                    <td className="r">{num(y.end)}</td>
                    <td className="r">{pct(y.change)}</td>
                    <td>
                      <span className="yr-bar" role="img" aria-label={`${y.up} rising, ${y.flat} stable, ${y.down} falling`}>
                        <i style={{ width: `${(y.up / t) * 100}%`, background: DIRC.UP }} /><i style={{ width: `${(y.flat / t) * 100}%`, background: '#C5D2DE' }} /><i style={{ width: `${(y.down / t) * 100}%`, background: DIRC.DOWN }} />
                      </span>
                      <span className="yr-n">{y.up} · {y.flat} · {y.down}</span>
                    </td>
                    {isPrimary && <td className="r">{r && r.n ? `${r.correct} of ${r.n}` : <span className="dim">{r?.pending ? 'pending' : '—'}</span>}</td>}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        {isPrimary && <p className="fine hist-note">Outlooks are scored against the final published figure. The first outlook is for January 2016; earlier years were used only to build the seasonal record. <Link to="/market/forecast#outcomes">Every outlook and its outcome</Link></p>}
      </Section>

      <Section title="The full record" id="record" aside="Every published month, latest first. The most recent months are first releases and can still be revised.">
        <div className="tbl-wrap">
          <table className="tbl">
            <thead><tr><th>Month</th><th className="r">Index level</th><th className="r">Change</th><th className="r">On the year</th><th>Movement</th><th>Figure</th><th>First published</th></tr></thead>
            <tbody>
              {shown.map((r) => (
                <tr key={r.m}><td>{fmtMonth(r.m)}</td><td className="r">{num(r.v)}</td><td className="r">{pct(r.mom)}</td><td className="r">{pct(r.yoy)}</td><td><Dir d={r.dir} /></td><td>{r.final ? 'Final' : <span className="dim">First release</span>}</td><td>{fmtDay(r.rel)}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
        {!all && <button type="button" className="more" onClick={() => setAll(true)}>Show all {full.length} months</button>}
      </Section>

      <nav className="next-row" aria-label="Continue">
        {isPrimary && <Next to="/replay" title="Replay" note="What AirPulse knew in any of these months" />}
        {isPrimary && <Next to="/market/forecast" title="Forecast" note="The current outlook and its record" />}
        <Next to="/market/fuel" title="Fuel prices" note="Jet fuel and crude oil, as published" />
      </nav>
    </div>
  )
}
