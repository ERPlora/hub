// Snapshots + verificación CSP de hub/apps/web contra el BUILD DE PRODUCCIÓN (dist/),
// servido con CSP (script-src 'self' estricto; style-src permite inline por Tailwind/inline
// styles). Usa Chrome headless vía DevTools Protocol (sin deps npm). ARQUITECTURA.md §12.
//
// - Siembra una sesión demo en localStorage para entrar al shell sin backend.
// - Captura PNG de: login, login-pin, dashboard, employees, módulo (WC Lit dinámico).
// - Falla si hay violaciones de CSP de SCRIPT (las de estilo inline se toleran).
import { spawn } from 'node:child_process';
import { setTimeout as sleep } from 'node:timers/promises';
import { createServer } from 'node:http';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { extname, normalize, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = fileURLToPath(new URL('.', import.meta.url));
const DIST = join(HERE, 'dist');
const SHOTS = join(HERE, 'snapshots');
const PORT = 4321;
const DEBUG_PORT = 9222;
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';

if (!existsSync(DIST)) { console.error('✗ No existe dist/. Ejecuta `vite build` primero.'); process.exit(2); }
await mkdir(SHOTS, { recursive: true });

const CSP = [
  "default-src 'none'",
  "script-src 'self'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data:",
  "font-src 'self' data:",
  "connect-src 'self'",
  "base-uri 'none'",
  "object-src 'none'",
].join('; ');

const TYPES = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.json': 'application/json; charset=utf-8', '.svg': 'image/svg+xml', '.woff2': 'font/woff2' };

// Servidor estático con SPA fallback (rutas desconocidas → index.html).
const server = createServer(async (req, res) => {
  try {
    let p = decodeURIComponent((req.url || '/').split('?')[0]);
    let filePath = join(DIST, normalize(p).replace(/^(\.\.[/\\])+/, ''));
    if (!filePath.startsWith(DIST)) return res.writeHead(403).end('forbidden');
    if (p === '/' || !existsSync(filePath) || !extname(filePath)) filePath = join(DIST, 'index.html');
    const data = await readFile(filePath);
    res.writeHead(200, { 'Content-Type': TYPES[extname(filePath)] || 'application/octet-stream', 'Content-Security-Policy': CSP });
    res.end(data);
  } catch {
    res.writeHead(404, { 'Content-Security-Policy': CSP }).end('not found');
  }
});
await new Promise((r) => server.listen(PORT, r));

const chrome = spawn(CHROME, ['--headless=new', `--remote-debugging-port=${DEBUG_PORT}`, '--no-first-run', '--no-default-browser-check', '--window-size=1440,900', '--user-data-dir=/tmp/erplora-web-snap', 'about:blank']);
const cleanup = () => { try { chrome.kill(); } catch {} try { server.close(); } catch {} };

// Sesión + dispositivo de confianza demo (inyectado antes de cargar la app).
const SESSION = JSON.stringify({ id: 'u1', name: 'Demo Owner', email: 'demo@erplora.com', isAdmin: true, kind: 'cloud' });
const DEVICE = JSON.stringify({ trusted: true, users: [{ id: 'u1', name: 'Demo Owner', email: 'demo@erplora.com', initials: 'DO', pin: '0000' }] });

try {
  let wsUrl;
  for (let i = 0; i < 40; i++) {
    await sleep(150);
    try {
      const targets = await (await fetch(`http://localhost:${DEBUG_PORT}/json`)).json();
      const page = targets.find((t) => t.type === 'page' && t.webSocketDebuggerUrl);
      if (page) { wsUrl = page.webSocketDebuggerUrl; break; }
    } catch { /* retry */ }
  }
  if (!wsUrl) { console.error('✗ Chrome no expuso target de página'); cleanup(); process.exit(1); }

  const ws = new WebSocket(wsUrl);
  const scriptViolations = [];
  const styleViolations = [];
  let id = 0; const pending = new Map();
  const send = (method, params = {}) => new Promise((res) => { const mid = ++id; pending.set(mid, res); ws.send(JSON.stringify({ id: mid, method, params })); });
  await new Promise((r) => (ws.onopen = r));
  ws.onmessage = (ev) => {
    const m = JSON.parse(ev.data);
    if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); return; }
    if (m.method === 'Log.entryAdded') {
      const t = m.params.entry.text || '';
      if (/content security policy|refused to/i.test(t)) (/(script-src|script)/i.test(t) && !/style/i.test(t) ? scriptViolations : styleViolations).push(t);
    }
  };
  const evaluate = async (expr) => { const m = await send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true }); if (m.error) throw new Error(JSON.stringify(m.error)); return m.result?.result?.value; };
  const goto = async (path) => {
    const url = `http://localhost:${PORT}${path}`;
    const m = await send('Page.navigate', { url });
    if (m.error) throw new Error(`navigate ${url}: ${JSON.stringify(m.error)}`);
    await sleep(1300);
  };
  const shot = async (name) => { const r = await send('Page.captureScreenshot', { format: 'png' }); if (r.result?.data) await writeFile(join(SHOTS, `${name}.png`), Buffer.from(r.result.data, 'base64')); };

  await send('Log.enable'); await send('Runtime.enable'); await send('Page.enable');

  // Siembra localStorage navegando primero a la app (mismo origen) y recargando.
  const seed = async (path, js) => {
    await goto(path);
    await evaluate(`try{${js}}catch(e){}`);
    await goto(path); // recarga con el storage ya puesto
    await sleep(700);
  };

  // 1) LOGIN email (sin sesión).
  await seed('/login', `localStorage.clear()`);
  await shot('01-login-email');

  // 2) LOGIN PIN (dispositivo de confianza sembrado).
  await seed('/login', `localStorage.clear();localStorage.setItem('erplora.device', ${JSON.stringify(DEVICE)})`);
  await shot('02-login-pin');

  // 3) APP autenticada (sesión + dispositivo).
  await seed('/', `localStorage.setItem('erplora.session', ${JSON.stringify(SESSION)});localStorage.setItem('erplora.device', ${JSON.stringify(DEVICE)})`);
  await shot('03-dashboard');
  await goto('/employees'); await sleep(500); await shot('04-employees');

  // 4) MÓDULO: WC Lit cargado en runtime (de-risk #1).
  await goto('/m/inventory'); await sleep(1200);
  // hasTable: el WC del módulo (Lit) renderizó el <ok-data-table> compartido (@erplora/outfitkit) en
  // su shadow root. Es la señal real de de-risk #1 (WC dinámico montado + renderizado bajo CSP); NO
  // contamos filas porque sin backend la tabla está vacía y ok-data-table usa <td>, no <li>.
  const wc = JSON.parse(await evaluate(`(() => { const el = document.querySelector('erp-inventory-products'); const sr = el?.shadowRoot; return JSON.stringify({ mounted: !!el, hasShadow: !!sr, hasTable: !!sr?.querySelector('ok-data-table') }); })()`));
  await shot('05-module-inventory');

  // 5) resto de vistas de primer nivel.
  await goto('/roles'); await sleep(500); await shot('06-roles');
  await goto('/billing'); await sleep(500); await shot('07-billing');
  await goto('/marketplace'); await sleep(500); await shot('08-marketplace');
  await goto('/settings'); await sleep(500); await shot('09-settings');
  await goto('/system'); await sleep(500); await shot('10-system');
  await goto('/employees/new'); await sleep(500); await shot('11-employee-form');

  // 6) asistente abierto (drawer).
  await goto('/'); await sleep(500);
  await evaluate(`(() => { const b=[...document.querySelectorAll('ion-button')].find(x=>x.getAttribute('aria-label')==='Asistente'); b && b.click(); })()`);
  await sleep(700); await shot('12-assistant');

  // 7) modo oscuro del dashboard.
  await evaluate(`document.documentElement.classList.add('ion-palette-dark')`); await goto('/'); await sleep(500);
  await evaluate(`document.documentElement.classList.add('ion-palette-dark')`); await sleep(200); await shot('13-dashboard-dark');

  console.log('--- snapshots + CSP ---');
  console.log('WC módulo →', JSON.stringify(wc));
  console.log('violaciones CSP de SCRIPT:', scriptViolations.length, '| de estilo (toleradas):', styleViolations.length);
  scriptViolations.forEach((v) => console.log('   SCRIPT-CSP:', v));
  await writeFile(join(SHOTS, 'VERDICT.json'), JSON.stringify({ ok: scriptViolations.length === 0 && wc.mounted && wc.hasShadow && wc.hasTable, wc, scriptViolations: scriptViolations.length, styleViolations: styleViolations.length }, null, 2));

  cleanup();
  const ok = scriptViolations.length === 0 && wc.mounted && wc.hasShadow && wc.hasTable;
  console.log(ok ? '\n✓ ÉXITO: app navegable, WC de módulo (Lit) montado + <ok-data-table> renderizado, 0 violaciones de script-CSP. Snapshots en apps/web/snapshots/.' : '\n✗ Revisar VERDICT.json');
  process.exit(ok ? 0 : 1);
} catch (e) {
  console.error('✗ error:', e.message); cleanup(); process.exit(1);
}
