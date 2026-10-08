import { Component, useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { useCore } from '../lib/data.js'
import { fmtDay, fmtMonth } from '../lib/format.js'
import { needsAttention } from '../lib/derive.js'
import { Loading, Logo } from './bits.jsx'

// Five destinations. A destination with more than one page shows its pages in a second row.
export const NAV = [
  { label: 'Overview', to: '/dashboard', under: ['/dashboard'] },
  { label: 'Market', to: '/market', under: ['/market'], items: [{ to: '/market', label: 'Market', end: true }, { to: '/market/forecast', label: 'Monthly outlook' }, { to: '/market/trends', label: 'Trends' }, { to: '/market/history', label: 'History' }, { to: '/market/fuel', label: 'Fuel prices' }] },
  { label: 'Operations', to: '/operations', under: ['/operations', '/routes', '/replay', '/estimate'], items: [{ to: '/operations', label: 'Air traffic' }, { to: '/routes', label: 'Lanes' }, { to: '/replay', label: 'Replay' }, { to: '/estimate', label: 'Estimate' }] },
  { label: 'Research', to: '/methodology', under: ['/methodology', '/data'], items: [{ to: '/methodology', label: 'Methodology' }, { to: '/data', label: 'Data' }] },
]
const inGroup = (g, path) => g.under.some((u) => path === u || path.startsWith(`${u}/`))

class Boundary extends Component {
  state = { error: null }
  static getDerivedStateFromError(error) { return { error } }
  componentDidUpdate(prev) { if (prev.at !== this.props.at && this.state.error) this.setState({ error: null }) }
  render() {
    if (!this.state.error) return this.props.children
    return (
      <div className="page narrow" role="alert">
        <p className="eyebrow">Something went wrong</p>
        <h1>This page could not be shown.</h1>
        <p className="lede">{String(this.state.error.message || this.state.error)}</p>
        <p>The application reads data files exported from the AirPulse engine. If they are missing, run <code>scripts/export_data.py</code> and reload.</p>
        <p><button type="button" className="btn ghost" onClick={() => window.location.reload()}>Reload</button></p>
      </div>
    )
  }
}

const MODE = { SNAPSHOT: 'Snapshot data', AUTOMATED: 'Automated data', LIVE: 'Live data' }

export default function Shell() {
  const core = useCore()
  const loc = useLocation()
  const [open, setOpen] = useState(false)
  useEffect(() => { setOpen(false); window.scrollTo(0, 0) }, [loc.pathname])
  useEffect(() => {
    const esc = (e) => e.key === 'Escape' && setOpen(false)
    window.addEventListener('keydown', esc); return () => window.removeEventListener('keydown', esc)
  }, [])
  const group = NAV.find((g) => inGroup(g, loc.pathname))
  const lane = core?.lanes.find((l) => l.primary)
  const attention = needsAttention(core).length
  // Each route names itself in the browser tab, so a screen reader announces where a navigation has landed.
  const here = group?.items?.find((it) => (it.end ? loc.pathname === it.to : loc.pathname === it.to || loc.pathname.startsWith(`${it.to}/`)))?.label ?? group?.label
  useEffect(() => { document.title = here ? `${here} · AirPulse` : 'AirPulse — Air freight intelligence' }, [here])
  return (
    <div className="shell">
      <a className="skip" href="#content">Skip to content</a>
      <header className="top">
        <div className="top-in">
          <Link to="/" className="top-logo" aria-label="AirPulse home"><Logo height={34} /></Link>
          <nav className="top-nav" aria-label="Product">
            {NAV.map((g) => <NavLink key={g.to} to={g.to} className={() => (inGroup(g, loc.pathname) ? 'on' : '')} aria-current={inGroup(g, loc.pathname) ? 'true' : undefined}>{g.label}</NavLink>)}
          </nav>
          {core && (
            <Link to="/data" className="top-state" title="Data state and freshness">
              <i className={attention ? 'attention' : core.state.data_mode.toLowerCase()} aria-hidden="true" />
              <span>{MODE[core.state.data_mode]}</span>
              {attention > 0 && <b>{attention} {attention === 1 ? 'source needs' : 'sources need'} attention</b>}
              <em>Index through {fmtMonth(lane.latest_month)} · fuel through {fmtDay(core.fuel.jet.latest_date).slice(0, -5)}</em>
            </Link>
          )}
          <button type="button" className="top-menu" aria-expanded={open} aria-controls="drawer" onClick={() => setOpen(!open)}>{open ? 'Close' : 'Menu'}</button>
        </div>
        {group?.items && (
          <div className="sub">
            <nav className="sub-in" aria-label={group.label}>
              {group.items.map((it) => <NavLink key={it.to} to={it.to} end={it.end}>{it.label}</NavLink>)}
              <Link to="/methodology#proxy" className="sub-proxy">Asia → US · public market proxy</Link>
            </nav>
          </div>
        )}
        <nav id="drawer" className={`drawer${open ? ' open' : ''}`} aria-label="All pages" hidden={!open}>
          {NAV.map((g) => (
            <div key={g.to}>
              <p>{g.label}</p>
              {(g.items ?? [{ to: g.to, label: g.label }]).map((it) => <NavLink key={it.to} to={it.to} end={it.end}>{it.label}</NavLink>)}
            </div>
          ))}
          {core && <Link to="/data" className="drawer-state">{MODE[core.state.data_mode]}{attention > 0 ? ` · ${attention} ${attention === 1 ? 'source needs' : 'sources need'} attention` : ''} · index through {fmtMonth(lane.latest_month)} · fuel through {fmtDay(core.fuel.jet.latest_date)}</Link>}
        </nav>
      </header>
      <main id="content" tabIndex={-1}>
        <Boundary at={loc.pathname}>
          {core ? <Outlet context={core} /> : <Loading />}
        </Boundary>
      </main>
      <footer className="foot">
        <div className="foot-in">
          <Logo height={30} />
          <p>
            AirPulse forecasts the direction of one public market measure: the BLS Asia → US air-freight price index. It is a market proxy.
            It is not a carrier quote, not a route-level price, and not a South Asia → Europe series.
          </p>
          <nav aria-label="Footer">
            <Link to="/methodology">Methodology</Link>
            <Link to="/data">Data</Link>
            <Link to="/methodology#control-center">Control Center</Link>
          </nav>
        </div>
      </footer>
    </div>
  )
}
