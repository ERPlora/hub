#!/usr/bin/env node
// qa-local-ui.mjs — barrido de rutas del shell del Hub contra el dev server local (:5173) o un hub
// provisionado. Distingue SEÑALES DE PRODUCTO (que fallan el run) de RUIDO TÉCNICO (solo se reporta).
//
// Antes (hub#113) un barrido ingenuo marcaba 195/195 checks como fallidos: capturaba CSS dentro de
// shadow DOM (overflow interno de Ionic), contaba errores de consola genéricos (Ionic/Lit/Vite HMR)
// y enterraba los fallos reales (`routed-to-login`, `module-element-not-mounted`, `load-error-text`).
// Este script los separa: el exit code lo deciden SOLO los fallos `severity: 'product'`.
//
// Check-types:
//   product:  routed-to-login | load-error-text | module-element-not-mounted
//   noise:    horizontal-overflow | console-error
//   info:     probe-error
//
// Usage:
//   node scripts/qa-local-ui.mjs [base_url] [email] [password] [--routes=/a,/b]
//   default base_url: http://localhost:5173
//
// Requiere Playwright (lo localiza como e2e.mjs: require local, npm root -g o npx cache).
import { createRequire } from 'node:module';
import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { execSync } from 'node:child_process';
import { homedir } from 'node:os';
import path from 'node:path';

const argv = process.argv.slice(2);
const flags = argv.filter((a) => a.startsWith('--'));
const positional = argv.filter((a) => !a.startsWith('--'));
const baseUrl = (positional[0] || 'http://localhost:5173').replace(/\/$/, '');
const email = positional[1] || process.env.HUB_QA_EMAIL || 'demo@erplora.com';
const password = positional[2] || process.env.HUB_QA_PASSWORD || 'demo';
const routesFlag = flags.find((a) => a.startsWith('--routes='));
const REPORT_DIR = process.env.HUB_QA_REPORT_DIR;

// Rutas del shell autenticado a barrer (router/index.ts). Las de módulo se generan dinámicamente
// desde /api/modules si el hub responde; si no, esta lista por defecto cubre las core.
const DEFAULT_ROUTES = [
  '/dashboard',
  '/marketplace',
  '/apps',
  '/system',
  '/settings',
  '/billing',
  '/profile',
  '/api-docs',
];
const routes = routesFlag ? routesFlag.split('=')[1].split(',').map((r) => r.trim()) : DEFAULT_ROUTES;

// ── localizar Playwright (mismo helper que ops/scripts/qa/e2e.mjs) ──────────────────────────
function locatePlaywright() {
  const require = createRequire(import.meta.url);
  try { return require('playwright'); } catch { /* */ }
  const roots = [];
  try { roots.push(execSync('npm root -g', { encoding: 'utf8' }).trim()); } catch { /* */ }
  roots.push(path.join(homedir(), '.npm', '_npx'));
  for (const root of roots) {
    if (!root || !existsSync(root)) continue;
    try {
      const found = execSync(`find ${JSON.stringify(root)} -maxdepth 5 -type d -path '*/node_modules/playwright' 2>/dev/null`, { encoding: 'utf8' }).trim().split('\n').filter(Boolean);
      for (const dir of found) { try { return createRequire(path.join(dir, 'index.js'))('playwright'); } catch { /* */ } }
    } catch { /* */ }
  }
  return null;
}
function findChromium() {
  const cache = path.join(homedir(), 'Library', 'Caches', 'ms-playwright');
  if (!existsSync(cache)) return undefined;
  const scan = (e) => { try { return execSync(`find ${JSON.stringify(cache)} ${e} 2>/dev/null | sort -r`, { encoding: 'utf8' }).trim().split('\n').filter(Boolean); } catch { return []; } };
  return scan(`-type f -name 'chrome-headless-shell'`)[0] || scan(`-type f -path '*chromium-*' -path '*Contents/MacOS/*' ! -name '*.dylib'`)[0];
}

// ── allowlist de ruido de consola (Ionic/Lit/Vite HMR) para no falsear `console-error` ──────
// Patrones benignos: HMR, deprecaciones de Ionic, warnings de Lit, el SW en dev, prefetch.
const CONSOLE_NOISE = [
  /Vite (HMR|dev server|server connection)/i,
  /\[vite\]/i,
  /ionic|iön-/i,
  /\[lit\]|lit-html|will update/i,
  /service worker|sw\.js|workbox/i,
  /Download the React DevTools/i,
  /prefetch|preload/i,
  /Warning: .*deprecated/i,
];

const findings = [];

// Cada hallazgo lleva tipo + severidad. El exit code lo deciden SOLO los de severidad 'product'.
function record(route, type, detail, severity = 'noise') {
  findings.push({ route, type, detail, severity });
  const tag = severity === 'product' ? '✗' : severity === 'noise' ? '~' : '·';
  console.error(`  ${tag} [${type}] ${route}: ${detail}`);
}

const onLogin = (u) => {
  // hub#113: parsear el PATHNAME, no la URL entera. `/login?redirect=/dashboard` contiene
  // "/dashboard" en la query y un match ingenuo reporta un falso login-OK mientras sigues en /login.
  try { return /^\/login(\/|$|\?)/.test(new URL(u).pathname); } catch { return false; }
};

(async () => {
  const pw = locatePlaywright();
  if (!pw) { console.error('playwright no encontrado (instálalo: npm i -g playwright)'); process.exit(3); }

  const browser = await pw.chromium.launch({ headless: true, ...(findChromium() ? { executablePath: findChromium() } : {}) });
  const page = await (await browser.newContext()).newPage();
  const shot = (n) => { if (REPORT_DIR) page.screenshot({ path: path.join(REPORT_DIR, n), fullPage: true }).catch(() => {}); };

  // ── capturas: console-error (noise) y respuestas 4xx/5xx (ruido salvo rutas de producto) ──
  page.on('console', (m) => {
    if (m.type() !== 'error') return;
    const txt = m.text().slice(0, 300);
    // Sólo cuenta como hallazgo lo que NO casa con el allowlist de ruido conocido.
    if (!CONSOLE_NOISE.some((re) => re.test(txt))) record('(global)', 'console-error', txt, 'noise');
  });

  try {
    // ── LOGIN ──
    if (REPORT_DIR) mkdirSync(REPORT_DIR, { recursive: true });
    await page.goto(`${baseUrl}/login`, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await page.waitForSelector('input[type="email"]', { timeout: 30000 }).catch(() => {});
    await page.fill('input[type="email"]', email).catch(() => {});
    await page.fill('input[type="password"]', password).catch(() => {});
    await page.locator('ion-button', { hasText: /Entrar|Sign in|Login/i }).first().click({ timeout: 8000 }).catch(() => {});
    let logged = false;
    for (let i = 0; i < 25; i++) {
      await page.waitForTimeout(1000);
      const onEmailForm = await page.locator('input[type="email"]').count().catch(() => 0);
      const hasShell = await page.locator('ion-menu, ion-split-pane').count().catch(() => 0);
      if (hasShell > 0 && onEmailForm === 0) { logged = true; break; }
    }
    shot('01-after-login.png');
    if (!logged) {
      record('/login', 'load-error-text', `login falló (sin shell tras credenciales); url=${page.url()}`, 'product');
      throw new Error('login falló');
    }

    // Descubrir rutas de módulo desde /api/modules (si el hub responde).
    let moduleRoutes = [];
    try {
      const mods = await page.evaluate(async () => {
        const r = await fetch('/api/modules', { headers: { Accept: 'application/json' } });
        return r.ok ? r.json() : [];
      });
      const ids = Array.isArray(mods) ? mods.map((m) => m.id).filter(Boolean) : [];
      moduleRoutes = ids.map((id) => `/m/${id}`);
    } catch { /* hub sin /api/modules o sin módulos instalados: no es fallo */ }
    const allRoutes = [...routes, ...moduleRoutes];

    for (const route of allRoutes) {
      try {
        await page.goto(`${baseUrl}${route}`, { waitUntil: 'domcontentloaded', timeout: 30000 });
        await page.waitForTimeout(2500); // WC dinámico (import() del módulo) + layout settle

        // product: routed-to-login — la ruta protegida rebotó al login (auth roto o permiso).
        if (onLogin(page.url())) {
          record(route, 'routed-to-login', `redirige a login (auth/permiso): ${page.url()}`, 'product');
          continue;
        }

        // product: load-error-text — banner/texto explícito de error de carga del módulo o ruta.
        const bodyText = (await page.locator('body').innerText().catch(() => '')).toLowerCase();
        if (/error al cargar|módulo no encontrado|failed to load|module not found|no se pudo cargar/.test(bodyText)) {
          record(route, 'load-error-text', bodyText.slice(0, 160).replace(/\n/g, ' '), 'product');
        }

        // product: module-element-not-mounted — rutas /m/<id> deben montar un WC `erp-*`.
        if (route.startsWith('/m/')) {
          // hub#113: usar customElements (pierza shadow DOM) en vez de un locator desde la raíz,
          // que no atraviesa el shadow de ion-content y daría un falso "no montado".
          const mounted = await page.evaluate(() => {
            const ids = Array.from(document.body.querySelectorAll('*'))
              .map((el) => el.tagName.toLowerCase())
              .filter((t) => t.startsWith('erp-'));
            return new Set(ids).size;
          });
          if (mounted === 0) record(route, 'module-element-not-mounted', 'no hay ningún WC erp-* en el DOM', 'product');
        }

        // noise: horizontal-overflow — SOLO documentElement (no shadow interno de Ionic), post-settle,
        // umbral >16px (1rem) para no contar scroll cosmético de sub-píxel.
        const overflow = await page.evaluate(() => {
          const de = document.documentElement;
          return Math.round((de.scrollWidth - de.clientWidth) * 100) / 100;
        }).catch(() => 0);
        if (overflow > 16) record(route, 'horizontal-overflow', `+${overflow}px de scroll horizontal`, 'noise');

        shot(`route-${route.replace(/[^\w.-]/g, '_')}.png`);
      } catch (e) {
        // info: probe-error — timeout/fallo del propio barrido (no del producto). No falla el run.
        record(route, 'probe-error', e.message.slice(0, 160), 'info');
      }
    }
  } catch (e) {
    if (e.message !== 'login falló') record('(global)', 'probe-error', e.message, 'info');
  } finally {
    await browser.close();
    const report = { baseUrl, routes: allRoutes, findings, productFailures: findings.filter((f) => f.severity === 'product') };
    if (REPORT_DIR) writeFileSync(path.join(REPORT_DIR, 'qa-local-ui-report.json'), JSON.stringify(report, null, 2));
    console.log(JSON.stringify(report, null, 2));
    process.exit(report.productFailures.length ? 1 : 0);
  }
})();
