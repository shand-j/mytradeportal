#!/usr/bin/env node
/**
 * Wave A evidence capture orchestrator.
 *
 * Interleaves two kinds of video segments into docs/evidence/wave-a/:
 *   * terminal segments — the narrated lifecycle runner (lifecycle.sh) runs
 *     LIVE while a browser records scripts/terminal.html polling its log;
 *   * browser segments — the real customer-facing pages on the local landing
 *     dev server (/quote/:token, /invoice/:token, /pay/:token) plus Mailpit.
 *
 * Prerequisites (see README.md): stubbed API on :8100, landing dev server on
 * :5174, docker infra (postgres/mailpit) up, Playwright chromium installed.
 *
 *   node docs/evidence/wave-a/scripts/capture.mjs
 */
import { chromium } from 'playwright'
import { spawn } from 'node:child_process'
import http from 'node:http'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const WAVE_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const RUN_DIR = path.join(WAVE_DIR, 'run')
const LOG = path.join(RUN_DIR, 'lifecycle.log')
const STATE = path.join(RUN_DIR, 'state.env')
const SHOTS = path.join(RUN_DIR, 'screenshots')
const LANDING = process.env.LANDING || 'http://localhost:5174'
const API = process.env.API || 'http://localhost:8100'
const MAILPIT = process.env.MAILPIT || 'http://localhost:8025'
const REPO = path.resolve(WAVE_DIR, '../../..')

fs.mkdirSync(RUN_DIR, { recursive: true })
fs.mkdirSync(SHOTS, { recursive: true })

function state() {
  const out = {}
  for (const line of fs.readFileSync(STATE, 'utf8').split('\n')) {
    const m = line.match(/^([A-Z_]+)="?(.*?)"?$/)
    if (m) out[m[1]] = m[2]
  }
  return out
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

// --- tiny static server for the terminal page + live runner log ------------
function startTerminalServer() {
  const server = http.createServer((req, res) => {
    const url = req.url.split('?')[0]
    if (url === '/run.log') {
      res.writeHead(200, { 'Content-Type': 'text/plain; charset=utf-8', 'Cache-Control': 'no-store' })
      res.end(fs.existsSync(LOG) ? fs.readFileSync(LOG) : '')
      return
    }
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' })
    res.end(fs.readFileSync(path.join(WAVE_DIR, 'scripts', 'terminal.html')))
  })
  return new Promise((resolve) => server.listen(8899, () => resolve(server)))
}

// --- video segment helper ---------------------------------------------------
let browser
async function segment(name, fn) {
  const tmp = path.join(RUN_DIR, 'raw-video')
  fs.rmSync(tmp, { recursive: true, force: true })
  fs.mkdirSync(tmp, { recursive: true })
  const context = await browser.newContext({
    viewport: { width: 1280, height: 720 },
    recordVideo: { dir: tmp, size: { width: 1280, height: 720 } },
  })
  const page = await context.newPage()
  try {
    await fn(page)
  } finally {
    await sleep(800) // let the final frame settle into the recording
    await context.close()
    const videoPath = await page.video().path()
    fs.renameSync(videoPath, path.join(WAVE_DIR, name))
    console.log(`  saved ${name}`)
  }
}

async function shot(page, name) {
  await page.screenshot({ path: path.join(SHOTS, name), fullPage: false })
  console.log(`  screenshot run/screenshots/${name}`)
}

async function slowScroll(page, times = 6, pauseMs = 1000) {
  for (let i = 0; i < times; i++) {
    await page.mouse.wheel(0, 240)
    await sleep(pauseMs)
  }
  for (let i = 0; i < times; i++) {
    await page.mouse.wheel(0, -240)
    await sleep(Math.round(pauseMs / 2))
  }
}

// Run a lifecycle step range live while the terminal page records it.
async function terminalSegment(name, from, to) {
  await segment(name, async (page) => {
    await page.goto('http://localhost:8899/')
    await sleep(1200)
    const logStream = fs.createWriteStream(LOG, { flags: 'a' })
    const child = spawn('bash', [path.join(WAVE_DIR, 'scripts', 'lifecycle.sh'), String(from), String(to)], {
      env: {
        ...process.env,
        API,
        MAILPIT,
        PAUSE: process.env.PAUSE || '2.0',
        PY: process.env.PY || path.join(REPO, '.venv', 'bin', 'python'),
        STRIPE_WEBHOOK_SECRET: process.env.STRIPE_WEBHOOK_SECRET || 'whsec_evidence_local_test',
      },
    })
    child.stdout.pipe(logStream)
    child.stderr.pipe(logStream)
    const code = await new Promise((resolve, reject) => {
      child.on('exit', resolve)
      child.on('error', reject)
    })
    logStream.end()
    if (code !== 0) throw new Error(`lifecycle steps ${from}-${to} exited with code ${code}`)
    await sleep(4000) // let the viewer read the final assertions
  })
}

async function main() {
  // Preflight: the two app servers must be up before we record anything.
  for (const [label, url] of [['stubbed API', `${API}/health`], ['landing', LANDING], ['mailpit', `${MAILPIT}/api/v1/messages?limit=1`]]) {
    const res = await fetch(url).catch(() => null)
    if (!res || !res.ok) throw new Error(`${label} not reachable at ${url} — start it first (see README.md)`)
  }
  fs.writeFileSync(LOG, '')
  await startTerminalServer()

  browser = await chromium.launch({ headless: true })

  // -- Part A: onboarding -> AI quotes seeded -> hero quote sent ------------
  await terminalSegment('00a-terminal-onboarding-quote.webm', 1, 8)

  // -- Customer opens the secure quote link ----------------------------------
  let st = state()
  await segment('01-quote-view.webm', async (page) => {
    await page.goto(`${LANDING}/quote/${st.QUOTE_TOKEN}`)
    await page.getByText('Consumer unit replacement').waitFor({ timeout: 15000 })
    await sleep(3000)
    await shot(page, '01-quote-view.png')
    await slowScroll(page, 6)
    await page.getByText('Reply to your electrician').scrollIntoViewIfNeeded()
    await sleep(3500)
  })

  // -- Part B: customer accepts -> job -> invoice sent ----------------------
  await terminalSegment('00b-terminal-accept-job-invoice.webm', 10, 12)

  st = state()
  await segment('02-quote-accepted.webm', async (page) => {
    await page.goto(`${LANDING}/quote/${st.QUOTE_TOKEN}`)
    await page.locator('header').getByText(/approved/i).waitFor({ timeout: 15000 })
    await sleep(4500)
    await shot(page, '02-quote-accepted.png')
  })

  await segment('03-invoice-pay-button.webm', async (page) => {
    await page.goto(`${LANDING}/invoice/${st.INVOICE_TOKEN}`)
    await page.getByText('Pay this invoice').waitFor({ timeout: 15000 })
    await sleep(3000)
    await shot(page, '03-invoice-pay-button.png')
    await slowScroll(page, 5)
    await page.getByText('Pay this invoice').scrollIntoViewIfNeeded()
    await page.getByText('Pay this invoice').hover()
    await sleep(3000)
  })

  // -- /pay/:token branded shell + graceful degradation (no publishable key) -
  await segment('04-pay-page-degraded.webm', async (page) => {
    await page.goto(st.PAY_URL)
    await page.getByText(/Card payments aren't available right now/).waitFor({ timeout: 15000 })
    await sleep(5000)
    await shot(page, '04-pay-page-degraded.png')
  })

  // -- Part C: payment settles via signed webhook ---------------------------
  await terminalSegment('00c-terminal-payment-settled.webm', 14, 14)

  await segment('05-invoice-paid.webm', async (page) => {
    await page.goto(`${LANDING}/invoice/${st.INVOICE_TOKEN}`)
    await page.getByText('This invoice is paid — thank you.').waitFor({ timeout: 15000 })
    await sleep(3500)
    await shot(page, '05-invoice-paid.png')
    await page.getByText('This invoice is paid — thank you.').scrollIntoViewIfNeeded()
    await sleep(2500)
  })

  // -- Part D: full refund ---------------------------------------------------
  await terminalSegment('00d-terminal-refund.webm', 15, 16)

  await segment('06-invoice-refunded.webm', async (page) => {
    await page.goto(`${LANDING}/invoice/${st.INVOICE_TOKEN}`)
    await page.locator('header').getByText(/refunded/i).waitFor({ timeout: 15000 })
    await sleep(4500)
    await shot(page, '06-invoice-refunded.png')
  })

  // -- Mailpit: the lifecycle emails really flowed ---------------------------
  await segment('07-mailpit.webm', async (page) => {
    await page.goto(MAILPIT)
    await sleep(3500)
    const search = page.locator('input[placeholder*="Search"], input[type="search"]').first()
    if (await search.count()) {
      await search.fill('alice.homeowner@example.com')
      await page.keyboard.press('Enter')
      await sleep(3000)
    }
    await shot(page, '07-mailpit-inbox.png')
    // Open the newest message and let the branded HTML render.
    const row = page.locator('tr, .message, [class*="message"]').filter({ hasText: /Invoice|Quote/i }).first()
    if (await row.count()) {
      await row.click().catch(() => {})
      await sleep(5000)
      await shot(page, '07-mailpit-message.png')
    }
    await slowScroll(page, 4)
  })

  await browser.close()
  console.log('\nAll segments captured into', WAVE_DIR)
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
