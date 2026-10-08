import { Link, useOutletContext } from 'react-router-dom'
import { exportState, registryNow } from '../lib/derive.js'
import { fmtDay, fmtMonth, fmtTime, int } from '../lib/format.js'
import { PageHead, Section } from '../components/bits.jsx'

// Every figure and every state on this page is read from the export: the engine's source registry (state from its run
// records), its production policy (terms), its workflow files (schedules), its newest run record. The words below only name states.
const MODE = {
  SNAPSHOT: ['Snapshot', 'Every input comes from a data refresh that a person started. Nothing is fetched on a schedule.'],
  AUTOMATED: ['Automated', 'Every input was last fetched by a scheduled run, within its expected interval.'],
  LIVE: ['Live', 'Every input is checked at least hourly.'],
}
const LAYER = { core: 'Market and monthly outlook', weekly: 'Weekly fuel outlook', aviation: 'Air traffic' }
const STATUS = { HEALTHY: 'Healthy', DEGRADED: 'Degraded', STALE: 'Stale', FAILED: 'Failed', UNAVAILABLE: 'Unavailable' }
const TERMS = { 'COMMERCIAL-SAFE': 'Public domain', 'COMMERCIAL-SAFE-WITH-ATTRIBUTION': 'Free to use with attribution', 'COMMERCIAL-SAFE-WITH-LIMITS': 'Free to reuse by the publisher’s own statement' }
const DATASET = { benchmark_snapshot: 'Index and fuel snapshot of the evaluation', expansion_snapshot: 'Snapshot of the data of the later tests', weekly_fuel_vintages: 'Weekly fuel releases' }
const STARTED = { manual: 'By hand', 'manual-dispatch': 'By hand (hosted)', schedule: 'Scheduler', seed: 'Copied from the snapshot' }
const RUN = { OK: 'Completed', DEGRADED: 'Completed; a source was not healthy', FAILED: 'Failed its checks' }
const when = (s) => (!s ? '—' : s.length > 10 ? fmtTime(s) : s.length === 7 ? fmtMonth(s) : fmtDay(s))
const days = (n) => (n == null ? '—' : `${Number.isInteger(n) ? n : n.toFixed(1)} days`)
const yesNo = (b) => (b == null ? '—' : b ? 'Yes' : 'No')

/** What a reader should keep in mind. Each sentence takes its number or its state from the export, so it cannot fall behind the data. */
function limits(core, scheduledRuns) {
  const others = core.counts.lanes - core.counts.lanes_with_outlook
  return [
    scheduledRuns > 0
      ? ['Not real-time', `The data are as old as the last refresh shown above. ${int(scheduledRuns)} scheduled fetches are on record.`]
      : ['Snapshot, not real-time', 'The data are as old as the last refresh shown above. No scheduled fetch is on record: every refresh so far was started by a person.'],
    ['One validated market', `Only the validated index has an outlook. ${int(others)} other ${others === 1 ? 'index is' : 'indices are'} stored and shown without one.`],
    ['First releases are provisional', `The latest months can be revised by BLS in the following ${int(core.revision_releases)} releases.`],
    ['A gap is left as a gap', 'A month or a day a source did not publish is shown as missing. It is not interpolated and it is not zero.'],
    ['Fuel prices are corrected now and then', `Fuel is shown at its current values, with a publication delay of ${int(core.fuel_lag_days)} days. Each file read from the publisher is kept with its date.`],
    ['No weekly outlook', 'No public weekly air-freight rate series may be used, so there is no weekly freight outlook. The weekly fuel-cost outlook is not offered either: the reason is in the Methodology.'],
    ['No lane rates', 'AirPulse holds no carrier quotes and no rates per kilogram for any route.'],
  ]
}

export default function DataPage() {
  const core = useOutletContext()
  const s = core.state, [modeName, modeText] = MODE[s.data_mode] ?? MODE.SNAPSHOT
  const rows = registryNow(core), healthy = rows.filter((x) => x.status === 'HEALTHY').length
  const attention = rows.filter((x) => x.status !== 'HEALTHY'), ex = exportState(core), run = core.status
  const scheduledRuns = core.registry.summary.scheduled_runs, manualRuns = core.registry.summary.manual_runs
  return (
    <div className="page obs">
      <PageHead kicker="Research · Data" title="Data state" lede="Where the numbers come from, how fresh they are, and under what terms they are shown." />

      <div className="obs-top">
        <div className="obs-mode">
          <p className="eyebrow">Data mode</p>
          <p className={`obs-mode-word ${s.data_mode.toLowerCase()}`}><i aria-hidden="true" />{modeName}</p>
          <p>{modeText}</p>
          {s.not_live_statement && <p className="fine">{s.not_live_statement}</p>}
        </div>
        <dl className="obs-facts">
          <div><dt>Last data refresh</dt><dd>{fmtTime(s.latest_ingestion)}</dd><dd className="sub">{STARTED[s.latest_ingestion_trigger] ? `Started ${STARTED[s.latest_ingestion_trigger].toLowerCase()}` : '—'}</dd></div>
          <div><dt>Scheduled fetches on record</dt><dd>{int(scheduledRuns)}</dd><dd className="sub">{int(manualRuns)} started by hand</dd></div>
          <div><dt>Sources healthy</dt><dd>{healthy} of {rows.length}</dd><dd className="sub">worked out now, from the last fetch of each</dd></div>
          <div><dt>Run records</dt><dd>{s.records_intact ? 'Intact' : 'Check failed'}</dd><dd className="sub">append-only, verified</dd></div>
        </dl>
      </div>

      {ex.stale && (
        <p className="obs-stale" role="status"><b>Data delay.</b> These pages were last updated on {fmtTime(core.generated_at)}, {Math.floor(ex.days)} days ago. An update is expected at least every {ex.limit} days. Everything below is as it stood then.</p>
      )}
      {attention.length > 0 && (
        <p className="obs-stale" role="status"><b>{attention.length} {attention.length === 1 ? 'source needs' : 'sources need'} attention.</b> {attention.map((x) => `${x.name}: ${STATUS[x.status].toLowerCase()}`).join('; ')}. Figures that depend on them may be out of date.</p>
      )}

      {core.through && (
        <dl className="obs-through" aria-label="How far each kind of data runs">
          <div><dt>Air-freight index through</dt><dd>{fmtMonth(core.through.index)}</dd></div>
          <div><dt>Fuel prices through</dt><dd>{fmtDay(core.through.fuel)}</dd></div>
          {core.through.weekly_fuel_release && <div><dt>Newest weekly fuel release</dt><dd>{fmtDay(core.through.weekly_fuel_release)}</dd></div>}
        </dl>
      )}

      <Section title="Sources" id="sources" aside="Every source behind this site. For each: its state now, when it was last fetched and what started that, the newest data it holds, how often it is checked, when it counts as stale, and the terms under which it is shown. The state is worked out from the run records and today's date; nothing in this table is typed.">
        <div className="tbl-wrap">
          <table className="tbl obs-table">
            <thead><tr><th>Source</th><th>Used for</th><th>Status</th><th>Last success</th><th>Last attempt</th><th>Started</th><th>Newest data</th><th>Published</th><th>Checked every</th><th>Stale after</th><th>Terms</th></tr></thead>
            <tbody>
              {rows.map((x) => (
                <tr key={x.id}>
                  <td>{x.name}<span className="obs-why">{x.authority}</span></td>
                  <td className="dim">{LAYER[x.layer] ?? x.layer}</td>
                  <td><span className={`st ${x.status.toLowerCase()}`}><i aria-hidden="true" />{STATUS[x.status] ?? x.status}</span>{x.error && <span className="obs-why">{x.error}</span>}</td>
                  <td className="num">{when(x.last_success)}</td>
                  <td className="num">{when(x.last_attempt)}</td>
                  <td>{STARTED[x.last_trigger] ?? '—'}</td>
                  <td className="num">{when(x.latest_data)}</td>
                  <td className="dim">{x.frequency}</td>
                  <td className="dim num">{days(x.check_every_days)}</td>
                  <td className="dim num">{days(x.stale_after_days)}{x.data_stale_after_days != null && <span className="obs-why">data older than {days(x.data_stale_after_days)}</span>}</td>
                  <td className="dim">{TERMS[x.license] ?? x.license}{x.awaiting && <span className="obs-why">Awaiting {x.awaiting}</span>}<span className="obs-why">{x.attribution}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="fine">Only sources whose terms allow this use are shown and listed. What is not in the product, and why, is in the <Link to="/methodology#expansion">methodology</Link>.</p>
      </Section>

      {run && (
        <Section title="Last pipeline run" id="run" aside="The newest record of the run that fetches, checks, forecasts and prepares these pages. One record is written per run and never changed.">
          <dl className="obs-limits">
            <div><dt>Run</dt><dd className="num">{run.run_id ?? '—'}</dd></div>
            <div><dt>Started</dt><dd>{fmtTime(run.started_at)} · {(STARTED[run.trigger] ?? run.trigger ?? '—').toLowerCase()}</dd></div>
            <div><dt>Finished</dt><dd>{fmtTime(run.finished_at)}</dd></div>
            <div><dt>Result</dt><dd>{RUN[run.status] ?? (run.gate_passed ? 'Completed' : 'Failed its checks')}</dd></div>
            {run.sources_attempted != null && <div><dt>Sources of this site asked</dt><dd>{int(run.sources_attempted.length)} asked, {int(run.sources_succeeded.length)} answered, {int(run.sources_failed.length)} failed</dd></div>}
            {run.data_changed != null && <div><dt>New data</dt><dd>{yesNo(run.data_changed)}</dd></div>}
            {run.forecast_issued != null && <div><dt>Outlooks issued</dt><dd>{int(run.forecast_issued)}</dd></div>}
            <div><dt>Runs on record</dt><dd>{int(run.runs_on_record)}, {int(run.scheduled_runs_on_record)} of them by a scheduler</dd></div>
          </dl>
        </Section>
      )}

      <Section title="Coverage and freshness" id="coverage" aside={`The newest published month of each index, and when its first figure came out. The index files were last retrieved on ${fmtDay(core.snapshot_retrieved)}.`}>
        <div className="tbl-wrap">
          <table className="tbl">
            <thead><tr><th>Index</th><th>Newest month</th><th>First published</th><th>Outlook</th></tr></thead>
            <tbody>
              {core.freshness.map((f) => (
                <tr key={f.id}><td><Link to={f.id === core.primary ? '/market' : `/market?lane=${f.id}`}>{f.name.replace(' air freight', '')}</Link></td><td>{fmtMonth(f.latest_month)}</td><td>{fmtDay(f.latest_release)}</td><td>{f.id === core.primary ? 'Monthly direction' : <span className="dim">None: index only</span>}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <Section title="Refresh schedule" id="schedule" aside={scheduledRuns > 0 ? `Read from the workflow files of the engine. ${int(scheduledRuns)} scheduled fetches are on record.` : 'Read from the workflow files of the engine. A schedule is a definition: no scheduled fetch is on record yet.'}>
        <div className="tbl-wrap">
          <table className="tbl">
            <thead><tr><th>Job</th><th>When</th><th>Schedule as written</th></tr></thead>
            <tbody>{core.schedule.map((r) => <tr key={`${r.file}${r.cron}`}><td>{r.workflow}</td><td>{r.meaning ? r.meaning.charAt(0).toUpperCase() + r.meaning.slice(1) : '—'}</td><td className="num dim">{r.cron}</td></tr>)}</tbody>
          </table>
        </div>
      </Section>

      <Section title="Known limitations" id="limits" aside="What a reader should keep in mind about every number on this site.">
        <dl className="obs-limits">{limits(core, scheduledRuns).map(([t, d]) => <div key={t}><dt>{t}</dt><dd>{d}</dd></div>)}</dl>
      </Section>

      {core.export && (
        <Section title="Versions" id="versions" aside="What these pages were built from. The same identifiers are stored with every forecast, so a figure can be traced to its data.">
          <dl className="obs-limits">
            <div><dt>Export</dt><dd className="num">version {core.export.version} · {fmtTime(core.generated_at)}</dd></div>
            <div><dt>Engine</dt><dd className="num">{core.export.engine_commit ?? 'not recorded'}</dd></div>
            {core.export.content_hash && <div><dt>Content</dt><dd className="num">{core.export.content_hash.slice(0, 16)}</dd></div>}
            <div><dt>Terms last read</dt><dd>{fmtDay(core.export.policy_audited)}</dd></div>
            <div><dt>Published by</dt><dd>{core.publish?.workflow_run ? `a hosted run (${core.publish.workflow_run.run_id}), started by ${(STARTED[core.publish.trigger] ?? core.publish.trigger).toLowerCase()}` : 'an export that a person started'}</dd></div>
            {Object.entries(core.export.datasets).filter(([, v]) => v).map(([k, v]) => <div key={k}><dt>{DATASET[k] ?? k}</dt><dd className="num">{v}</dd></div>)}
          </dl>
        </Section>
      )}

      <p className="fine obs-gen">These pages were exported from the AirPulse engine on {fmtTime(core.generated_at)}.</p>
    </div>
  )
}
