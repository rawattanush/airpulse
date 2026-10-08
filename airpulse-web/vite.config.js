import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The port can be given by the environment (a preview tool, a second dev server); 5183 is the default.
const port = Number(process.env.PORT) || 5183

// VITE_BASE: the path the site is served under when it is not the root of its host (for example /airpulse/ on GitHub Pages, where it is read from the Pages settings).
const base = process.env.VITE_BASE || '/'

export default defineConfig({ base, plugins: [react()], server: { port, strictPort: true } })
