// Captura enfocada de la pantalla de login en sus estados, contra el build de prod.
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
const PORT = 4399, DEBUG_PORT = 9333;
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
await mkdir(SHOTS, { recursive: true });

const TYPES = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.json': 'application/json; charset=utf-8', '.svg': 'image/svg+xml', '.woff2': 'font/woff2' };
const server = createServer(async (req, res) => {
  try {
    let p = decodeURIComponent((req.url || '/').split('?')[0]);
    let fp = join(DIST, normalize(p).replace(/^(\.\.[/\\])+/, ''));
    if (!fp.startsWith(DIST)) return res.writeHead(403).end();
    if (p === '/' || !existsSync(fp) || !extname(fp)) fp = join(DIST, 'index.html');
    res.writeHead(200, { 'Content-Type': TYPES[extname(fp)] || 'application/octet-stream' });
    res.end(await readFile(fp));
  } catch { res.writeHead(404).end(); }
});
await new Promise((r) => server.listen(PORT, r));

const chrome = spawn(CHROME, ['--headless=new', `--remote-debugging-port=${DEBUG_PORT}`, '--no-first-run', '--window-size=1100,900', '--user-data-dir=/tmp/erplora-login-snap', 'about:blank']);
const cleanup = () => { try { chrome.kill(); } catch {} try { server.close(); } catch {} };

const DEVICE = JSON.stringify({ trusted: true, users: [{ id: 'u1', name: 'Demo Owner', email: 'demo@erplora.com', initials: 'DO', pin: '0000' }] });

try {
  let ws;
  for (let i = 0; i < 40; i++) { await sleep(150); try { const ts = await (await fetch(`http://localhost:${DEBUG_PORT}/json`)).json(); const pg = ts.find((t) => t.type === 'page' && t.webSocketDebuggerUrl); if (pg) { ws = pg.webSocketDebuggerUrl; break; } } catch {} }
  const W = new WebSocket(ws); let id = 0; const pend = new Map();
  const send = (m, p = {}) => new Promise((r) => { const i = ++id; pend.set(i, r); W.send(JSON.stringify({ id: i, method: m, params: p })); });
  await new Promise((r) => (W.onopen = r));
  W.onmessage = (e) => { const m = JSON.parse(e.data); if (m.id && pend.has(m.id)) { pend.get(m.id)(m); pend.delete(m.id); } };
  const evald = async (ex) => { const m = await send('Runtime.evaluate', { expression: ex, returnByValue: true, awaitPromise: true }); return m.result?.result?.value; };
  const goto = async (path) => { await send('Page.navigate', { url: `http://localhost:${PORT}${path}` }); await sleep(1200); };
  const shot = async (n) => { const r = await send('Page.captureScreenshot', { format: 'png' }); if (r.result?.data) await writeFile(join(SHOTS, `${n}.png`), Buffer.from(r.result.data, 'base64')); };
  await send('Runtime.enable'); await send('Page.enable');

  const seed = async (js) => { await goto('/login'); await evald(`try{${js}}catch(e){}`); await goto('/login'); await sleep(700); };

  // 1) Login email (dispositivo NO de confianza) → muestra checkbox + icono info.
  await seed(`localStorage.clear()`);
  await shot('login-email');
  // abrir popover del icono "i"
  await evald(`(() => { const b=document.querySelector('#trust-info'); b && b.click(); })()`);
  await sleep(600);
  await shot('login-email-info');

  // 2) Dispositivo de confianza → TABS (PIN | Email), por defecto PIN.
  await seed(`localStorage.clear();localStorage.setItem('erplora.device', ${JSON.stringify(DEVICE)})`);
  await shot('login-pin-tabs');
  // cambiar a la tab Email vía el segmento.
  await evald(`(() => { const btns=[...document.querySelectorAll('ion-segment-button')]; const em=btns.find(b=>b.value==='email'); em && em.click(); })()`);
  await sleep(700);
  await shot('login-tabs-email');

  console.log('OK login snapshots: login-email, login-email-info, login-pin-tabs, login-tabs-email');
  cleanup(); process.exit(0);
} catch (e) { console.error('error', e.message); cleanup(); process.exit(1); }
