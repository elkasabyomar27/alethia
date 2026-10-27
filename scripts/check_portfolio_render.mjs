// Render actual portfolio components against the bundled snapshot, without a browser/API.
import { createRequire, Module } from 'node:module'
import { fileURLToPath } from 'node:url'
import assert from 'node:assert/strict'
const require = createRequire(new URL('../frontend/package.json', import.meta.url))
const { build } = require('esbuild')
const { createElement } = require('react')
const { renderToStaticMarkup } = require('react-dom/server')
const filename = fileURLToPath(new URL('../frontend/.portfolio-render-check.cjs', import.meta.url))
const result = await build({ entryPoints: [fileURLToPath(new URL('../frontend/src/portfolio/PortfolioApp.tsx', import.meta.url))],
  bundle: true, write: false, platform: 'node', format: 'cjs', external: ['react', 'react-dom'], loader: { '.css': 'empty' }, jsx: 'automatic' })
const compiled = new Module(filename)
compiled.filename = filename
compiled.paths = require.resolve.paths('react')
compiled._compile(result.outputFiles[0].text, filename)
const scenarios = [
  ['#oracle', 'Explore a saved conversation'],
  ['#library?source=03-returns-section-2', 'Change-of-mind returns'],
  ['#tribunal', '0.7333'],
  ['#dispatch', 'NO TICKET IS CREATED'],
  ['#library?source=missing', 'This saved source link is unavailable'],
]
for (const [hash, expected] of scenarios) {
  globalThis.location = { hash }
  const html = renderToStaticMarkup(createElement(compiled.exports.default))
  assert.ok(html.includes(expected), `Missing expected flow for ${hash}`)
  assert.ok(html.includes('Guided demo — saved examples'))
  assert.ok(!html.includes('undefined'))
  assert.ok(!html.includes('/api/'))
}
delete globalThis.location
console.log(`Portfolio render contracts passed: ${scenarios.length} routes/states, no API usage.`)
