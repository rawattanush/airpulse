import { Link } from 'react-router-dom'
import photos from '../lib/photos.json'
import { DIR, fmtDay, monthOnly, num, pct } from '../lib/format.js'
import { exportState, needsAttention } from '../lib/derive.js'

// A file of public/ addressed under the path the site is served from (the root, or a sub-path such as /airpulse/ on GitHub Pages).
export const asset = (p) => `${import.meta.env.BASE_URL}${p}`

// The brand lock-up, cut from the brand kit (public/brand). It is drawn for dark grounds.
export function Logo({ height = 40 }) {
  return <img className="logo" src={asset('brand/logo-light.png')} alt="AirPulse — Air Freight Intelligence" height={height} width={Math.round(height * 426 / 122)} />
}

export const Arrow = () => (
  <svg className="arrow" width="18" height="12" viewBox="0 0 18 12" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path d="M0 6h16M11 1l5 5-5 5" /></svg>
)

/** A photograph: WebP in the width the layout needs, JPEG as the fallback. Below-the-fold photographs load lazily. */
export function Photo({ name, alt = '', sizes = '100vw', eager = false, className, focus }) {
  const p = photos[name]
  const srcSet = p.widths.map((w) => `${asset(`img/${name}-${w}.webp`)} ${w}w`).join(', ')
  return (
    <picture className={className}>
      <source type="image/webp" srcSet={srcSet} sizes={sizes} />
      <img src={asset(p.fallback)} alt={alt} width={p.width} height={p.height} loading={eager ? 'eager' : 'lazy'} fetchPriority={eager ? 'high' : undefined} decoding="async" style={focus ? { objectPosition: focus } : undefined} />
    </picture>
  )
}

export function Loading({ what = 'the market record' }) {
  return <div className="loading" role="status" aria-live="polite"><span />Loading {what}…</div>
}

export function Empty({ title, children }) {
  return <div className="empty" role="status"><p className="empty-title">{title}</p>{children && <p>{children}</p>}</div>
}

/** Typographic page head. Pages that open on a photograph use Banner instead. */
export function PageHead({ kicker, title, lede, children }) {
  return (
    <header className="head">
      <div className="head-text">
        {kicker && <p className="eyebrow">{kicker}</p>}
        <h1>{title}</h1>
        {lede && <p className="lede">{lede}</p>}
      </div>
      {children && <div className="head-tools">{children}</div>}
    </header>
  )
}

/** Image-led page head. The photograph is the ground; a navy wash keeps the title readable. */
export function Banner({ photo, alt, kicker, title, lede, focus, tall = false, children }) {
  return (
    <header className={`banner${tall ? ' tall' : ''}`}>
      <Photo name={photo} alt={alt} eager focus={focus} sizes="100vw" />
      <div className="banner-in">
        {kicker && <p className="eyebrow">{kicker}</p>}
        <h1>{title}</h1>
        {lede && <p className="lede">{lede}</p>}
        {children}
      </div>
    </header>
  )
}

export function Section({ title, aside, children, id, className = '' }) {
  return (
    <section className={`section ${className}`} id={id} aria-labelledby={id ? `${id}-h` : undefined}>
      <div className="section-head">
        <h2 id={id ? `${id}-h` : undefined}>{title}</h2>
        {aside && <p>{aside}</p>}
      </div>
      {children}
    </section>
  )
}

export const Tag = ({ children, tone = '' }) => <span className={`tag ${tone}`}>{children}</span>

/** A direction in customer words, with its arrow. */
export function Dir({ d }) {
  if (!d) return <span className="dir none">—</span>
  return <span className={`dir ${DIR[d].cls}`}><i aria-hidden="true">{DIR[d].glyph}</i>{DIR[d].word}</span>
}

export function Seg({ value, onChange, options, label }) {
  return (
    <div className="seg" role="group" aria-label={label}>
      {options.map((o) => (
        <button key={o.value} type="button" aria-pressed={value === o.value} onClick={() => onChange(o.value)}>{o.label}</button>
      ))}
    </div>
  )
}

/** The index is a level, not a price. This note travels with every place the level is shown large. */
export function IndexNote({ last, open = false }) {
  return (
    <details className="disclosure" open={open}>
      <summary>What is an index?</summary>
      <div>
        <p>An index tracks how freight-price levels change over time. The number is a level relative to a base period, published each month by the US Bureau of Labor Statistics from prices that carriers report.</p>
        <p>
          <b>It is not a dollar-per-kilogram freight quote.</b> A level of {num(last.v)} is not an amount of money in any currency. What it tells you is the movement
          {last.mom != null ? <>: the index moved {pct(last.mom)} in {monthOnly(last.m)}, so air-freight price levels on this lane moved by about that much on average.</> : '.'}
        </p>
      </div>
    </details>
  )
}

export function Next({ to, title, note }) {
  return (
    <Link to={to} className="next">
      <span><b>{title}</b>{note && <em>{note}</em>}</span>
      <Arrow />
    </Link>
  )
}

export function Field({ label, hint, children, id }) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {children}
      {hint && <p className="field-hint" id={`${id}-hint`}>{hint}</p>}
    </div>
  )
}

/** Shown above an outlook when a source it depends on has failed or is stale. Nothing is shown when every production source is healthy. */
export function SourceAlert({ core }) {
  const bad = needsAttention(core), ex = exportState(core)
  if (!bad.length && !ex.stale) return null
  return (
    <p className="src-alert" role="status">
      {ex.stale && <><b>Data delay.</b> These pages were last updated {ex.days == null ? 'at an unknown time' : `${Math.floor(ex.days)} days ago`}; an update is expected at least every {ex.limit} days. </>}
      {bad.length > 0 && <><b>{bad.length} {bad.length === 1 ? 'data source needs' : 'data sources need'} attention.</b> {bad.map((x) => `${x.name}: ${x.status.toLowerCase()}`).join('; ')}. </>}
      What is shown here may be out of date. <Link to="/data#sources">Data state</Link>
    </p>
  )
}
