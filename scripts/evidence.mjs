// pr-verify evidence helpers for Playwright (Page from `playwright` or `@playwright/test`).
//
//   import { settle, shot, card } from '<skill-dir>/scripts/evidence.mjs'
//   await shot(page, 'shots/T03-head-admin-menu.png', {
//     stamp: 'T03 · head · web@1a2b3c4',
//     settleOpts: { ready: 'table tbody tr' },   // what "data has arrived" looks like on this screen
//   })
//
// No dependencies of its own: it only calls methods on the page you pass in.
// Every failure throws. Let it throw: a `.catch(() => {})` around these calls turns a
// missing screenshot into a passing case without evidence.

const BUSY = [
  '[aria-busy="true"]',
  '.ant-skeleton', '.ant-spin-spinning',
  '.el-skeleton', '.el-loading-mask',
  '.v-skeleton-loader', '.v-progress-circular',
  '.skeleton', '.loading', '.spinner', '.nprogress-busy',
]

/**
 * Wait until the page has finished rendering.
 *  1. network quiet, bounded by `networkIdleMs` (pages with polling/websockets never go idle);
 *  2. `ready` satisfied, when given: a CSS selector that must match a visible element, or a
 *     function evaluated in the page that must return true. Pass it whenever you know what the
 *     loaded screen shows — it is the only reliable signal for data that arrives late;
 *  3. `stableRounds` consecutive identical samples, `interval` ms apart, of a hash of the
 *     body text + element count, with no visible busy indicator, no pending in-viewport image,
 *     and some content (text, or a sized canvas/img/svg/video) unless `allowEmpty`.
 * Throws with the last sample when `timeout` elapses.
 *
 * Volatile text (a clock, a live counter) must not keep the page from settling:
 * `ignoreDigits` (default true) normalises digit runs to '#' before hashing, and `ignoreSelectors`
 * removes those elements from the hash. `ready` stays the signal that the data has arrived.
 */
export async function settle(page, opts = {}) {
  const {
    timeout = 30_000,
    stableRounds = 4,
    interval = 500,
    networkIdleMs = 3_000,
    busySelectors = BUSY,
    ignoreSelectors = [],
    ignoreDigits = true,
    ready = null,
    allowEmpty = false,
  } = opts
  const deadline = Date.now() + timeout
  await page.waitForLoadState('networkidle', { timeout: Math.min(networkIdleMs, timeout) }).catch(() => {})

  let last = null
  let same = 0
  let s = null
  while (Date.now() < deadline) {
    s = await page.evaluate(({ sels, readySel, ignoreSels, dropDigits }) => {
      const inView = (r) => r.bottom > 0 && r.right > 0 && r.top < innerHeight && r.left < innerWidth
      const visible = (el) => {
        const r = el.getBoundingClientRect()
        if (r.width === 0 || r.height === 0) return false
        for (let e = el; e && e.nodeType === 1; e = e.parentElement) {
          const cs = getComputedStyle(e)
          if (cs.display === 'none' || cs.visibility === 'hidden' || Number(cs.opacity) === 0) return false
        }
        return true
      }
      let busy = 0
      for (const sel of sels) {
        try { document.querySelectorAll(sel).forEach((el) => { if (visible(el) && inView(el.getBoundingClientRect())) busy++ }) } catch { /* bad selector */ }
      }
      const imgs = [...document.images].filter((i) => !i.complete && visible(i) && inView(i.getBoundingClientRect())).length
      // hash the body text, minus the volatile bits
      let text = (document.body && document.body.innerText || '').trim()
      let count = document.getElementsByTagName('*').length
      if (ignoreSels.length) {
        const clone = document.body.cloneNode(true)
        for (const sel of ignoreSels) {
          try { clone.querySelectorAll(sel).forEach((el) => el.remove()) } catch { /* bad selector */ }
        }
        text = (clone.textContent || '').trim()
        count = clone.getElementsByTagName('*').length
      }
      if (dropDigits) text = text.replace(/\d+/g, '#')
      let h = 0
      for (let i = 0; i < text.length; i++) h = (h * 31 + text.charCodeAt(i)) | 0
      const media = [...document.querySelectorAll('canvas,img,svg,video')].filter(visible).length
      const ok = readySel === null ? true : !!document.querySelector(readySel) && visible(document.querySelector(readySel))
      return { key: `${h}:${text.length}:${count}`, text: text.length, media, busy, imgs, ok }
    }, { sels: busySelectors, readySel: typeof ready === 'string' ? ready : null, ignoreSels: ignoreSelectors, dropDigits: ignoreDigits })
    if (typeof ready === 'function') s.ok = !!(await page.evaluate(ready))
    same = s.key === last ? same + 1 : 1
    last = s.key
    const hasContent = allowEmpty || s.text > 0 || s.media > 0
    if (s.ok && s.busy === 0 && s.imgs === 0 && hasContent && same >= stableRounds) return s
    await page.waitForTimeout(interval)
  }
  throw new Error(`settle: page not ready after ${timeout}ms (${JSON.stringify(s)}) at ${page.url()}`)
}

/**
 * settle() then screenshot to `path`.
 * `stamp` draws a label in the top-right corner for the capture only (test case id,
 * base/head, commit) so a reviewer knows what build the picture is from. It stays small
 * (top 32px, at most half the width) so it never hides the content being proven.
 * `intentionalBlank: true` is for evidence of a broken/blank screen: it skips the content
 * requirement and turns the stamp red with "INTENTIONAL BLANK".
 * `mock: true` adds "MOCK" to the stamp: the picture illustrates, it cannot prove a test case.
 * For lazy-loaded pages, scroll to the bottom and back before calling shot() with fullPage.
 */
export async function shot(page, path, opts = {}) {
  const { stamp, fullPage = true, intentionalBlank = false, mock = false, settleOpts = {} } = opts
  await settle(page, { ...settleOpts, allowEmpty: intentionalBlank || settleOpts.allowEmpty })
  let label = stamp || ''
  if (mock) label = `MOCK · ${label}`
  if (intentionalBlank) label = `INTENTIONAL BLANK — this is the defect${label ? ' · ' + label : ''}`
  if (label) {
    await page.evaluate(({ label, red }) => {
      const d = document.createElement('div')
      d.id = '__pr_verify_stamp'
      d.textContent = label
      d.style.cssText = `position:fixed;top:3px;right:4px;z-index:2147483647;padding:3px 8px;` +
        `font:12px/16px monospace;color:#fff;background:${red ? '#c62828' : '#1565c0'};` +
        `border-radius:4px;opacity:.92;pointer-events:none;white-space:nowrap;` +
        `max-width:46vw;overflow:hidden;text-overflow:ellipsis`
      document.documentElement.appendChild(d)
    }, { label, red: intentionalBlank || mock })
  }
  try {
    const buf = await page.screenshot({ path, fullPage })
    return { path, bytes: buf.length, url: page.url() }
  } finally {
    if (label) await page.evaluate(() => document.getElementById('__pr_verify_stamp')?.remove()).catch(() => {})
  }
}

/**
 * Render non-UI evidence (API response, SQL result, log excerpt) as a readable image,
 * optionally BEFORE | AFTER side by side, for reviewers who only look at pictures.
 *   await card(page, 'shots/T05-card.png', {
 *     title: 'T05 · locked account ⇒ /me returns 403',
 *     before: { label: 'api@0ld0000', text: fs.readFileSync('logs/T05-base.txt', 'utf8') },
 *     after:  { label: 'api@abc1234', text: fs.readFileSync('logs/T05-head.txt', 'utf8') },
 *   })
 * Pass `after` alone for a single panel. Text is shown verbatim (monospace, escaped); feed it
 * the evidence file written by capture.sh, so the picture and the log say the same thing.
 * Long text is cut at `maxChars` (default 2000) and the cut is stated in the picture; the file
 * itself stays untouched, so the full text is always available.
 * Uses a fresh page, so the caller's page is untouched.
 */
export async function card(page, path, { title, before, after, width = 1280, maxChars = 2000 }) {
  const esc = (s) => String(s).replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]))
  const cut = (p) => {
    if (!p) return ''
    const text = String(p.text ?? '')
    const body = text.length > maxChars ? `${text.slice(0, maxChars)}\n… (đã cắt ${text.length - maxChars} ký tự; xem file đầy đủ)` : text
    return `<section><h2 style="background:${p.colour}">${esc(p.label || '')}</h2><pre>${esc(body)}</pre></section>`
  }
  const panel = (p, colour) => (p ? cut({ ...p, colour }) : '')
  const html = `<!doctype html><meta charset="utf-8"><style>
    body{margin:0;font:14px/1.45 system-ui,sans-serif;background:#fff;color:#111}
    h1{font-size:16px;margin:0;padding:10px 14px;background:#263238;color:#fff}
    main{display:grid;grid-template-columns:${before && after ? '1fr 1fr' : '1fr'};gap:10px;padding:10px}
    h2{font-size:13px;margin:0;padding:6px 10px;color:#fff}
    pre{margin:0;padding:10px;background:#f5f5f5;white-space:pre-wrap;word-break:break-word;font:12px/1.45 monospace}
    section{border:1px solid #ddd}</style>
    <h1>${esc(title)}</h1><main>${panel(before, '#c62828')}${panel(after, '#2e7d32')}</main>`
  // A page opened by browser.newPage() owns its context, which refuses a second page.
  const ctx = page.context()
  const p = await ctx.newPage().catch(() => ctx.browser().newPage())
  try {
    await p.setViewportSize({ width, height: 120 }) // fullPage grows to the content
    await p.setContent(html)
    await p.screenshot({ path, fullPage: true, timeout: 60_000 })
    return { path }
  } catch (err) {
    throw new Error(`card: could not render ${path}: ${err.message}`)
  } finally {
    await p.close()
  }
}
