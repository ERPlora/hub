import { createServer } from 'node:http';
import { spawn, spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';

const root = fileURLToPath(new URL('../../../../../', import.meta.url));
const webDir = resolve(root, 'apps/web');
const fixtureRoot = resolve(root, 'crates/server/tests');
const seed = resolve(root, 'crates/server/seeds/demo.sql');
const port = (name, fallback) => {
  const value = Number(process.env[name] ?? fallback);
  if (!Number.isInteger(value) || value < 1 || value > 65_535) throw new Error(`${name} inválido`);
  return value;
};
const cloudPort = port('ASSISTANT_E2E_CLOUD_PORT', 18991);
const pgPort = port('ASSISTANT_E2E_PG_PORT', 55432);
const runtimePort = port('ASSISTANT_E2E_RUNTIME_PORT', 8787);
const webPort = port('ASSISTANT_E2E_WEB_PORT', 5173);
const children = [];
let observations = { embeddings: [], assistant: [] };

function inspectIndex() {
  const sql = "SELECT ref_id, source, version FROM knowledge_chunk WHERE hub_id = 'assistant-e2e-hub' ORDER BY ref_id, source";
  const command = dockerName
    ? ['docker', ['exec', dockerName, 'psql', '-U', 'postgres', '-d', 'erplora_assistant_e2e', '-At', '-F', '\t', '-c', sql]]
    : ['psql', [databaseUrl, '-At', '-F', '\t', '-c', sql]];
  const result = spawnSync(command[0], command[1], { encoding: 'utf8' });
  if (result.status !== 0) throw new Error(result.stderr || 'no se pudo inspeccionar knowledge_chunk');
  return result.stdout.trim().split('\n').filter(Boolean).map((line) => {
    const [refId, source, version] = line.split('\t');
    return { refId, source, version };
  });
}

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
  if (req.url === '/__index' && req.method === 'GET') {
    try { return json(res, 200, { rows: inspectIndex() }); }
    catch (error) { return json(res, 500, { error: String(error) }); }
  }
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

const databaseUrl = await provisionDatabase();
await new Promise((resolveListen, reject) => {
  cloud.once('error', reject);
  cloud.listen(cloudPort, '127.0.0.1', resolveListen);
});
run('cargo', ['run', '-p', 'erplora-server'], {
  cwd: root,
  env: {
    ...process.env,
    HUB_DATABASE_URL: databaseUrl,
    HUB_BIND: `127.0.0.1:${runtimePort}`,
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
run('pnpm', ['exec', 'vite', '--host', '127.0.0.1', '--port', String(webPort), '--strictPort'], {
  cwd: webDir,
  env: { ...process.env, VITE_RUNTIME_PROXY_TARGET: `http://127.0.0.1:${runtimePort}` },
});
await Promise.all([
  waitFor(`http://127.0.0.1:${runtimePort}/healthz`),
  waitFor(`http://127.0.0.1:${webPort}`),
]);
console.log('assistant E2E stack ready');
await new Promise(() => {});
