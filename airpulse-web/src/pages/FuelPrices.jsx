import { useState } from 'react'
import { Link, useOutletContext } from 'react-router-dom'
import { lastFuelChange } from '../lib/derive.js'
import { fmtDay, fmtMonthLong, num, pct } from '../lib/format.js'
import { Banner, Seg } from '../components/bits.jsx'
import { C, TimeChart } from '../components/charts.jsx'

// Published fuel prices, as context. Every figure is read from the export; nothing here is an input of the monthly outlook.
export default function FuelPrices() {
  const core = useOutletContext()
  const [view, setView] = useState('long')
  const jet = core.fuel.jet, brent = core.fuel.brent
  const j = lastFuelChange(jet), b = lastFuelChange(brent)
  const yearTick = (r) => r.m.endsWith('-01') && +r.m.slice(0, 4) % 3 === 0
  const chart = (s, name, unit, color) => view === 'long'
    ? <TimeChart rows={s.monthly} height={250} label={`${name}, monthly average`} series={[{ key: 'v', name, color, width: 2, type: 'line' }]} yFmt={(v) => `$${num(v, unit === 'gal' ? 1 : 0)}`} tipFmt={(v) => `$${num(v, 2)}`} xTick={(m) => m.slice(0, 4)} tickEvery={yearTick} />
    : <TimeChart rows={s.daily} xKey="d" xFmt={fmtDay} height={250} label={`${name}, daily`} series={[{ key: 'v', name, color, width: 1.6, type: 'line' }]} yFmt={(v) => `$${num(v, unit === 'gal' ? 1 : 0)}`} tipFmt={(v) => `$${num(v, 2)}`} />
  return (
    <>
      <Banner photo="globe" alt="The Earth at night from orbit, Europe to Asia" kicker="Market · Fuel" title="Fuel prices"
        lede="Fuel is among the largest costs of flying cargo. Published market prices, with the date each became public." focus="50% 40%" />
      <div className="page flush drivers">
        <section className="drv drv-fuel" id="fuel" aria-labelledby="fuel-h">
          <div className="drv-intro">
            <p className="eyebrow">Published prices</p>
            <h2 id="fuel-h">Jet fuel and crude oil</h2>
            <p className="drv-read">Jet fuel averaged <b>${num(j.value, 2)}</b> a gallon in {fmtMonthLong(j.month)}: {pct(j.m1)} on the month, {pct(j.m3)} over three months, {pct(j.y1)} on the year.</p>
            <Seg label="Period" value={view} onChange={setView} options={[{ value: 'long', label: `Since ${jet.monthly[0].m.slice(0, 4)}` }, { value: 'recent', label: 'Last two years' }]} />
          </div>
          <div className="drv-fuel-charts">
            <figure className="figure">
              <figcaption><b>Jet fuel, US Gulf Coast</b><span>US dollars per gallon · latest {fmtDay(jet.latest_date)}</span></figcaption>
              {chart(jet, 'Jet fuel', 'gal', C.navy)}
            </figure>
            <figure className="figure">
              <figcaption><b>Brent crude</b><span>US dollars per barrel · {pct(b.m1)} on the month · latest {fmtDay(brent.latest_date)}</span></figcaption>
              {chart(brent, 'Brent crude', 'bbl', C.deep)}
            </figure>
          </div>
          <p className="fine drv-foot">Fuel is shown as context. It is not an input of the monthly outlook. Fuel prices are in dollars; the air-freight index is not. <Link to="/market/weekly">Weekly fuel-cost outlook</Link> · <Link to="/data#sources">Sources</Link></p>
        </section>
      </div>
    </>
  )
}
