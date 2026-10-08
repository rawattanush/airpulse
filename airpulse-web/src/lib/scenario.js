// The scenario calculator. It is arithmetic on numbers the user types: baseline × (1 + movement).
// It is NOT a forecast and uses no AirPulse output. AirPulse has no validated route-level rate model.

// Money to the cent. A product such as 4.35 × 1200.5 is held as 5222.17499999…; twelve significant digits remove that binary noise before rounding half up.
const round2 = (v) => Math.round(Number(v.toPrecision(12)) * 100) / 100

/** Parse a user-typed number. Accepts "650", "650.5", "1,250.75"; rejects anything else. */
export function parseAmount(text) {
  if (typeof text === 'number') return Number.isFinite(text) ? text : null
  const t = String(text ?? '').trim().replace(/,/g, '')
  if (!/^[-+]?\d*\.?\d+$/.test(t)) return null
  const v = Number(t)
  return Number.isFinite(v) ? v : null
}

/**
 * @param {{rate: number|null, weight: number|null, movementPct: number|null}} input
 *   rate: the user's current known rate per kilogram; weight: chargeable weight in kilograms; movementPct: the user's own scenario, in per cent.
 * @returns {{ok: false, problems: string[]} | {ok: true, scenarioRate: number, baselineCost: number|null, scenarioCost: number|null, difference: number|null, rateDifference: number}}
 */
export function scenario({ rate, weight, movementPct }) {
  const problems = []
  if (rate == null) problems.push('Enter your current rate per kilogram.')
  else if (rate <= 0) problems.push('The rate must be greater than zero.')
  if (movementPct == null) problems.push('Choose or enter a scenario movement.')
  else if (movementPct <= -100) problems.push('A movement of −100% or less leaves no rate.')
  else if (Math.abs(movementPct) > 500) problems.push('Enter a movement between −99% and +500%.')
  if (weight != null && weight <= 0) problems.push('The chargeable weight must be greater than zero.')
  if (problems.length) return { ok: false, problems }
  const scenarioRate = round2(rate * (1 + movementPct / 100))
  const hasWeight = weight != null
  const baselineCost = hasWeight ? round2(rate * weight) : null
  const scenarioCost = hasWeight ? round2(scenarioRate * weight) : null
  return { ok: true, scenarioRate, rateDifference: round2(scenarioRate - rate), baselineCost, scenarioCost, difference: hasWeight ? round2(scenarioCost - baselineCost) : null }
}
