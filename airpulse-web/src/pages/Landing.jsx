import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { useOutlook } from '../lib/data.js'
import { outlookView } from '../lib/derive.js'
import { DIR, fmtMonthLong, prob } from '../lib/format.js'
import { Arrow, Logo, Photo } from '../components/bits.jsx'

// One line of the real product inside the hero: the current outlook, read from the engine's export.
function Now() {
  const o = useOutlook()
  if (!o) return <div className="hero-now" aria-hidden="true" />
  const f = o.forecasts.at(-1), v = outlookView(f)
  return (
    <Link to="/dashboard" className="hero-now">
      <span className="eyebrow">AirPulse outlook · {fmtMonthLong(f.t)}</span>
      <b>{DIR[v.dir].glyph} {DIR[v.dir].word}</b>
      <span>{prob(v.p)} outlook probability{v.closeCall ? ' · a close call' : ''}</span>
      <span className="hero-now-lane">Asia → US market proxy</span>
      <span className="hero-now-go">Open the briefing <Arrow /></span>
    </Link>
  )
}

export default function Landing() {
  useEffect(() => { document.title = 'AirPulse — Air freight intelligence' }, [])
  return (
    <div className="land">
      <header className="hero">
        <Photo name="aircraft" alt="Wide-body freighter climbing above a cloud deck at sunrise" eager sizes="100vw" focus="70% 40%" />
        <div className="hero-shade" />
        <nav className="hero-nav" aria-label="Primary">
          <Link to="/" aria-label="AirPulse home"><Logo height={44} /></Link>
          <div>
            <a href="#how">How it works</a>
            <Link to="/methodology">Methodology</Link>
            <Link to="/dashboard" className="hero-nav-cta">Open AirPulse</Link>
          </div>
        </nav>
        <div className="hero-body">
          <p className="hero-eyebrow"><i />Air freight intelligence</p>
          <h1>Know where <span>air-freight</span> markets are heading.</h1>
          <p className="hero-copy">AirPulse follows the published air-freight price index, fuel prices and official flight counts, and states one monthly outlook with its full record.</p>
          <div className="hero-cta">
            <Link to="/dashboard" className="btn">Explore AirPulse <Arrow /></Link>
            <a href="#how" className="hero-second">How it works</a>
          </div>
        </div>
        <Now />
      </header>

      <section className="land-how" id="how" aria-labelledby="how-h">
        <p className="eyebrow">How it works</p>
        <h2 id="how-h">One outlook a month, and the record behind it.</h2>
        <ol>
          <li><span>01</span><div><h3>It reads what is published</h3><p>An official air-freight price index with every revision, daily jet-fuel and crude prices, and official counts of flights. Each value is kept with the date it became public.</p></div></li>
          <li><span>02</span><div><h3>It states one outlook</h3><p>Rising, stable or falling for the month ahead, with a probability. One result, not a choice between models.</p></div></li>
          <li><span>03</span><div><h3>It keeps the record</h3><p>Every outlook is checked against what was later published. Any past month can be replayed to see exactly what was known.</p></div></li>
        </ol>
      </section>

      <section className="land-scope" aria-labelledby="scope-h">
        <h2 id="scope-h" className="eyebrow">Built on what it can support</h2>
        <div>
          <p className="land-scope-is"><b>What AirPulse tells you.</b> The direction of the monthly BLS Asia → US air-freight price index: a public measure of the market, used as a proxy.</p>
          <p className="land-scope-not"><b>What it does not.</b> Carrier quotes, route-level prices per kilogram, or South Asia → Europe rates. Where a number does not exist, AirPulse says so.</p>
        </div>
        <Link to="/dashboard" className="text-link">Explore AirPulse <Arrow /></Link>
      </section>

      <footer className="land-foot">
        <Logo height={30} />
        <p>The forecast target is the BLS Asia → US air-freight price index, a public market proxy. It is not a quoted freight rate.</p>
        <nav aria-label="Footer"><Link to="/methodology">Methodology</Link><Link to="/data">Data</Link></nav>
      </footer>
    </div>
  )
}
