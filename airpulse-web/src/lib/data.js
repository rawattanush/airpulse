// Frontend adapter, browser side. The React application reads the JSON that scripts/export_data.py writes from the AirPulse
// engine's persisted outputs. Each file is fetched once and kept. Nothing here computes a forecast.
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

const pending = {}
const resolved = {}

function load(path) {
  if (!pending[path]) {
    pending[path] = fetch(`${import.meta.env.BASE_URL}data/${path}`)
      .then((r) => { if (!r.ok) throw new Error(`The data file ${path} could not be read (${r.status}).`); return r.text() })
      // a development server answers a missing file with the application page, so the content is checked, not only the status
      .then((t) => { try { return JSON.parse(t) } catch { throw new Error(`The data file ${path} is missing or is not valid data.`) } })
      .then((d) => (resolved[path] = d))
      .catch((e) => { delete pending[path]; throw e })
  }
  return pending[path]
}

/** Returns the data of a file, or null while it is loading. A failed read is thrown to the nearest error boundary. */
export function useData(path) {
  const [state, set] = useState({ path, data: resolved[path] ?? null, error: null })
  useEffect(() => {
    let on = true
    if (resolved[path]) { set({ path, data: resolved[path], error: null }); return }
    set({ path, data: null, error: null })
    load(path).then((d) => on && set({ path, data: d, error: null })).catch((e) => on && set({ path, data: null, error: e }))
    return () => { on = false }
  }, [path])
  if (state.error && state.path === path) throw state.error
  return state.path === path ? state.data : resolved[path] ?? null
}

export const useCore = () => useData('core.json')        // lanes, fuel, data state, source registry, run status
export const useOutlook = () => useData('outlook.json')  // the one official forecast and its record, validated target only
export const useMarket = (id) => useData(`market/${id}.json`) // the published index of a lane
export const useReplay = () => useData('replay.json')    // what was known at each issuance date
export const useAviation = () => useData('aviation.json') // observed air traffic: counts from official sources, nothing derived
export const useWeekly = () => useData('weekly.json')    // the weekly fuel-cost outlook: a fuel target, not a freight price

/** The lane in view is carried in the URL (?lane=IC1311) so a page can be linked to; the validated target is the default. */
export function useLane(core) {
  const [params, setParams] = useSearchParams()
  const primary = core?.primary
  const wanted = params.get('lane')
  const lane = core?.lanes.find((l) => l.id === wanted)?.id ?? primary
  const setLane = (id) => {
    const next = new URLSearchParams(params)
    if (id === primary) next.delete('lane'); else next.set('lane', id)
    setParams(next, { replace: true })
  }
  return [lane, setLane]
}
