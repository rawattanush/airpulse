import { useOutletContext } from 'react-router-dom'
import { useLane, useMarket } from '../lib/data.js'
import { turningPoints, withChanges } from '../lib/derive.js'
import { fmtMonth, monthShort, num, pct } from '../lib/format.js'
import { Loading, Next, PageHead, Section, Tag } from '../components/bits.jsx'
import { C, DIRC, Legend, SeasonGrid, ShareBars, TimeChart } from '../components/charts.jsx'

// The periods the engine's evaluation uses. The last one is open: it runs to the newest month held, and its label says so.
const ERA_STARTS = [['2006-01', '2015-12'], ['2016-01', '2019-12'], ['2020-01', '2022-12'], ['2023-01', null]]
const eraList = (lastMonth) => ERA_STARTS.map(([a, b]) => [`${a.slice(0, 4)}–${(b ?? lastMonth).slice(0, 4)}`, a, b ?? lastMonth])

function stats(rows) {
  const ch = rows.map((r) => r.mom).filter((v) => v != null)
  const mean = ch.reduce((a, b) => a + b, 0) / (ch.length || 1)
  const count = (d) => rows.filter((r) => r.dir === d).length
  return { n: ch.length, mean, up: count('UP'), flat: count('FLAT'), down: count('DOWN'), max: Math.max(...ch), min: Math.min(...ch), first: rows[0], last: rows.at(-1) }
}

export default function Trends() {
  const core = useOutletContext()
  const [lane] = useLane(core)
  const market = useMarket(lane)
  if (!market) return <Loading />
  const full = withChanges(market.history).filter((r) => r.m >= '2006-01')
  const tp = turningPoints(full, 18)
  const eras = eraList(full.at(-1).m).map(([label, a, b]) => ({ label, ...stats(full.filter((r) => r.m >= a && r.m <= b)) })).filter((e) => e.n > 0)
  const byMonth = Array.from({ length: 12 }, (_, i) => {
    const rs = full.filter((r) => +r.m.slice(5, 7) === i + 1 && r.dir)
    return { label: monthShort(i), up: rs.filter((r) => r.dir === 'UP').length, flat: rs.filter((r) => r.dir === 'FLAT').length, down: rs.filter((r) => r.dir === 'DOWN').length }
  })
  const rank = [...byMonth].sort((a, b) => b.up / (b.up + b.flat + b.down) - a.up / (a.up + a.flat + a.down))
  const yearTick = (r) => r.m.endsWith('-01') && +r.m.slice(0, 4) % 2 === 0
  const eraBands = eraList(full.at(-1).m).slice(1).map(([label, a]) => ({ i: full.findIndex((r) => r.m >= a), label })).filter((b) => b.i > 0)

  return (
    <div className="page">
      <PageHead kicker="Market · Trends" title="The market over time" lede={`${market.name}: the level, its monthly and yearly changes, and the seasonal pattern, from ${fmtMonth(full[0].m)} to ${fmtMonth(full.at(-1).m)}.`}>
        {lane !== core.primary && <Tag>Tracked index</Tag>}
      </PageHead>

      <figure className="figure trend-main">
        <figcaption><b>Index level, with its turning points</b><span>Index level, not a freight quote</span></figcaption>
        <TimeChart rows={full} height={440} label={`${market.name} index level with highs and lows`} series={[{ key: 'v', name: 'Index level', color: C.navy, width: 2, type: 'line' }]}
          yFmt={(v) => num(v, 0)} tipFmt={(v, k, r) => `${num(v)}${r.yoy != null ? ` (${pct(r.yoy)} on the year)` : ''}`} xTick={(m) => m.slice(0, 4)} tickEvery={yearTick}
          marks={eraBands} dots={tp.map((p) => ({ i: p.i, key: 'v', label: `${num(p.v, 0)} · ${fmtMonth(p.m)}`, fill: p.kind === 'high' ? C.yellow : C.sky, below: p.kind === 'low', centre: true }))} />
        <Legend items={[{ name: 'Local high', color: C.yellow, shape: 'box' }, { name: 'Local low', color: C.sky, shape: 'box' }]} />
        <p className="caption">A turning point is the highest or lowest month within eighteen months on either side; where two labels would collide, only the first is written, and all of them are listed under History. Dashed lines mark the periods used in the table below.</p>
      </figure>

      <Section title="Year over year" id="yoy" aside="The index against the same month a year earlier. This removes the seasonal pattern and shows the underlying direction.">
        <TimeChart rows={full} height={240} label="Year-over-year change of the index, per cent" yFmt={(v) => `${v}%`} tipFmt={(v) => pct(v)} zero xTick={(m) => m.slice(0, 4)} tickEvery={yearTick}
          series={[{ key: 'yoy', name: 'Change on the year', color: C.deep, width: 2, type: 'line' }]} />
      </Section>

      <Section title="Month over month" id="mom" aside={`Each bar is one month's change. Moves beyond ±${core.flat_band_pct}% count as rising or falling.`}>
        <TimeChart rows={full} height={220} label="Month-on-month change of the index, per cent" yFmt={(v) => `${v}%`} tipFmt={(v) => pct(v)} xTick={(m) => m.slice(0, 4)} tickEvery={yearTick}
          series={[{ key: 'mom', name: 'Change on the month', color: C.navy, colorNeg: C.sky, type: 'bar' }]} />
      </Section>

      <Section title="Seasonality" id="season" aside={`Some calendar months rise more often than others. ${rank[0].label} rose most often; ${rank.at(-1).label} least. This pattern is what the AirPulse outlook is built on.`}>
        <div className="trend-season">
          <div>
            <h3>Every month since 2006</h3>
            <SeasonGrid rows={full} />
            <Legend items={[{ name: 'Rising', color: DIRC.UP, shape: 'box' }, { name: 'Stable', color: '#C5D2DE', shape: 'box' }, { name: 'Falling', color: DIRC.DOWN, shape: 'box' }]} />
          </div>
          <div>
            <h3>How often each calendar month rose, held or fell</h3>
            <ShareBars rows={byMonth} />
          </div>
        </div>
      </Section>

      <Section title="Periods" id="periods" aside="The same market behaved differently in each period. Average and extreme monthly changes, and the count of months by direction.">
        <div className="tbl-wrap">
          <table className="tbl">
            <thead><tr><th>Period</th><th className="r">Start level</th><th className="r">End level</th><th className="r">Average month</th><th className="r">Largest rise</th><th className="r">Largest fall</th><th className="r">Rising</th><th className="r">Stable</th><th className="r">Falling</th></tr></thead>
            <tbody>
              {eras.map((e) => (
                <tr key={e.label}><td>{e.label}</td><td className="r">{num(e.first.v)}</td><td className="r">{num(e.last.v)}</td><td className="r">{pct(e.mean, 2)}</td><td className="r">{pct(e.max)}</td><td className="r">{pct(e.min)}</td><td className="r">{e.up}</td><td className="r">{e.flat}</td><td className="r">{e.down}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <nav className="next-row" aria-label="Continue">
        <Next to={`/market/history${lane === core.primary ? '' : `?lane=${lane}`}`} title="History" note="Extremes, turning points, year by year" />
        {lane === core.primary && <Next to="/market/forecast" title="Forecast" note="The outlook this seasonal pattern gives" />}
        <Next to="/market/fuel" title="Fuel prices" note="Jet fuel and crude oil, as published" />
      </nav>
    </div>
  )
}
