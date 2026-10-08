import { Link } from 'react-router-dom'
import { useAviation } from '../lib/data.js'
import { sourceStatus } from '../lib/derive.js'
import { fmtDay, fmtMonth, int, num } from '../lib/format.js'
import { Empty, Loading, Next, PageHead, Section } from '../components/bits.jsx'
import { C, Legend, TimeChart } from '../components/charts.jsx'

// Observation only: counts of flights as the official sources publish them. This page holds no expected level, no reading of
// what is unusual, no capacity figure and no statement about prices. Every figure and every state is read from the export.
const STATE = { HEALTHY: 'Up to date', DEGRADED: 'Last fetch incomplete', STALE: 'Stale', FAILED: 'Fetch failing', UNAVAILABLE: 'Unavailable' }

/** A source: what it is, how far it runs, its state now (worked out when the page is opened) and the attribution its terms ask for. */
export function SourceCard({ s, now }) {
  const st = sourceStatus(s.registry, now)
  return (
    <div className={`at-feed ${st.status.toLowerCase()}`}>
      <p className="at-feed-mode"><i aria-hidden="true" />{STATE[st.status] ?? st.status} · data through {s.through.length === 7 ? fmtMonth(s.through) : fmtDay(s.through)}</p>
      <p className="at-feed-name">{s.name}</p>
      <p className="fine">{s.kind}. {s.collected}{st.error ? ` ${st.error}` : ''}</p>
      <p className="fine">{s.attribution}</p>
    </div>
  )
}

export function Unavailable({ title = 'Air traffic data are not available', children }) {
  return (
    <div className="page narrow">
      <Empty title={title}>{children ?? 'No air traffic data have been exported.'}</Empty>
    </div>
  )
}

export default function AirTraffic() {
  const av = useAviation()
  if (!av) return <Loading what="air traffic" />
  if (!av.available) return <Unavailable>{Object.values(av.not_shown ?? {}).join(' ')}</Unavailable>
  const now = new Date(), ap = av.airport, L = ap?.latest, w = av.route_window
  const withheld = Object.values(av.not_shown ?? {})
  return (
    <div className="page at">
      <PageHead kicker="Operations · Air traffic" title="Observed air traffic"
        lede="Counts of flights from official sources, shown as published and with their date." />

      <p className="at-scope"><b>What this page is.</b> {av.statement}</p>

      <div className="at-feeds">{av.sources.map((s) => <SourceCard key={s.id} s={s} now={now} />)}</div>
      {withheld.map((t) => <p className="src-alert" role="status" key={t}>{t}</p>)}

      {ap && (
        <Section title={`${ap.name} (${ap.iata})`} id="airport" aside={`Every flight of each day from the airport's own flight information, archived since ${fmtDay(ap.first_day)}: ${int(ap.days_archived)} days. A day that was not archived is absent from the chart, not zero. Cancelled flights are counted beside movements, never among them.`}>
          <div className="at-figs">
            <div><p className="eyebrow">Movements · {fmtDay(L.day)}</p><p className="big-num">{int(L.movements)}</p><p className="fine">{int(L.arrivals)} arrivals, {int(L.departures)} departures</p></div>
            <div><p className="eyebrow">Cargo flights</p><p className="big-num">{int(L.cargo_movements)}</p><p className="fine">listed apart by the airport</p></div>
            <div><p className="eyebrow">Passenger flights</p><p className="big-num">{int(L.passenger_movements)}</p><p className="fine">same day</p></div>
            <div><p className="eyebrow">Cancelled</p><p className="big-num">{int(L.cancellations)}</p><p className="fine">same day</p></div>
          </div>
          <TimeChart rows={ap.series} xKey="d" xFmt={fmtDay} height={300} label={`${ap.iata}: flights per day`}
            series={[{ key: 'm', name: 'All movements', type: 'line', color: C.navy }, { key: 'c', name: 'Cargo flights', type: 'line', color: C.sky }]} yFmt={(v) => int(v)} tipFmt={(v) => int(v)} />
          <Legend items={[{ name: 'All movements', color: C.navy }, { name: 'Cargo flights', color: C.sky }]} />
          <div className="at-two">
            <div>
              <p>The airport reported {int(ap.cancellations.total)} cancelled flights in the archived days, on {int(ap.cancellations.days_with_any)} of them. The largest day was {fmtDay(ap.cancellations.largest_day)} with {int(ap.cancellations.largest)}.</p>
              <p className="fine">These are counts. They say nothing about why a flight was cancelled.</p>
            </div>
            {ap.cargo_first_stops.length > 0 && (
              <div className="tbl-wrap">
                <table className="tbl wrap">
                  <thead><tr><th>First stop of cargo departures</th><th className="r">Last {ap.window_days} days</th>{ap.previous_window_complete && <th className="r">{ap.window_days} days before</th>}</tr></thead>
                  <tbody>{ap.cargo_first_stops.slice(0, 8).map((x) => <tr key={x.airport}><td><b>{x.airport}</b> <span className="dim">{x.name ?? ''}</span></td><td className="r">{int(x.last)}</td>{ap.previous_window_complete && <td className="r">{int(x.previous)}</td>}</tr>)}</tbody>
                </table>
              </div>
            )}
          </div>
        </Section>
      )}

      {av.routes.length > 0 && (
        <Section title="Routes between Asia and the United States" id="routes" aside={`Official monthly count of nonstop departures, both directions together, through ${fmtMonth(w.through)}. The publisher releases it months after the month it describes: this is a historical record, not a current figure. The ${int(av.routes.length)} routes with the most departures in the newest ${w.months} months are listed.`}>
          <div className="tbl-wrap">
            <table className="tbl">
              <thead><tr><th>Route</th><th>From</th><th className="r">Departures, newest {w.months} months</th><th className="r">By all-cargo airlines</th><th className="r">{fmtMonth(w.through)}</th></tr></thead>
              <tbody>
                {av.routes.map((r) => (
                  <tr key={r.id}>
                    <td><Link to={`/operations/route/${r.id}`}><b>{r.from} – {r.to}</b></Link></td>
                    <td className="dim">{r.from_name}</td>
                    <td className="r num">{int(r.departures_last_12_months)}</td>
                    <td className="r num">{r.all_cargo_share == null ? '—' : `${num(r.all_cargo_share * 100, 0)}%`}</td>
                    <td className="r num">{r.latest.departures == null ? '—' : int(r.latest.departures)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>
      )}

      <nav className="next-row" aria-label="Go deeper">
        <Next to="/methodology#aviation" title="What is and is not shown" note="Why this page holds counts only" />
        <Next to="/data#sources" title="Data state" note="Every source, its state and its terms" />
      </nav>
    </div>
  )
}
