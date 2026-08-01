#!/usr/bin/env node
// Stack autónomo y real para ADR-0049: Postgres efímero → Axum → Vite → Chromium + receptor HTTP.
import { execFileSync, spawn } from 'node:child_process';
import { mkdtempSync, mkdirSync, rmSync, symlinkSync } from 'node:fs';
import { createServer } from 'node:net';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const temp = mkdtempSync(join(tmpdir(), 'erplora-edge-e2e-'));
const container = `erplora-edge-${process.pid}`;
const children = [];
let cleaning = false;

const freePort = () => new Promise((resolve, reject) => {
  const server = createServer();
  server.once('error', reject);
  server.listen(0, '127.0.0.1', () => {
    const address = server.address();
    if (!address || typeof address === 'string') return reject(new Error('sin puerto TCP'));
    server.close(() => resolve(address.port));
  });
});

function start(command, args, options) {
  const child = spawn(command, args, { ...options, stdio: ['ignore', 'pipe', 'pipe'] });
  children.push(child);
  child.stdout.pipe(process.stdout);
  child.stderr.pipe(process.stderr);
  return child;
}

async function waitFor(url, label, timeout = 120_000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch { /* aún arrancando */ }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`${label} no arrancó: ${url}`);
}

function cleanup() {
  if (cleaning) return;
  cleaning = true;
  for (const child of children) {
    if (!child.killed) child.kill('SIGTERM');
  }
  try { execFileSync('docker', ['rm', '-f', container], { stdio: 'ignore' }); } catch { /* ya terminó */ }
  rmSync(temp, { recursive: true, force: true });
}

process.on('SIGINT', () => { cleanup(); process.exit(130); });
process.on('SIGTERM', () => { cleanup(); process.exit(143); });

try {
  const runtimePort = await freePort();
  const webPort = await freePort();
  const unavailableCloudPort = await freePort();
  execFileSync('docker', [
    'run', '--detach', '--rm', '--name', container,
    '-e', 'POSTGRES_PASSWORD=postgres',
    '-p', '127.0.0.1::5432',
    'postgres:18',
  ], { stdio: 'ignore' });
  const pgPort = execFileSync(
    'docker', ['port', container, '5432/tcp'], { encoding: 'utf8' },
  ).trim().split(':').at(-1);
  for (let attempt = 0; attempt < 120; attempt += 1) {
    try {
      execFileSync('docker', ['exec', container, 'pg_isready', '-U', 'postgres'], { stdio: 'ignore' });
      break;
    } catch {
      if (attempt === 119) throw new Error('Postgres efímero no quedó listo');
      await new Promise((resolve) => setTimeout(resolve, 250));
    }
  }

  const moduleRoot = join(temp, 'modules');
  mkdirSync(moduleRoot);
  symlinkSync(join(ROOT, 'crates/server/tests/fixture_public_api'), join(moduleRoot, 'catalog'));
  const runtimeUrl = `http://127.0.0.1:${runtimePort}`;
  const webUrl = `http://127.0.0.1:${webPort}`;
  const commonEnv = {
    ...process.env,
    HUB_DATABASE_URL: `postgres://postgres:postgres@127.0.0.1:${pgPort}/postgres`,
    HUB_ID: 'playwright-edge-hub',
    HUB_BIND: `127.0.0.1:${runtimePort}`,
    HUB_CLOUD_API_URL: `http://127.0.0.1:${unavailableCloudPort}`,
    HUB_AUTH: 'session',
    HUB_DEV_MODE: '1',
    HUB_MODULES_DIR: moduleRoot,
    HUB_SEED_SQL_PATH: join(ROOT, 'crates/server/seeds/demo.sql'),
    HUB_CLOUD_API_TOKEN: 'playwright-enrolled-machine',
    HUB_SECRETS_KEY: 'BwcHBwcHBwcHBwcHBwcHBwcHBwcHBwcHBwcHBwcHBwc=',
    HUB_RUNTIME_URL: runtimeUrl,
    HUB_WEB_PORT: String(webPort),
    HUB_WEB_URL: webUrl,
    VITE_RUNTIME_URL: '',
  };

  start('cargo', ['run', '-p', 'erplora-server'], { cwd: ROOT, env: commonEnv });
  await waitFor(`${runtimeUrl}/healthz`, 'Axum');
  start('pnpm', ['exec', 'vite', '--host', '127.0.0.1', '--port', String(webPort), '--strictPort'], {
    cwd: join(ROOT, 'apps/web'),
    env: commonEnv,
  });
  await waitFor(webUrl, 'Vite');

  const playwright = start(
    'pnpm',
    ['exec', 'playwright', 'test', 'tests/e2e/IntegrationEdge.spec.ts', '--config', 'tests/playwright.config.ts'],
    { cwd: join(ROOT, 'apps/web'), env: commonEnv },
  );
  const code = await new Promise((resolve) => playwright.once('exit', (value) => resolve(value ?? 1)));
  cleanup();
  process.exit(code);
} catch (error) {
  console.error(error);
  cleanup();
  process.exit(1);
}
