#!/usr/bin/env node
// E2E autónomo de contratos host↔módulo (hub#70/#139): Postgres efímero, Axum y Vite reales,
// y Playwright Chromium. La auth de prueba es EXPLÍCITA (`HUB_AUTH=dev`) y cada llamada manda
// X-Hub-Id/X-User-Id/X-Permissions; la receta no reutiliza sesiones ni servicios previos.

import { spawn, spawnSync } from 'node:child_process';
import { existsSync, mkdtempSync, rmSync, symlinkSync } from 'node:fs';
import { createServer } from 'node:net';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const HUB_ROOT = join(HERE, '..');
const MONOREPO_ROOT = join(HUB_ROOT, '..');
const DEV_HUB_ID = '00000000-0000-0000-0000-000000000001';
const modulesDir = mkdtempSync(join(tmpdir(), 'erplora-runtime-contracts-'));
const schedulesDir = process.env.ERPLORA_SCHEDULES_MODULE_DIR
  ?? join(MONOREPO_ROOT, 'modules-workspace', 'modules', 'schedules');
const taxesDir = process.env.ERPLORA_TAXES_MODULE_DIR
  ?? join(MONOREPO_ROOT, 'modules-workspace', 'modules', 'taxes');
const inventoryDir = process.env.ERPLORA_INVENTORY_MODULE_DIR
  ?? join(MONOREPO_ROOT, 'modules-workspace', 'modules', 'inventory');
const customersDir = process.env.ERPLORA_CUSTOMERS_MODULE_DIR
  ?? join(MONOREPO_ROOT, 'modules-workspace', 'modules', 'customers');
const salesDir = process.env.ERPLORA_SALES_MODULE_DIR
  ?? join(MONOREPO_ROOT, 'modules-workspace', 'modules', 'sales');
const w140Dir = join(HUB_ROOT, 'crates', 'runtime', 'tests', 'fixture_w140');
const children = [];
let postgresContainer = null;
let cleaning = false;

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: HUB_ROOT,
    env: process.env,
    stdio: 'inherit',
    ...options,
  });
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(`${command} terminó con código ${result.status}`);
}

function capture(command, args) {
  const result = spawnSync(command, args, { cwd: HUB_ROOT, encoding: 'utf8' });
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(result.stderr || `${command} falló`);
  return result.stdout.trim();
}

function start(name, command, args, env) {
  const child = spawn(command, args, {
    cwd: HUB_ROOT,
    env,
    stdio: 'inherit',
    detached: true,
  });
  child.on('exit', (code, signal) => {
    if (!cleaning && code !== null && code !== 0) {
      console.error(`✗ ${name} terminó antes de tiempo (code=${code}, signal=${signal ?? '-'})`);
    }
  });
  children.push(child);
}

function freePort() {
  return new Promise((resolve, reject) => {
    const server = createServer();
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const address = server.address();
      if (!address || typeof address === 'string') {
        server.close();
        reject(new Error('no se pudo reservar un puerto local para el E2E'));
        return;
      }
      server.close((error) => error ? reject(error) : resolve(address.port));
    });
  });
}

async function waitFor(url, label, timeoutMs = 120_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch {
      // El proceso todavía está arrancando.
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`${label} no respondió en ${url} tras ${timeoutMs / 1000}s`);
}

function cleanup() {
  if (cleaning) return;
  cleaning = true;
  for (const child of children.reverse()) {
    if (!child.pid) continue;
    try {
      process.kill(-child.pid, 'SIGTERM');
    } catch {
      // Ya terminó.
    }
  }
  if (postgresContainer) {
    spawnSync('docker', ['rm', '-f', postgresContainer], { stdio: 'ignore' });
  }
  rmSync(modulesDir, { recursive: true, force: true });
}

for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, () => {
    cleanup();
    process.exit(130);
  });
}

try {
  for (const [name, path] of [
    ['taxes', taxesDir],
    ['inventory', inventoryDir],
    ['customers', customersDir],
    ['sales', salesDir],
    ['schedules', schedulesDir],
    ['w140', w140Dir],
  ]) {
    if (!existsSync(join(path, 'module.json'))) throw new Error(`falta el módulo ${name}: ${path}`);
    symlinkSync(path, join(modulesDir, name), 'dir');
  }

  let databaseUrl = process.env.HUB_RUNTIME_CONTRACT_DATABASE_URL;
  if (!databaseUrl) {
    postgresContainer = `erplora-runtime-contracts-${process.pid}`;
    run('docker', [
      'run', '--detach', '--rm', '--name', postgresContainer,
      '--env', 'POSTGRES_PASSWORD=test', '--env', 'POSTGRES_DB=hub_e2e',
      '--publish', '127.0.0.1::5432', 'postgres:18-alpine',
    ]);
    const portLine = capture('docker', ['port', postgresContainer, '5432/tcp']);
    const port = portLine.split(':').at(-1);
    if (!port) throw new Error(`docker no devolvió el puerto de Postgres: ${portLine}`);
    const deadline = Date.now() + 60_000;
    let postgresReady = false;
    while (Date.now() < deadline) {
      const ready = spawnSync(
        'docker', ['exec', postgresContainer, 'pg_isready', '-U', 'postgres', '-d', 'hub_e2e'],
        { stdio: 'ignore' },
      );
      if (ready.status === 0) {
        postgresReady = true;
        break;
      }
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
    if (!postgresReady) throw new Error('Postgres efímero no quedó listo tras 60s');
    databaseUrl = `postgres://postgres:test@127.0.0.1:${port}/hub_e2e`;
  }

  console.log('→ compilando Axum');
  run('cargo', ['build', '-p', 'erplora-server']);

  // Puertos dedicados: la receta puede correr en paralelo con otros worktrees/servidores.
  const [runtimePort, webPort] = await Promise.all([freePort(), freePort()]);
  const runtimeUrl = `http://127.0.0.1:${runtimePort}`;
  const webUrl = `http://127.0.0.1:${webPort}`;

  const env = {
    ...process.env,
    HUB_DATABASE_URL: databaseUrl,
    HUB_BIND: `127.0.0.1:${runtimePort}`,
    HUB_ID: DEV_HUB_ID,
    HUB_AUTH: 'dev',
    HUB_DEV_MODE: '1',
    HUB_MODULES_DIR: modulesDir,
    HUB_RUNTIME_URL: runtimeUrl,
    VITE_RUNTIME_URL: '',
  };
  console.log('→ arrancando Axum con HUB_AUTH=dev (solo esta receta de test)');
  start('runtime', join(HUB_ROOT, 'target', 'debug', 'erplora-server'), [], env);
  start(
    'vite',
    'pnpm',
    [
      '--filter', '@erplora/web', 'exec', 'vite', '--host', '127.0.0.1',
      '--port', String(webPort), '--strictPort',
    ],
    env,
  );
  await Promise.all([
    waitFor(`${runtimeUrl}/healthz`, 'Axum'),
    waitFor(webUrl, 'Vite'),
  ]);

  console.log('→ Playwright: navegador → SDK → HTTP → Axum → WASM/SQL → Postgres');
  run(
    'pnpm',
    [
      '--filter', '@erplora/web', 'exec', 'playwright', 'test',
      'tests/e2e/ModuleRuntimeContracts.spec.ts', '--config', 'tests/playwright.config.ts',
    ],
    {
      env: {
        ...env,
        HUB_RUNTIME_CONTRACT_E2E: '1',
        HUB_RUNTIME_URL: runtimeUrl,
        HUB_WEB_URL: webUrl,
      },
    },
  );
} finally {
  cleanup();
}
