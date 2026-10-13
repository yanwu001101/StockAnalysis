// Local-only Chrome fixture test. Never connects to the user's browser or a live API.
// First: node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5179
// Then: node tests/visual-smoke.mjs
import { spawn } from 'node:child_process'
import { mkdir, writeFile } from 'node:fs/promises'
import path from 'node:path'
import net from 'node:net'
const output = path.resolve('tests/artifacts')
await mkdir(output, { recursive: true })
const lease = net.createServer()
await new Promise(resolve => lease.listen(0, '127.0.0.1', resolve))
const port = lease.address().port
await new Promise(resolve => lease.close(resolve))
const chrome = process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const processHandle = spawn(chrome, ['--headless=new', '--disable-gpu', '--no-first-run', '--hide-scrollbars', '--disable-extensions',
  `--remote-debugging-port=${port}`, `--user-data-dir=${path.join(output, 'smoke-profile')}`, 'about:blank'],
  { windowsHide: true, stdio: 'ignore' })
let socket
try {
  let target
  for (let i = 0; i < 50; i++) {
    try { target = await (await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, { method: 'PUT' })).json(); break } catch {}
    await new Promise(resolve => setTimeout(resolve, 100))
  }
  if (!target) throw new Error('Isolated Chrome did not start')
  socket = new WebSocket(target.webSocketDebuggerUrl)
  await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject })
  let nextId = 0
  const pending = new Map()
  socket.onmessage = event => {
    const msg = JSON.parse(event.data)
    if (!pending.has(msg.id)) return
    const { resolve, reject } = pending.get(msg.id); pending.delete(msg.id)
    msg.error ? reject(new Error(msg.error.message)) : resolve(msg.result)
  }
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++nextId; pending.set(id, { resolve, reject }); socket.send(JSON.stringify({ id, method, params }))
  })
  await send('Page.enable')
  await send('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true })
  const report = []
  const scenarios = (process.env.SMOKE_CASES || 'uncalibrated,calibrated,insufficient,backtest-null,backtest-error,paper-error').split(',')
  const baseURL = process.env.SMOKE_BASE_URL || 'http://127.0.0.1:5179'
  for (const scenario of scenarios) {
    await send('Page.navigate', { url: `${baseURL}/tests/fixtures/presentation.html?case=${scenario}&view=mobile` })
    let outcome
    for (let i = 0; i < 100; i++) {
      await new Promise(resolve => setTimeout(resolve, 100))
      const state = await send('Runtime.evaluate', { expression: 'document.body.dataset.smoke || null', returnByValue: true })
      if (state.result.value) { outcome = JSON.parse(state.result.value); break }
    }
    if (!outcome) {
      const debug = await send('Runtime.evaluate', { expression: 'document.documentElement.outerHTML', returnByValue: true })
      await writeFile(path.join(output, `${scenario}-error.html`), debug.result.value || '')
      throw new Error(`Fixture timeout: ${scenario}`)
    }
    const screenshot = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true })
    await writeFile(path.join(output, `${scenario}-390.png`), Buffer.from(screenshot.data, 'base64'))
    report.push(outcome)
  }
  await writeFile(path.join(output, 'visual-smoke.json'), JSON.stringify(report, null, 2))
  console.log(JSON.stringify(report, null, 2))
  if (report.some(item => !item.passed || item.viewport !== 390)) process.exitCode = 1
} finally { socket?.close(); processHandle.kill() }
