// Orquestador del demo: arranca el server Rust real, instala 2 módulos, sirve la página
// (proxy /api → server, mismo origen → sin CORS), abre Chrome headless, captura el grid
// de módulos en 2 estados (todo activo / notes desactivado).
import { spawn } from 'node:child_process';
import { setTimeout as sleep } from 'node:timers/promises';
import { createServer } from 'node:http';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { extname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = fileURLToPath(new URL('.', import.meta.url));
const ROOT = join(HERE, '../..');               // hub/
const API_PORT = 8802, WEB_PORT = 4400, DBG = 9444;
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const SHOTS = join(HERE, 'snapshots');
await mkdir(SHOTS, { recursive: true });

// 1) server Rust (Postgres-only, ADR-0154). BD de demo dedicada; créala con
//    `createdb erplora_hotplug_demo` o exporta HUB_DATABASE_URL apuntando a otra.
const DB_URL = process.env.HUB_DATABASE_URL || 'postgres://localhost/erplora_hotplug_demo';
const srv = spawn('cargo', ['run', '-q', '-p', 'erplora-server'], {
  cwd: ROOT, env: { ...process.env, HUB_DATABASE_URL: DB_URL, HUB_BIND: `127.0.0.1:${API_PORT}` },
  stdio: 'ignore',
});
const apiBase = `http://127.0.0.1:${API_PORT}`;
await waitHealth(apiBase);

// 2) instalar los 2 módulos (hot-plug)
await post(`${apiBase}/api/modules/install`, { dir: 'modules/inventory' });
await post(`${apiBase}/api/modules/install`, { dir: 'modules/notes' });

// 3) static + proxy /api → server (mismo origen)
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json' };
const web = createServer(async (req, res) => {
  try {
    if (req.url.startsWith('/api/')) {
      const body = await readBody(req);
      const r = await fetch(apiBase + req.url, {
        method: req.method,
        headers: { 'content-type': 'application/json', 'x-permissions': '*' },
        body: ['GET', 'HEAD'].includes(req.method) ? undefined : body || undefined,
      });
      res.writeHead(r.status, { 'content-type': 'application/json' });
      res.end(await r.text());
      return;
    }
    let p = req.url === '/' ? '/index.html' : req.url.split('?')[0];
    const data = await readFile(join(HERE, p));
    res.writeHead(200, { 'content-type': TYPES[extname(p)] || 'application/octet-stream' });
    res.end(data);
  } catch { res.writeHead(404).end('nf'); }
});
await new Promise((r) => web.listen(WEB_PORT, r));

// 4) Chrome headless + screenshots
const chrome = spawn(CHROME, ['--headless=new', `--remote-debugging-port=${DBG}`, '--no-first-run',
  '--window-size=1100,820', '--user-data-dir=/tmp/erplora-hotplug-chrome', 'about:blank']);

const cleanup = async () => { try{chrome.kill()}catch{} try{web.close()}catch{} try{srv.kill()}catch{} };
try {
  let ws;
  for (let i=0;i<40;i++){ await sleep(150); try{ const ts=await(await fetch(`http://localhost:${DBG}/json`)).json(); const pg=ts.find(t=>t.type==='page'&&t.webSocketDebuggerUrl); if(pg){ws=pg.webSocketDebuggerUrl;break;} }catch{} }
  const W=new WebSocket(ws); let id=0; const pend=new Map();
  const send=(m,p={})=>new Promise(r=>{const i=++id;pend.set(i,r);W.send(JSON.stringify({id:i,method:m,params:p}))});
  await new Promise(r=>W.onopen=r); W.onmessage=e=>{const m=JSON.parse(e.data);if(m.id&&pend.has(m.id)){pend.get(m.id)(m);pend.delete(m.id)}};
  await send('Page.enable'); await send('Runtime.enable');
  const shot=async n=>{const r=await send('Page.captureScreenshot',{format:'png'});if(r.result?.data)await writeFile(join(SHOTS,n),Buffer.from(r.result.data,'base64'))};

  await send('Page.navigate',{url:`http://127.0.0.1:${WEB_PORT}/`}); await sleep(1400);
  await shot('01-modules-all-active.png');
  // desactivar 'notes' desde la UI (clic en el botón) y recapturar
  await send('Runtime.evaluate',{expression:`document.querySelector('button[data-act="deactivate"][data-id="notes"]').click()`});
  await sleep(900);
  await shot('02-notes-deactivated.png');

  console.log('OK demo: snapshots en demos/hotplug/snapshots/ (01-modules-all-active, 02-notes-deactivated)');
  await cleanup(); process.exit(0);
} catch(e){ console.error('error',e.message); await cleanup(); process.exit(1); }

// helpers
async function waitHealth(base){ for(let i=0;i<60;i++){ await sleep(300); try{ if((await fetch(base+'/healthz')).ok) return; }catch{} } throw new Error('server no arrancó'); }
async function post(url,body){ return fetch(url,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)}); }
function readBody(req){ return new Promise(r=>{let d='';req.on('data',c=>d+=c);req.on('end',()=>r(d))}); }
