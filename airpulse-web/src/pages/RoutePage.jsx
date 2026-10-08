import { useParams } from 'react-router-dom'
import { useAviation } from '../lib/data.js'
import { fmtMonth, int, num } from '../lib/format.js'
import { Loading, Next, PageHead, Section, Tag } from '../components/bits.jsx'
import { C, TimeChart } from '../components/charts.jsx'
import { SourceCard, Unavailable } from './AirTraffic.jsx'

// One route as the publisher counts it: monthly nonstop departures, both directions together. A historical record.
export default function RoutePage() {
  const { id } = useParams()
  const av = useAviation()
  if (!av) return <Loading what="the route" />
  if (!av.available || av.routes.length === 0) return <Unavailable>{Object.values(av.not_shown ?? {}).join(' ')}</Unavailable>
  const key = (id || '').toUpperCase(), [x, y] = key.split('-')
  const r = av.routes.find((q) => q.id === key) ?? av.routes.find((q) => q.id === `${y}-${x}`)
  const src = av.sources.find((s) => s.id === 'usdot')
  if (!r) {
    return (
      <div className="page at">
        <PageHead kicker="Operations · Air traffic · Route" title={`${x ?? '—'} – ${y ?? '—'}`} lede="Route departures"><Tag tone="soft">Not held</Tag></PageHead>
        <p className="at-scope"><b>No count is held for this route.</b> Route counts are held only for the nonstop routes between Asian and US airports that the publisher lists. Nothing is estimated in its place.</p>
        <div className="next-row"><Next to="/operations#routes" title="Routes that are held" note="Asia and the United States" /></div>
      </div>
    )
  }
  return (
    <div className="page at">
      <PageHead kicker={`Operations · Air traffic · Route · ${r.region}`} title={`${r.from} – ${r.to}`} lede={`Nonstop flights between ${r.from_name} and ${r.to}, both directions together, as counted by the publisher.`}>
        <Tag tone="soft">Historical record</Tag>
      </PageHead>
      <div className="at-feeds">{src && <SourceCard s={src} now={new Date()} />}</div>
      <div className="at-figs">
        <div><p className="eyebrow">Departures · {fmtMonth(r.latest.month)}</p><p className="big-num">{r.latest.departures == null ? '—' : int(r.latest.departures)}</p><p className="fine">in the month</p></div>
        <div><p className="eyebrow">Newest {av.route_window.months} months</p><p className="big-num">{int(r.departures_last_12_months)}</p><p className="fine">departures</p></div>
        <div><p className="eyebrow">By all-cargo airlines</p><p className="big-num">{r.all_cargo_share == null ? '—' : `${num(r.all_cargo_share * 100, 0)}%`}</p><p className="fine">of those departures</p></div>
      </div>
      <Section title="Departures by month" id="activity" aside="As published. A month the publisher did not list is a gap, not zero. A count of flights is not cargo capacity: it says nothing about aircraft size or load.">
        <TimeChart rows={r.series} xKey="m" xFmt={fmtMonth} height={300} label={`${r.id}: departures per month`} series={[{ key: 'a', name: 'Departures', type: 'line', color: C.navy }]} yFmt={(v) => int(v)} tipFmt={(v) => int(v)} />
      </Section>
      <div className="next-row"><Next to="/operations#routes" title="All routes" note="Asia and the United States" /></div>
    </div>
  )
}
