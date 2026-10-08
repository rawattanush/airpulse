// A static host has no file for /market/forecast. GitHub Pages answers an unknown path with 404.html, so the application itself
// is published under that name too: a deep link or a reload on any route loads the application, which then shows the route.
import { copyFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const dist = join(dirname(fileURLToPath(import.meta.url)), '..', 'dist')
copyFileSync(join(dist, 'index.html'), join(dist, '404.html'))
console.log('404.html written: deep links are answered with the application')
