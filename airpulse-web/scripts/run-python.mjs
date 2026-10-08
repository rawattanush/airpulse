// Runs a script with the AirPulse engine's interpreter, on Windows and on POSIX alike.
//   node scripts/run-python.mjs scripts/export_data.py [arguments]
// The interpreter is AIRPULSE_PYTHON when set, otherwise the virtual environment of the engine (the parent folder in the
// hosted repository, the folder AirPlus beside this one on the research machine).
import { spawnSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const web = join(dirname(fileURLToPath(import.meta.url)), '..')
// single repository: the engine is the parent folder; two folders side by side: the folder AirPlus
const engine = process.env.AIRPULSE_ROOT || (existsSync(join(web, '..', 'src', 'ops')) ? join(web, '..') : join(web, '..', 'AirPlus'))
const candidates = [process.env.AIRPULSE_PYTHON, join(engine, '.venv', 'Scripts', 'python.exe'), join(engine, '.venv', 'bin', 'python')].filter(Boolean)
const python = candidates.find((p) => p === process.env.AIRPULSE_PYTHON || existsSync(p))
if (!python) { console.error(`No interpreter found. Create the engine's environment (${join(engine, '.venv')}) or set AIRPULSE_PYTHON.`); process.exit(1) }
const r = spawnSync(python, process.argv.slice(2), { cwd: web, stdio: 'inherit' })
process.exit(r.status ?? 1)
