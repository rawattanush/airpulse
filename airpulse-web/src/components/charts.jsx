import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { fmtMonth, prob, dirWord } from '../lib/format.js'

export const C = { navy: '#102A43', deep: '#123B5D', yellow: '#FFC928', sky: '#6FAED6', grey: '#9FB3C8', rule: '#D9E2EC', faint: '#E8EEF3', ink3: '#627D98', amber: '#B7791F' }
export const DIRC = { UP: C.yellow, FLAT: C.grey, DOWN: C.sky }

function useWidth() {
  const ref = useRef(null)
  const [w, setW] = useState(0)
  useEffect(() => {
    if (!ref.current) return
    const ro = new ResizeObserver(([e]) => setW(Math.floor(e.contentRect.width)))
    ro.observe(ref.current)
    return () => ro.disconnect()
  }, [])
  return [ref, w]
}

function niceTicks(lo, hi, n = 4) {
  if (lo === hi) { lo -= 1; hi += 1 }
  const raw = (hi - lo) / n, mag = 10 ** Math.floor(Math.log10(raw)), f = raw / mag
  const step = (f < 1.5 ? 1 : f < 3 ? 2 : f < 7 ? 5 : 10) * mag
  const a = Math.floor(lo / step) * step, b = Math.ceil(hi / step) * step, out = []
  for (let v = a; v <= b + step / 2; v += step) out.push(+v.toFixed(10))
  return out
}

/* A time chart over a shared row index. series: [{key, name, color, dash, width, type: 'line' | 'bar' | 'area'}]
   marks: vertical annotations [{i, label}]; dots: annotated points [{i, key, label, fill}]; bands: shaded x ranges [{from, to, label}] */
export function TimeChart({ rows, series, xKey = 'm', xFmt = fmtMonth, xTick, yFmt = (v) => v, tipFmt, height = 300, marks = [], dots = [], bands = [], zero = false, yDomain, label, tickEvery, ticks = 4 }) {
  const [ref, w] = useWidth()
  const [hover, setHover] = useState(null)
  const pad = { l: 46, r: 14, t: 18, b: 26 }
  const n = rows.length
  const geo = useMemo(() => {
    let lo = Infinity, hi = -Infinity
    for (const r of rows) for (const s of series) { const v = r[s.key]; if (v != null) { if (v < lo) lo = v; if (v > hi) hi = v } }
    if (!isFinite(lo)) { lo = 0; hi = 1 }
    if (zero || series.some((s) => s.type === 'bar')) { lo = Math.min(lo, 0); hi = Math.max(hi, 0) }
    if (yDomain) { lo = yDomain[0]; hi = yDomain[1] }
    const tk = niceTicks(lo, hi, ticks)
    return { ticks: tk, lo: tk[0], hi: tk[tk.length - 1] }
  }, [rows, series, zero, yDomain, ticks])
  const iw = Math.max(10, w - pad.l - pad.r), ih = height - pad.t - pad.b
  const x = (i) => pad.l + (n <= 1 ? iw / 2 : (i / (n - 1)) * iw)
  const y = (v) => pad.t + (1 - (v - geo.lo) / (geo.hi - geo.lo || 1)) * ih
  const path = (key) => {
    let d = '', pen = false
    rows.forEach((r, i) => { const v = r[key]; if (v == null) { pen = false; return } d += `${pen ? 'L' : 'M'}${x(i).toFixed(1)} ${y(v).toFixed(1)}`; pen = true })
    return d
  }
  const xt = useMemo(() => {
    if (tickEvery) return rows.map((r, i) => i).filter((i) => tickEvery(rows[i], i))
    const want = Math.max(2, Math.min(8, Math.floor(iw / 96))), out = []
    for (let k = 0; k < want; k++) out.push(Math.round((k / (want - 1)) * (n - 1)))
    return [...new Set(out)]
  }, [rows, iw, n, tickEvery])
  const move = (e) => {
    const box = e.currentTarget.getBoundingClientRect()
    const i = Math.round(((e.clientX - box.left - pad.l) / iw) * (n - 1))
    setHover(Math.max(0, Math.min(n - 1, i)))
  }
  const bw = Math.max(1, (iw / n) * 0.72)
  const hr = hover != null ? rows[hover] : null
  return (
    <div className="chart" ref={ref} style={{ height }}>
      {w > 0 && (
        <svg width={w} height={height} role="img" aria-label={label} onMouseMove={move} onMouseLeave={() => setHover(null)}>
          {bands.map((b, k) => (
            <g key={k}>
              <rect x={x(b.from)} y={pad.t} width={Math.max(0, x(b.to) - x(b.from))} height={ih} fill={C.sky} opacity="0.12" />
              {b.label && <text x={x(b.from) + 6} y={pad.t + 12} className="chart-note">{b.label}</text>}
            </g>
          ))}
          {geo.ticks.map((t) => (
            <g key={t}>
              <line x1={pad.l} x2={w - pad.r} y1={y(t)} y2={y(t)} stroke={t === 0 && geo.lo < 0 ? C.grey : C.faint} />
              <text x={pad.l - 8} y={y(t) + 4} textAnchor="end" className="chart-tick">{yFmt(t)}</text>
            </g>
          ))}
          {xt.map((i) => (
            <text key={i} x={x(i)} y={height - 6} textAnchor={i === 0 ? 'start' : i === n - 1 ? 'end' : 'middle'} className="chart-tick">{(xTick || xFmt)(rows[i][xKey])}</text>
          ))}
          {series.filter((s) => s.type === 'bar').map((s) => rows.map((r, i) => r[s.key] == null ? null : (
            <rect key={s.key + i} x={x(i) - bw / 2} width={bw} y={Math.min(y(0), y(r[s.key]))} height={Math.max(0.5, Math.abs(y(r[s.key]) - y(0)))}
              fill={s.colorNeg && r[s.key] < 0 ? s.colorNeg : s.color} opacity={hover == null || hover === i ? 1 : 0.55} />
          )))}
          {series.filter((s) => s.type === 'area').map((s) => (
            <path key={s.key} d={`${path(s.key)}L${x(n - 1)} ${y(geo.lo)}L${x(0)} ${y(geo.lo)}Z`} fill={s.color} opacity="0.1" />
          ))}
          {series.filter((s) => s.type === 'line').map((s) => (
            <path key={s.key} d={path(s.key)} fill="none" stroke={s.color} strokeWidth={s.width ?? 2} strokeDasharray={s.dash} strokeLinejoin="round" strokeLinecap="round" />
          ))}
          {marks.map((m, k) => (
            <g key={k}>
              <line x1={x(m.i)} x2={x(m.i)} y1={pad.t} y2={pad.t + ih} stroke={C.navy} strokeDasharray="2 4" />
              <text x={x(m.i) + (m.i > n * 0.8 ? -6 : 6)} y={pad.t + 10} textAnchor={m.i > n * 0.8 ? 'end' : 'start'} className="chart-note">{m.label}</text>
            </g>
          ))}
          {placeDots(dots, rows, x, y, n, w).map((d, k) => (
            <g key={k}>
              <circle cx={d.cx} cy={d.cy} r="5" fill={d.fill ?? C.yellow} stroke={C.navy} strokeWidth="2" />
              {d.show && <text x={d.tx} y={d.ty} textAnchor={d.anchor} className="chart-note strong">{d.label}</text>}
            </g>
          ))}
          {hr && (
            <g pointerEvents="none">
              <line x1={x(hover)} x2={x(hover)} y1={pad.t} y2={pad.t + ih} stroke={C.navy} opacity="0.35" />
              {series.filter((s) => s.type === 'line' && hr[s.key] != null).map((s) => <circle key={s.key} cx={x(hover)} cy={y(hr[s.key])} r="3.5" fill="#fff" stroke={s.color} strokeWidth="2" />)}
            </g>
          )}
        </svg>
      )}
      {hr && (
        <div className="tip" style={{ left: Math.min(Math.max(x(hover), 90), w - 90), top: 0 }}>
          <b>{xFmt(hr[xKey])}</b>
          {series.filter((s) => s.type !== "area").map((s) => hr[s.key] == null ? null : <span key={s.key}><i style={{ background: s.color }} />{s.name} <em>{(tipFmt || yFmt)(hr[s.key], s.key, hr)}</em></span>)}
          {hr.note && <span className="tip-note">{hr.note}</span>}
        </div>
      )}
    </div>
  )
}

/* Where each annotated point and its label go. A label that would run into one already placed, or off the chart, is left out. */
function placeDots(dots, rows, x, y, n, w) {
  const placed = []
  return dots.filter((d) => rows[d.i]?.[d.key] != null).map((d) => {
    const cx = x(d.i), cy = y(rows[d.i][d.key])
    if (!d.label) return { ...d, cx, cy, show: false }
    const width = d.label.length * 6.9 + 6
    const centred = d.centre && cx - width / 2 > 40 && cx + width / 2 < w - 4
    const end = !centred && d.i > n * 0.75
    const tx = centred ? cx : cx + (end ? -10 : 10), ty = cy + (d.below ? 21 : -13)
    const x0 = centred ? tx - width / 2 : end ? tx - width : tx, box = { x0, x1: x0 + width, y0: ty - 11, y1: ty + 3 }
    const clash = placed.some((b) => box.x0 < b.x1 && box.x1 > b.x0 && box.y0 < b.y1 && box.y1 > b.y0)
    if (!clash) placed.push(box)
    return { ...d, cx, cy, tx, ty, anchor: centred ? 'middle' : end ? 'end' : 'start', show: !clash }
  })
}

export function Legend({ items }) {
  return (
    <div className="legend">
      {items.map((it) => (
        <span key={it.name}><i className={it.shape ?? 'line'} style={it.shape === 'dash' ? { borderTopColor: it.color } : it.shape === 'ring' ? { borderColor: it.color } : { background: it.color }} />{it.name}</span>
      ))}
    </div>
  )
}

export function Spark({ values, width = 120, height = 30, color = C.navy }) {
  const lo = Math.min(...values), hi = Math.max(...values)
  const d = values.map((v, i) => `${i ? 'L' : 'M'}${((i / (values.length - 1)) * (width - 6) + 1).toFixed(1)} ${(height - 4 - ((v - lo) / (hi - lo || 1)) * (height - 8)).toFixed(1)}`).join('')
  const ly = height - 4 - ((values[values.length - 1] - lo) / (hi - lo || 1)) * (height - 8)
  return (
    <svg width={width} height={height} aria-hidden="true">
      <path d={d} fill="none" stroke={color} strokeWidth="1.5" />
      <circle cx={width - 5} cy={ly} r="2.5" fill={C.yellow} stroke={C.navy} strokeWidth="1.2" />
    </svg>
  )
}

/* The outlook's three probabilities as horizontal bars. The direction AirPulse calls is marked. */
export function ProbBars({ f, big = false }) {
  const items = [['UP', f.u], ['FLAT', f.f], ['DOWN', f.d]]
  return (
    <div className={`probbars${big ? ' big' : ''}`}>
      {items.map(([k, v]) => (
        <div key={k} className={k === f.p ? 'call' : ''}>
          <span className="pb-name">{dirWord(k)}</span>
          <span className="pb-track"><span style={{ width: `${(v ?? 0) * 100}%`, background: DIRC[k] }} /></span>
          <span className="pb-val">{prob(v)}</span>
        </div>
      ))}
    </div>
  )
}

/* Forecast probabilities for every month as stacked columns, with the outcome under each column. */
export function ProbTimeline({ items, height = 220 }) {
  const [ref, w] = useWidth()
  const [hover, setHover] = useState(null)
  const pad = { l: 46, r: 14, t: 10, b: 44 }
  const n = items.length, iw = Math.max(10, w - pad.l - pad.r), ih = height - pad.t - pad.b
  const cw = iw / n
  const h = hover != null ? items[hover] : null
  return (
    <div className="chart" ref={ref} style={{ height }}>
      {w > 0 && (
        <svg width={w} height={height} role="img" aria-label="Outlook probabilities by month, with the published outcome beneath"
          onMouseMove={(e) => { const b = e.currentTarget.getBoundingClientRect(); setHover(Math.max(0, Math.min(n - 1, Math.floor((e.clientX - b.left - pad.l) / cw)))) }} onMouseLeave={() => setHover(null)}>
          {[0, 0.5, 1].map((t) => <text key={t} x={pad.l - 8} y={pad.t + (1 - t) * ih + 4} textAnchor="end" className="chart-tick">{t * 100}%</text>)}
          {items.map((f, i) => {
            if (f.d == null) return null
            const x0 = pad.l + i * cw, ww = Math.max(1, cw - 1), o = hover == null || hover === i ? 1 : 0.5
            const hd = f.d * ih, hf = f.f * ih, hu = f.u * ih
            return (
              <g key={f.t} opacity={o}>
                <rect x={x0} y={pad.t} width={ww} height={hu} fill={DIRC.UP} />
                <rect x={x0} y={pad.t + hu} width={ww} height={hf} fill={DIRC.FLAT} />
                <rect x={x0} y={pad.t + hu + hf} width={ww} height={hd} fill={DIRC.DOWN} />
                <rect x={x0} y={pad.t + ih + 6} width={ww} height="8" fill={f.c === 1 ? C.navy : f.c === 0 ? '#fff' : C.faint} stroke={f.c === 0 ? C.navy : 'none'} strokeWidth="1" />
              </g>
            )
          })}
          <line x1={pad.l} x2={w - pad.r} y1={pad.t + ih / 3} y2={pad.t + ih / 3} stroke="#fff" strokeDasharray="2 3" opacity="0.7" />
          <line x1={pad.l} x2={w - pad.r} y1={pad.t + (2 * ih) / 3} y2={pad.t + (2 * ih) / 3} stroke="#fff" strokeDasharray="2 3" opacity="0.7" />
          {items.map((f, i) => f.t.endsWith('-01') && (n < 60 || +f.t.slice(0, 4) % 2 === 0) ? <text key={f.t} x={pad.l + i * cw} y={height - 6} className="chart-tick">{f.t.slice(0, 4)}</text> : null)}
        </svg>
      )}
      {h && (
        <div className="tip" style={{ left: Math.min(Math.max(pad.l + (hover + 0.5) * cw, 100), w - 100), top: 0 }}>
          <b>{fmtMonth(h.t)}</b>
          <span><i style={{ background: DIRC.UP }} />Rising <em>{prob(h.u)}</em></span>
          <span><i style={{ background: DIRC.FLAT }} />Stable <em>{prob(h.f)}</em></span>
          <span><i style={{ background: DIRC.DOWN }} />Falling <em>{prob(h.d)}</em></span>
          <span className="tip-note">Outlook {dirWord(h.p)} · outcome {h.a ? dirWord(h.a) : 'pending'}</span>
        </div>
      )}
    </div>
  )
}

/* One square per forecast month, grouped by year: filled = called correctly, hollow = missed, hatched = outcome pending. */
export function OutcomeStrip({ items, to, current }) {
  const years = {}
  for (const f of items) (years[f.t.slice(0, 4)] ??= []).push(f)
  return (
    <div className="strip">
      {Object.entries(years).map(([yr, fs]) => (
        <div key={yr} className="strip-year">
          <span className="strip-label">{yr}</span>
          <div>
            {fs.map((f) => {
              const cls = `sq ${f.c === 1 ? 'hit' : f.c === 0 ? 'miss' : 'pend'}${current === f.t ? ' cur' : ''}`
              const title = `${fmtMonth(f.t)}: outlook ${dirWord(f.p)}, ${f.a ? `outcome ${dirWord(f.a)}` : 'outcome pending'}`
              return to ? <Link key={f.t} to={to(f.t)} className={cls} title={title} aria-label={title} /> : <span key={f.t} className={cls} title={title} />
            })}
          </div>
        </div>
      ))}
    </div>
  )
}

/* Calendar grid: one row per year, one column per calendar month, coloured by the direction of the month's change. */
export function SeasonGrid({ rows }) {
  const years = {}
  for (const r of rows) (years[r.m.slice(0, 4)] ??= {})[+r.m.slice(5, 7)] = r
  const M = ['J', 'F', 'M', 'A', 'M', 'J', 'J', 'A', 'S', 'O', 'N', 'D']
  return (
    <div className="season" role="img" aria-label="Direction of the monthly change by year and calendar month">
      <div className="season-row head"><span />{M.map((m, i) => <span key={i}>{m}</span>)}</div>
      {Object.entries(years).map(([yr, ms]) => (
        <div className="season-row" key={yr}>
          <span>{yr}</span>
          {M.map((_, i) => {
            const r = ms[i + 1]
            return <i key={i} className={r?.dir ? `d-${r.dir.toLowerCase()}` : 'd-none'} title={r ? `${fmtMonth(r.m)}: ${r.mom == null ? 'no change published' : `${r.mom > 0 ? '+' : ''}${r.mom.toFixed(1)}%`}` : ''} />
          })}
        </div>
      ))}
    </div>
  )
}

/* Share of directions per group as one stacked horizontal bar per row. */
export function ShareBars({ rows }) {
  return (
    <div className="share">
      {rows.map((r) => {
        const t = r.up + r.flat + r.down || 1
        return (
          <div key={r.label} className="share-row" title={`${r.label}: rising ${r.up}, stable ${r.flat}, falling ${r.down}`}>
            <span>{r.label}</span>
            <div>
              <i style={{ width: `${(r.down / t) * 100}%`, background: DIRC.DOWN }} />
              <i style={{ width: `${(r.flat / t) * 100}%`, background: DIRC.FLAT }} />
              <i style={{ width: `${(r.up / t) * 100}%`, background: DIRC.UP }} />
            </div>
            <em>{Math.round((r.up / t) * 100)}% rising</em>
          </div>
        )
      })}
    </div>
  )
}
