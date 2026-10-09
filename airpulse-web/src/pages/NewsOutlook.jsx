import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useNews } from '../lib/data.js'
import { DIR, fmtDay, fmtTime, num, prob, share } from '../lib/format.js'
import { Dir, Empty, Loading, Next, PageHead, Section, Tag } from '../components/bits.jsx'
import { ProbBars } from '../components/charts.jsx'

const MONTH = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
const monthOf = (p) => `${MONTH[+p.slice(5, 7) - 1]} ${p.slice(0, 4)}`
const SOURCE = { aircargoweek: 'Air Cargo Week', splash247: 'Splash247' }
const pts = (v) => `${v > 0 ? '+' : v < 0 ? '−' : ''}${num(Math.abs(v), 1)} pts`
/** "AIR_CAPACITY_REDUCTION" -> "Air capacity reduction". The words are the parser's own event names. */
const kind = (t) => { const s = t.toLowerCase().replace(/_/g, ' '); return s[0].toUpperCase() + s.slice(1) }
const push = (d) => (d > 0 ? 'Upward pressure on prices' : d < 0 ? 'Downward pressure on prices' : 'No stated direction')
/** Places and organisations as the parser names them, made readable; a two-letter code stays a code. */
const nice = (s) => (/^[A-Z]{2,3}$/.test(s) ? s : s.replace(/_/g, ' ').toLowerCase().replace(/\w/g, (c) => c.toUpperCase()))
const named = (e) => [...new Map([...e.places, ...e.organisations].map((s) => [nice(s).toLowerCase(), nice(s)])).values()].join(', ')
const STATUS = { ACTIVE: 'reported as happening', POTENTIAL: 'reported as possible', ENDED: 'reported as ended' }

export default function NewsOutlook() {
  const n = useNews()
  const [all, setAll] = useState(false)
  if (!n) return <Loading what="the news-adjusted outlook" />
  if (!n.available) {
    return (
      <div className="page narrow">
        <PageHead kicker="Market · News-adjusted" title="News-adjusted outlook" lede="A trial view of how recent press reports would shift the monthly outlook." />
        <Empty title="Not offered">{n.reason}</Empty>
        <nav className="next-row" aria-label="Continue"><Next to="/market/forecast" title="Monthly outlook" note="The official outlook and its record" /></nav>
      </div>
    )
  }
  const t = n.test, sea = t.seasonal, t1 = t.with_news
  const moved = [...n.by_group].filter((g) => g.value != null).sort((a, b) => Math.abs(b.shift_points.up) + Math.abs(b.shift_points.down) - Math.abs(a.shift_points.up) - Math.abs(a.shift_points.down))
  const hist = [...n.history].reverse().filter((r) => r.a)
  const shown = all ? hist : hist.slice(0, 12)
  const same = n.baseline.p === n.adjusted.p

  return (
    <div className="page">
      <PageHead kicker="Market · News-adjusted" title="What recent news would do to the outlook"
        lede="The official outlook comes from the seasonal record. This page adds a trained model that reads recent press reports and shifts those probabilities.">
        <Tag>Experiment</Tag>
      </PageHead>

      <p className="wk-not">
        <b>This is a trial, not the AirPulse outlook.</b> In its test over {t.months} months the news-adjusted model did not improve on the seasonal outlook: it was right in {t1.correct} months against {sea.correct},
        and it was far more sure of itself than its results justified. It is shown so that the effect of news can be seen, with its record beside it. The official outlook is on the <Link to="/market/forecast">Monthly outlook</Link> page.
      </p>

      <div className="fc-top">
        <div className="fc-call">
          <p className="eyebrow">Official outlook · seasonal record · {monthOf(n.target_period)}</p>
          <p className={`call-word ${DIR[n.baseline.p].cls}`}><i aria-hidden="true">{DIR[n.baseline.p].glyph}</i>{DIR[n.baseline.p].word}</p>
          <ProbBars f={n.baseline} big />
          <p className="fine">Issued {fmtDay(n.issuance_date)}. It does not change when news arrives.</p>
        </div>
        <div className="fc-call">
          <p className="eyebrow">With recent news · on trial · {monthOf(n.target_period)}</p>
          <p className={`call-word ${DIR[n.adjusted.p].cls}`}><i aria-hidden="true">{DIR[n.adjusted.p].glyph}</i>{DIR[n.adjusted.p].word}</p>
          <ProbBars f={n.adjusted} big />
          <p className="fine">
            From {num(n.articles_in_window, 0)} articles of the last {n.model.window_days} days, read {fmtTime(n.as_of)}.{' '}
            {same ? 'News does not change the direction.' : `News moves the call from ${DIR[n.baseline.p].word} to ${DIR[n.adjusted.p].word}.`}
          </p>
        </div>
      </div>

      <Section title="The shift" id="shift" aside="Probability points added to or taken from each direction by the news of the last 30 days.">
        <dl className="kv">
          <div><dt>Rising</dt><dd>{prob(n.baseline.u)} → {prob(n.adjusted.u)} <span>{pts(n.shift_points.up)}</span></dd></div>
          <div><dt>Stable</dt><dd>{prob(n.baseline.f)} → {prob(n.adjusted.f)} <span>{pts(n.shift_points.flat)}</span></dd></div>
          <div><dt>Falling</dt><dd>{prob(n.baseline.d)} → {prob(n.adjusted.d)} <span>{pts(n.shift_points.down)}</span></dd></div>
        </dl>
        <p className="fine">
          The model has often been too sure of itself: large shifts like this one are why it did no better than the seasonal outlook in testing. Read the direction of the shift, not its size.
        </p>
      </Section>

      <Section title="Which news moves it" id="groups" aside="Each line: the same calculation with that kind of news set to its usual level. The difference is what that kind of news contributes now.">
        <div className="tbl-wrap">
          <table className="tbl">
            <thead><tr><th>Kind of news</th><th className="r">Level now</th><th className="r">Usual level</th><th className="r">Rising</th><th className="r">Stable</th><th className="r">Falling</th></tr></thead>
            <tbody>
              {moved.map((g) => (
                <tr key={g.group}>
                  <td>{g.label}</td><td className="r">{num(g.value, 2)}</td><td className="r">{num(g.usual, 2)}</td>
                  <td className="r">{pts(g.shift_points.up)}</td><td className="r">{pts(g.shift_points.flat)}</td><td className="r">{pts(g.shift_points.down)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="fine">A level is the weighted number of reports of that kind per 100 articles, signed where the reports state a direction.</p>
      </Section>

      <Section title="What the press reported" id="reports" aside={`${n.reports_in_window} reports in the last ${n.model.window_days} days. Each line says what kind of event an article reported and links to it. The text of the article is not shown.`}>
        <div className="tbl-wrap">
          <table className="tbl wrap">
            <thead><tr><th>Last reported</th><th>What was reported</th><th>Where, who</th><th>Reading</th><th>Source</th></tr></thead>
            <tbody>
              {n.reports.slice(0, 40).map((e, i) => (
                <tr key={`${e.url}${i}`}>
                  <td>{fmtDay(e.last)}</td>
                  <td>{kind(e.type)} <span className="dim">· {STATUS[e.status] ?? e.status.toLowerCase()}{e.n > 1 ? ` · ${e.n} articles` : ''}</span></td>
                  <td>{named(e) || '—'}</td>
                  <td>{push(e.direction)}</td>
                  <td><a href={e.url} rel="noopener noreferrer nofollow" target="_blank">{SOURCE[e.source] ?? e.source}</a></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="fine">
          Articles are read by a fixed set of rules that recognise kinds of events. The rules miss many events and sometimes misread one; they were checked only against a reference annotation, not by people.
        </p>
      </Section>

      <Section title="How it did in testing" id="test" aside={`${t.months} months, ${t.first} to ${t.last}. For each month the model saw only the reports and the outcomes that existed before that month's outlook was issued.`}>
        <div className="tbl-wrap">
          <table className="tbl">
            <thead><tr><th>Version</th><th className="r">Months</th><th className="r">Correct</th><th className="r">Share correct</th><th className="r">How sure it was</th></tr></thead>
            <tbody>
              <tr><td>Seasonal outlook (official)</td><td className="r">{sea.n}</td><td className="r">{sea.correct}</td><td className="r">{share(sea.correct, sea.n)}</td><td className="r">{prob(sea.sure)}</td></tr>
              <tr><td>With news (this page)</td><td className="r">{t1.n}</td><td className="r">{t1.correct}</td><td className="r">{share(t1.correct, t1.n)}</td><td className="r">{prob(t1.sure)}</td></tr>
            </tbody>
          </table>
        </div>
        <p className="fine">
          “How sure it was” is the probability it gave, on average, to the direction it named. A version is reliable when that figure and its share correct are close: the seasonal outlook is, the version with news is not.
          News changed the call in {t.call_changed_months} months: right where the seasonal outlook was wrong in {t.news_right_seasonal_wrong}, wrong where it was right in {t.seasonal_right_news_wrong}.
          By the rule fixed before the test, news {t.adds_value ? 'adds' : 'does not add'} value. The model was trained on {n.model.trained_on_months} months ({n.model.trained_from} to {n.model.trained_to}).
        </p>
        <div className="tbl-wrap">
          <table className="tbl">
            <thead><tr><th>Month</th><th>Seasonal</th><th>With news</th><th>Outcome</th><th>Seasonal</th><th>With news</th></tr></thead>
            <tbody>
              {shown.map((r) => (
                <tr key={r.m}>
                  <td>{monthOf(r.m)}</td><td><Dir d={r.sea.p} /></td><td><Dir d={r.t1.p} /></td><td><Dir d={r.a} /></td>
                  <td>{r.sea.p === r.a ? 'Correct' : 'Missed'}</td><td>{r.t1.p === r.a ? 'Correct' : 'Missed'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!all && hist.length > shown.length && <button type="button" className="more" onClick={() => setAll(true)}>Show all {hist.length} months</button>}
      </Section>

      <nav className="next-row" aria-label="Continue">
        <Next to="/market/forecast" title="Monthly outlook" note="The official outlook and its full record" />
        <Next to="/methodology" title="Methodology" note="How the outlook is formed and tested" />
        <Next to="/data" title="Data" note="Sources, freshness and terms" />
      </nav>
    </div>
  )
}
