import { Link, useOutletContext } from 'react-router-dom'
import { useOutlook, useWeekly } from '../lib/data.js'
import { fmtDay, fmtMonth, int, prob, share } from '../lib/format.js'
import { Banner, Loading } from '../components/bits.jsx'

const TOC = [
  ['proxy', 'What AirPulse predicts'], ['data', 'Data'], ['target', 'The target'], ['forecasting', 'How the outlook is formed'], ['benchmarks', 'Benchmarks'],
  ['expansion', 'What was tested to improve it'], ['weekly', 'The weekly fuel-cost outlook'], ['aviation', 'Air traffic'], ['validation', 'Walk-forward validation'], ['leakage', 'No hindsight'], ['limitations', 'Limitations'], ['roadmap', 'Towards rate estimates'], ['control-center', 'Control Center'],
]

export default function Methodology() {
  const core = useOutletContext()
  const outlook = useOutlook()
  const weekly = useWeekly()
  if (!outlook) return <Loading what="the methodology" />
  const o = outlook.official, lane = core.lanes.find((l) => l.primary)
  const pctHit = Math.round(o.hit_rate * 1000) / 10
  const flat = outlook.reliability?.find((c) => c.dir === 'FLAT')
  const [evalFrom, evalTo] = o.evaluation_period.split(' to ')

  return (
    <>
      <Banner photo="engine" alt="Close view of a turbofan engine in warm light" kicker="Research · Methodology" title="How AirPulse works, and what it does not claim"
        lede="The target, the data, the forecast, how it is validated, and where the limits are." focus="50% 50%" />
      <div className="page flush doc">
        <nav className="doc-toc" aria-label="On this page">
          <p className="eyebrow">On this page</p>
          <ol>{TOC.map(([id, t]) => <li key={id}><a href={`#${id}`}>{t}</a></li>)}</ol>
        </nav>
        <article className="doc-body">
          <section id="proxy">
            <h2>What AirPulse predicts, and what it does not</h2>
            <div className="doc-two">
              <div className="doc-is">
                <p className="eyebrow">Currently predicts</p>
                <p>The <b>direction</b> of the monthly BLS Asia → US air-freight price index: rising, stable or falling against the previous month.</p>
              </div>
              <div className="doc-not">
                <p className="eyebrow">Does not predict</p>
                <p>Direct carrier quotes, validated route-level freight prices per kilogram, or South Asia → Europe rates.</p>
              </div>
            </div>
            <p>{core.proxy_statement}</p>
            <p>The index is a public market proxy. It is published by the US Bureau of Labor Statistics from prices that carriers report, and it describes the average price level of air freight imported into the United States from Asia. It is a level relative to a base period. It is not an amount of money, and it is not what any one shipper pays.</p>
          </section>

          <section id="data">
            <h2>Data</h2>
            <p>AirPulse reads published information only and stores every value with the date it became public.</p>
            <dl className="doc-list">
              <div><dt>Air-freight price indices</dt><dd>{core.counts.lanes} BLS import and export air-freight indices, with every revision BLS has made to them. The Asia → US index runs from {fmtMonth(lane.first_month)}; it is monthly from December 2005.</dd></div>
              <div><dt>Fuel prices</dt><dd>US Gulf Coast jet fuel and Brent crude, daily, in US dollars. A day's price is treated as public {core.fuel_lag_days} days later, which is how long publication has taken.</dd></div>
              <div><dt>Flight counts</dt><dd>Hong Kong International Airport's own flight information, every flight of each day, and the US Department of Transportation's monthly count of nonstop international departures. Shown as counted; nothing is derived from them.</dd></div>
            </dl>
            <p>The current data are a snapshot retrieved on {fmtDay(core.snapshot_retrieved)}. <Link to="/data">Data state and sources</Link></p>
          </section>

          <section id="target">
            <h2>The target</h2>
            <p>For each month the index either rises, stays stable or falls against the month before. A change of more than ±{core.flat_band_pct}% counts as rising or falling; anything inside that band counts as stable.</p>
            <p>BLS publishes a first figure for each month and then revises it in the next {core.revision_releases} releases. The outlook is scored against the final figure. The first release is shown too, because it is what a reader sees first, and the two sometimes disagree.</p>
            <p>The outlook for a month is issued on the day the previous month's first figure is published, which is during the month it describes. It is a statement about a month that is under way and not yet measured.</p>
          </section>

          <section id="forecasting">
            <h2>How the outlook is formed</h2>
            <p>The AirPulse outlook is one result. It comes from the <b>{o.method_name.toLowerCase()}</b>: {o.method_text.charAt(0).toLowerCase() + o.method_text.slice(1)}</p>
            <ol className="doc-steps">
              <li>Take the calendar month of the outlook, for example September.</li>
              <li>Count how the index moved in every earlier September whose final figure was already published on the issuance date.</li>
              <li>Turn the three counts into probabilities, adding one to each count so that no direction is ever given zero.</li>
              <li>The outlook is the direction with the highest probability. When two are level, a fixed order decides (falling, stable, rising) and the page says that it is a close call.</li>
            </ol>
            <p>The outlook probability shown is this share. It is not a confidence interval and not a guarantee.</p>
            <p>This approach is the official outlook because it has the best validated record on this market. {o.selection.split('. ').slice(-1)[0]}</p>
          </section>

          <section id="benchmarks">
            <h2>Benchmarks</h2>
            <p>The engine evaluates {o.other_approaches_evaluated + 1} approaches side by side on the same months: three simple rules, of which the seasonal record is one, and two statistical models that use recent index changes and fuel prices.</p>
            <p><b>{o.other_approaches_with_a_better_record === 0 ? 'None of the other approaches has a better record than the seasonal record on this market.' : `${o.other_approaches_with_a_better_record} other approaches have a better record on one measure.`}</b> The more complex models did not outperform it. That is the finding, and it is reported as found: a more elaborate model is not used merely because it is more elaborate.</p>
            <p>Customers see one outlook. The comparison of approaches, with its technical scores, is kept in the <a href="#control-center">Control Center</a>.</p>
          </section>

          <section id="expansion">
            <h2>What is not in the product, and why</h2>
            <p>AirPulse shows only what is real, licensed, automated and validated. Work that did not reach that standard stays in the research repository. The list is generated from the engine's production policy.</p>
            <dl className="doc-list">
              {core.not_in_product.map((n) => <div key={n.name}><dt>{n.name} <span className="dim">· {n.state}</span></dt><dd>{n.why}</dd></div>)}
            </dl>
          </section>

          {weekly?.available && (
            <section id="weekly">
              <h2>The weekly fuel-cost outlook</h2>
              <p><b>Weekly air-freight price forecasting is not yet supportable with the public data identified.</b> A weekly forecast needs a weekly price that is real, public, usable and dated. Every weekly air-freight rate series found is closed by subscription or by its terms of use. AirPulse does not turn the monthly index into weekly values.</p>
              <p>One weekly series does meet every condition, and it is a cost of air freight, not its price: the US Gulf Coast jet fuel spot price, published by the US Energy Information Administration in a weekly release. AirPulse keeps every release as it was published, {int(weekly.releases)} of them since 2011.</p>
              <dl className="doc-list">
                <div><dt>What is forecast</dt><dd>Whether the average price of the next weekly release will be above, within ±{weekly.band_pct}% of, or below the average of the release just published.</dd></div>
                <div><dt>When</dt><dd>On the release date. Every day of the week being forecast lies after the last price known. The outcome is published a week later.</dd></div>
                <div><dt>How</dt><dd>{weekly.method.text}</dd></div>
                <div><dt>Record</dt><dd>{weekly.record.correct} of {weekly.record.scored} weeks correct ({share(weekly.record.correct, weekly.record.scored)}), {fmtDay(weekly.first_scored)} to {fmtDay(weekly.last_scored)}. Repeating the previous week's direction was right {share(weekly.record.simple_rules[0].correct, weekly.record.simple_rules[0].scored)} of the time.</dd></div>
                <div><dt>The rule it had to meet</dt><dd>Better than three simple rules by a reliable margin, in each of three periods, with probabilities that hold. Written down before the test. More elaborate versions were tested and did worse.</dd></div>
              </dl>
              {weekly.carry_forward?.is_a_carry_forward && (
                <p><b>It is a carry-forward of the latest price, not a prediction of the price.</b> A second test asked whether anything forecasts the coming week better than assuming the price stays where it last was: last week's average, a four-week average, the usual follow-through of weekly changes, and adjustments for crude oil and momentum. Over {int(weekly.carry_forward.weeks)} weeks, none did.</p>
              )}
              <p>It is offered as what it is. <Link to="/market/weekly">Weekly fuel-cost outlook</Link></p>
            </section>
          )}

          <section id="aviation">
            <h2>Air traffic</h2>
            <p>The air traffic page shows counts of flights as two official sources publish them: every flight of each day at Hong Kong International Airport, and the monthly number of nonstop departures between US and foreign airports. Each is shown with its date and the state of its source.</p>
            <ul className="doc-bullets">
              <li><b>Counts only.</b> No expected level, no reading of what is unusual and no flag is shown. A method for that was built and tested against a rule set beforehand; it did not meet the rule, so it is not part of the product.</li>
              <li><b>Not capacity.</b> A flight count is not cargo capacity and an aircraft type is not a payload. No capacity figure is shown.</li>
              <li><b>Not a price signal.</b> Whether flight activity helps the freight outlook was tested; it does not, and no air-traffic figure enters the outlook.</li>
              <li><b>Missing is not zero.</b> A day or month a source did not cover is absent.</li>
              <li><b>Old is said to be old.</b> The route counts are published months after the month they describe and are shown as a historical record.</li>
            </ul>
            <p><Link to="/operations">Air traffic</Link></p>
          </section>

          <section id="validation">
            <h2>Walk-forward validation</h2>
            <p>The record is built the way the outlook is used. For every month from {fmtMonth(evalFrom)}, the approach is given only what was published by that month's issuance date, makes its outlook, and is scored later against the final figure. Then the next month, with one more month of history.</p>
            <p className="doc-figure"><b>{pctHit}%</b><span>correct over {o.months_scored} scored months, {fmtMonth(evalFrom)} to {fmtMonth(evalTo)}. Choosing one of three directions at random would be right about {Math.round(o.chance_rate * 100)}% of the time.</span></p>
            <p>{o.months_scored} months is a small sample. The record is better than chance and far from certain. <Link to="/market/forecast#outcomes">Every outlook and its outcome</Link></p>
          </section>

          <section id="leakage">
            <h2>No hindsight</h2>
            <p>A forecast tested on history can look better than it is if it quietly uses information that was not yet public. AirPulse is built to prevent this.</p>
            <ul className="doc-bullets">
              <li>Every value is stored with its publication date, and every revision is kept beside the value it replaced.</li>
              <li>An outlook is computed from the data as they stood on its issuance date: first releases where the final figure did not exist yet.</li>
              <li>Each stored outlook can be recomputed from a copy of the data that has physically lost everything published later. The result is identical.</li>
            </ul>
            <p><Link to="/replay">Replay</Link> shows this for any month: what was known, what was issued, and what was learned afterwards.</p>
          </section>


          <section id="limitations">
            <h2>Limitations</h2>
            <ul className="doc-bullets">
              <li><b>A proxy, on one lane.</b> The outlook concerns the Asia → US index. How closely any other lane follows it is unknown.</li>
              <li><b>A direction, not a price.</b> AirPulse states which way the index is likely to move. It does not state by how much, and it gives no rate per kilogram.</li>
              <li><b>A simple method.</b> The official approach is a seasonal record. It cannot anticipate a shock that has no seasonal pattern.</li>
              <li><b>An official benchmark, not a shipment quote.</b> The outlook concerns the Asia → US air-freight price index of the U.S. Bureau of Labor Statistics. AirPulse gives no live quote for a lane.</li>
              <li><b>Monthly only.</b> AirPulse does not claim a validated forecast of a commercial lane rate over the next 7 to 14 days: no current rate series may be used without a licence. There is no weekly outlook.</li>
              {flat && flat.given - flat.happened > 0.05 && <li><b>“Stable” is overstated.</b> The probability shown for a stable month has been too high since {fmtMonth(evalFrom)}.</li>}
              <li><b>A small sample.</b> {o.months_scored} scored months. The record may not hold.</li>
              <li><b>Revisions.</b> The most recent months are first releases. BLS revises them, and a revision can change a direction.</li>
              <li>{core.registry.summary.scheduled_runs > 0
                ? <><b>Scheduled data, not real-time.</b> {core.registry.summary.scheduled_runs} scheduled fetches are on record. Each source is as fresh as its last fetch.</>
                : <><b>Snapshot data.</b> No scheduled fetch is on record: every refresh so far was started by a person. Nothing here is real-time.</>} <Link to="/data">Data state</Link></li>
            </ul>
          </section>

          <section id="roadmap">
            <h2>Towards rate estimates</h2>
            <p>The question a shipper asks is what a shipment will cost. Answering it needs data AirPulse does not have: historical rates per kilogram for the lane. With them, the path is: normalise routes and services, establish a baseline rate, test how the lane has moved with the market index, keep fuel, capacity and disruption only if they improve the estimate, and publish a range that has been checked against outcomes. Currency conversion comes after that, with its own uncertainty.</p>
            <p>None of this exists today. Until it does, AirPulse shows no route-level number. <Link to="/estimate">The estimate page</Link> says so, and offers a calculator for scenarios the user chooses.</p>
          </section>

          <section id="control-center">
            <h2>Control Center</h2>
            <p>AirPulse has two interfaces on one engine. This site is for people who need to read the market. The Control Center is for technical work: comparing approaches, benchmark scores, data and source health, validation and reproducibility.</p>
            <p>The Control Center is the Streamlit application of the AirPulse repository. From the repository folder: <code>streamlit run src/dashboard/app.py</code>.</p>
          </section>
        </article>
      </div>
    </>
  )
}
