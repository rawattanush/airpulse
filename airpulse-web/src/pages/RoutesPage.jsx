import { Link, useOutletContext } from 'react-router-dom'
import { fmtMonth, num } from '../lib/format.js'
import { Arrow, Banner, Next, Section, Tag } from '../components/bits.jsx'
import { C, Spark } from '../components/charts.jsx'

/* A schematic of the lanes, not a map: which directions have a published index, and which one has an outlook. */
function LaneSchematic() {
  const node = (x, y, label, anchor, dx) => (
    <g>
      <circle cx={x} cy={y} r="7" fill={C.navy} stroke="#fff" strokeWidth="2" />
      <text x={x + dx} y={anchor === 'middle' ? y + 30 : y + 5} textAnchor={anchor} className="lane-node">{label}</text>
    </g>
  )
  return (
    <svg className="lane-svg" viewBox="0 0 900 340" role="img" aria-label="Schematic of covered lanes: Asia to United States has an AirPulse outlook; Europe to United States, United States to Europe and United States to Asia are tracked indices; South Asia to Europe is not covered.">
      <defs>
        <marker id="ah-y" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill={C.yellow} /></marker>
        <marker id="ah-s" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill={C.sky} /></marker>
        <marker id="ah-g" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill={C.grey} /></marker>
      </defs>
      <path d="M735 158 C 600 20, 300 20, 166 158" fill="none" stroke={C.yellow} strokeWidth="5" markerEnd="url(#ah-y)" />
      <text x="450" y="44" textAnchor="middle" className="lane-label strong">Asia → United States · AirPulse outlook</text>
      <path d="M166 184 C 320 330, 590 330, 738 186" fill="none" stroke={C.sky} strokeWidth="2.5" markerEnd="url(#ah-s)" />
      <text x="450" y="318" textAnchor="middle" className="lane-label">United States → Asia · tracked index</text>
      <path d="M440 162 C 360 122, 250 122, 170 162" fill="none" stroke={C.sky} strokeWidth="2.5" markerEnd="url(#ah-s)" />
      <path d="M170 178 C 250 216, 360 216, 440 180" fill="none" stroke={C.sky} strokeWidth="2.5" markerEnd="url(#ah-s)" />
      <text x="305" y="116" textAnchor="middle" className="lane-label">Europe ⇄ United States · tracked indices</text>
      <path d="M688 228 C 620 232, 520 216, 468 186" fill="none" stroke={C.grey} strokeWidth="2" strokeDasharray="5 6" markerEnd="url(#ah-g)" />
      <text x="572" y="254" textAnchor="middle" className="lane-label dim">South Asia → Europe · not covered</text>
      {node(150, 170, 'United States', 'end', -14)}
      {node(452, 170, 'Europe', 'start', 13)}
      {node(750, 170, 'Asia', 'start', 14)}
      <circle cx="696" cy="228" r="5" fill="#fff" stroke={C.grey} strokeWidth="2" />
      <text x="708" y="232" className="lane-node-sub">South Asia</text>
    </svg>
  )
}

export default function RoutesPage() {
  const core = useOutletContext()
  const main = core.lanes.find((l) => l.primary)
  const tracked = core.lanes.filter((l) => !l.primary)
  return (
    <>
      <Banner photo="network" alt="Flight paths linking cities across the globe at night" kicker="Operations · Routes" title="What AirPulse covers, lane by lane"
        lede="One lane has an AirPulse outlook. Seven more have a published index that AirPulse stores. Route-specific freight estimates are not currently supported." focus="50% 45%" />
      <div className="page flush routes">
        <LaneSchematic />

        <section className="lane-main" aria-labelledby="lane-main-h">
          <div>
            <p className="lane-tags"><Tag tone="yellow">AirPulse outlook</Tag><Tag>Public market proxy</Tag></p>
            <h2 id="lane-main-h">Asia <span aria-hidden="true">→</span><span className="sr"> to </span> United States</h2>
            <p>The one lane AirPulse forecasts. It is measured by the BLS price index for air freight imported into the United States from Asia: a public measure of the market, used as a proxy. It is not a quote for any airport pair.</p>
            <p className="lane-links"><Link to="/market" className="text-link">Market <Arrow /></Link><Link to="/market/forecast" className="text-link">Forecast <Arrow /></Link></p>
          </div>
          <dl className="kv">
            <div><dt>Market level</dt><dd>{num(main.latest_value)} <span>index, not a quote</span></dd></div>
            <div><dt>Latest month</dt><dd>{fmtMonth(main.latest_month)}</dd></div>
            <div><dt>Published since</dt><dd>{fmtMonth(main.first_month)}</dd></div>
            <div><dt>Outlook</dt><dd>Monthly direction</dd></div>
          </dl>
        </section>

        <Section title="Tracked indices" id="tracked" aside="AirPulse stores these BLS air-freight indices and shows their record. It issues no outlook for them.">
          <div className="tbl-wrap">
            <table className="tbl lane-board">
              <thead><tr><th>Lane</th><th>BLS series</th><th className="r">Index level</th><th>Latest month</th><th>Five years</th><th>Coverage</th></tr></thead>
              <tbody>
                {tracked.map((l) => (
                  <tr key={l.id}>
                    <td><Link to={`/market?lane=${l.id}`}>{l.name.replace(' air freight', '')}</Link></td>
                    <td className="dim">{l.title}</td>
                    <td className="r">{num(l.latest_value)}</td>
                    <td>{fmtMonth(l.latest_month)}</td>
                    <td><Spark values={l.spark} /></td>
                    <td><Tag tone="soft">Index only</Tag></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>

        <Section title="Not covered" id="not-covered" aside="Said plainly, so that nothing on this site is read as more than it is.">
          <ul className="lane-not">
            <li>
              <h3>South Asia → Europe</h3>
              <p>For example Mumbai to Frankfurt. No public historical price series for this lane could be obtained, so AirPulse has no outlook and no estimate for it. How closely the Asia → US index follows India–Europe rates is unknown.</p>
            </li>
            <li>
              <h3>Any airport-to-airport route</h3>
              <p>Route-specific freight estimates are not currently supported. AirPulse holds no carrier quotes and no lane rates per kilogram. <Link to="/estimate">What is needed, and a scenario calculator you can use today</Link></p>
            </li>
            <li>
              <h3>Carrier and service differences</h3>
              <p>The index averages the market. It does not distinguish airlines, service levels, contract and spot rates, or surcharges.</p>
            </li>
          </ul>
        </Section>

        <nav className="next-row" aria-label="Continue">
          <Next to="/estimate" title="Estimate" note="What a shipment estimate needs; a scenario calculator" />
          <Next to="/replay" title="Replay" note="What AirPulse knew on any past date" />
          <Next to="/methodology#roadmap" title="Towards rate estimates" note="The path to lane-level numbers" />
        </nav>
      </div>
    </>
  )
}
