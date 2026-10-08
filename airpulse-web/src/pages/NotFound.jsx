import { Link, useLocation } from 'react-router-dom'
import { Arrow } from '../components/bits.jsx'
import { NAV } from '../components/Shell.jsx'

export default function NotFound() {
  const loc = useLocation()
  return (
    <div className="page narrow nf">
      <p className="eyebrow">Page not found</p>
      <h1>There is no page at this address.</h1>
      <p className="lede"><code>{loc.pathname}</code> is not part of AirPulse. These are:</p>
      <ul>{NAV.map((g) => <li key={g.to}><Link to={g.to}>{g.label}<Arrow /></Link></li>)}</ul>
    </div>
  )
}
