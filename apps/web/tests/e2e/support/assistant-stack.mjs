import { createServer } from 'node:http';
import { spawn, spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';

const root = fileURLToPath(new URL('../../../../../', import.meta.url));
const webDir = resolve(root, 'apps/web');
const fixtureRoot = resolve(root, 'crates/server/tests');
const seed = resolve(root, 'crates/server/seeds/demo.sql');
const cloudPort = 18991;
const pgPort = 55_000 + (process.pid % 1_000);
const children = [];
let observations = { embeddings: [], assistant: [] };

function json(res, status, value) {
  res.writeHead(status, { 'content-type': 'application/json' });
  res.end(JSON.stringify(value));
}

function readJson(req) {
  return new Promise((resolveBody, reject) => {
    let raw = '';
    req.on('data', (chunk) => { raw += chunk; });
    req.on('end', () => {
      try { resolveBody(raw ? JSON.parse(raw) : {}); } catch (error) { reject(error); }
    });
    req.on('error', reject);
  });
}

const cloud = createServer(async (req, res) => {
  if (req.url === '/__observations' && req.method === 'GET') return json(res, 200, observations);
  if (req.url === '/__reset' && req.method === 'POST') {
    observations = { embeddings: [], assistant: [] };
    return json(res, 200, { ok: true });
  }
  if (req.url === '/__shutdown' && req.method === 'POST') {
    // Playwright may terminate its webServer immediately after this response. Remove the exact
    // disposable container synchronously first, so even a hard process-group shutdown leaves no
    // Postgres behind.
    if (dockerName) {
      spawnSync('docker', ['rm', '-f', dockerName], { stdio: 'ignore' });
      dockerName = null;
    }
    json(res, 200, { ok: true });
    setTimeout(() => void shutdown(0), 25);
    return;
  }
  if (req.url === '/api/v1/auth/public-key/') return json(res, 404, { error: 'not needed for PIN' });

  const body = await readJson(req).catch(() => null);
  if (!body) return json(res, 400, { error: 'invalid json' });
  const headers = {
    hubId: req.headers['x-hub-id'] ?? null,
    hubToken: req.headers['x-hub-token'] ?? null,
  };

  if (req.url === '/api/v1/hub/device/assistant/embeddings/' && req.method === 'POST') {
    observations.embeddings.push({ body, headers });
    const texts = Array.isArray(body.texts) ? body.texts : [];
    return json(res, 200, { embeddings: texts.map(() => [1, 0, 0]), model: 'e2e-fixed' });
  }

  if (req.url === '/api/v1/hub/device/assistant/chat/stream/' && req.method === 'POST') {
    observations.assistant.push({ body, headers });
    const messages = Array.isArray(body.messages) ? body.messages : [];
    const hasToolResult = messages.some((message) => message.role === 'tool');
    const input = typeof body.input === 'string' ? body.input : '';
    res.writeHead(200, { 'content-type': 'text/event-stream', 'cache-control': 'no-cache' });
    if (hasToolResult) {
      const answer = input.startsWith('CREATE ') ? 'Marcador creado por el runtime real.' : 'Marcador encontrado por el runtime real.';
      res.end(`data: ${JSON.stringify({ type: 'token', text: answer })}\n\ndata: [DONE]\n\n`);
      return;
    }
    if (input.startsWith('CREATE ')) {
      const name = input.slice('CREATE '.length);
      // Deliberadamente falso: Axum debe sobrescribirlo con el kind del catálogo (command).
      res.end(`data: ${JSON.stringify({ type: 'function_call', name: 'assistant_fixture.item.create', call_id: 'create-1', arguments: JSON.stringify({ name }), kind: 'query' })}\n\ndata: [DONE]\n\n`);
      return;
    }
    if (input.startsWith('FIND ')) {
      const name = input.slice('FIND '.length);
      // Deliberadamente falso: una query nunca debe convertirse en command por dato del Cloud.
      res.end(`data: ${JSON.stringify({ type: 'function_call', name: 'assistant_fixture.items.find', call_id: 'find-1', arguments: JSON.stringify({ name }), kind: 'command' })}\n\ndata: [DONE]\n\n`);
      return;
    }
    res.end(`data: ${JSON.stringify({ type: 'token', text: 'Sin herramientas activas.' })}\n\ndata: [DONE]\n\n`);
    return;
  }
  json(res, 404, { error: 'not mocked' });
});

function run(command, args, options = {}) {
  const child = spawn(command, args, { stdio: 'inherit', ...options });
  children.push(child);
  child.on('exit', (code, signal) => {
    if (!shuttingDown && code !== 0) {
      console.error(`${command} exited early (${code ?? signal})`);
      void shutdown(1);
    }
  });
  return child;
}

let dockerName = null;
let shuttingDown = false;
async function waitFor(url, timeoutMs = 120_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok || response.status < 500) return;
    } catch { /* process is still starting */ }
    await new Promise((resolveWait) => setTimeout(resolveWait, 250));
  }
  throw new Error(`timeout waiting for ${url}`);
}

async function provisionDatabase() {
  if (process.env.HUB_E2E_DATABASE_URL) return process.env.HUB_E2E_DATABASE_URL;
  dockerName = `erplora-assistant-e2e-${process.pid}`;
  const started = spawnSync('docker', [
    'run', '--rm', '-d', '--name', dockerName, '-e', 'POSTGRES_PASSWORD=postgres',
    '-e', 'POSTGRES_DB=erplora_assistant_e2e', '-p', `${pgPort}:5432`, 'postgres:16-alpine',
  ], { stdio: 'inherit' });
  if (started.status !== 0) throw new Error('could not start disposable Postgres');
  const deadline = Date.now() + 60_000;
  while (Date.now() < deadline) {
    const probe = spawn('docker', ['exec', dockerName, 'pg_isready', '-U', 'postgres'], { stdio: 'ignore' });
    const code = await new Promise((resolveCode) => probe.on('exit', resolveCode));
    if (code === 0) return `postgres://postgres:postgres@127.0.0.1:${pgPort}/erplora_assistant_e2e`;
    await new Promise((resolveWait) => setTimeout(resolveWait, 250));
  }
  throw new Error('Postgres E2E did not become ready');
}

async function shutdown(code = 0) {
  if (shuttingDown) return;
  shuttingDown = true;
  cloud.close();
  for (const child of children) child.kill('SIGTERM');
  if (dockerName) {
    const stop = spawn('docker', ['rm', '-f', dockerName], { stdio: 'ignore' });
    await new Promise((resolveStop) => stop.on('exit', resolveStop));
  }
  process.exit(code);
}

process.on('SIGINT', () => void shutdown(0));
process.on('SIGTERM', () => void shutdown(0));
process.on('exit', () => {
  if (dockerName) spawnSync('docker', ['rm', '-f', dockerName], { stdio: 'ignore' });
});

cloud.listen(cloudPort, '127.0.0.1');
const databaseUrl = await provisionDatabase();
run('cargo', ['run', '-p', 'erplora-server'], {
  cwd: root,
  env: {
    ...process.env,
    HUB_DATABASE_URL: databaseUrl,
    HUB_BIND: '127.0.0.1:8787',
    HUB_AUTH: 'session',
    HUB_ID: 'assistant-e2e-hub',
    HUB_DEV_MODE: '1',
    HUB_MODULE_CACHE: fixtureRoot,
    HUB_SEED_SQL_PATH: seed,
    HUB_CLOUD_API_URL: `http://127.0.0.1:${cloudPort}`,
    HUB_CLOUD_API_TOKEN: 'assistant-e2e-token',
    HUB_ASSISTANT_ROUTE_TOP_K: '1',
    HUB_ASSISTANT_ROUTE_MIN_MODULES: '1',
  },
});
run('pnpm', ['exec', 'vite', '--host', '127.0.0.1', '--port', '5173'], { cwd: webDir, env: process.env });
await Promise.all([
  waitFor('http://127.0.0.1:8787/healthz'),
  waitFor('http://127.0.0.1:5173'),
]);
console.log('assistant E2E stack ready');
await new Promise(() => {});
