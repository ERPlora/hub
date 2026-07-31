#!/usr/bin/env node
// Arranque turnkey del Hub local (dev): levanta EL runtime (Axum, crates/server) y EL shell web
// (Vite, apps/web) con un solo comando — `pnpm dev` desde la raíz de hub/. Sin dependencias npm
// extra (orquestador a mano sobre child_process); pensado para QA/UI E2E del POS.
//
// Qué hace:
//   1. Fija defaults de entorno sensatos para dev (Postgres local, módulos del workspace de dev,
//      bind 127.0.0.1:8787) — todo sobreescribible exportando la variable antes de invocar.
//   2. Lanza `cargo run -p erplora-server` (runtime + API + WS en :8787; instala los módulos de
//      HUB_MODULES_DIR al arrancar, topo-ordenando depends_on).
//   3. Lanza `pnpm -F @erplora/web dev` (Vite :5173; su predev sincroniza los WC de los módulos a
//      public/modules/**). El shell pega al runtime vía el proxy de Vite (/api + /ws → :8787).
//   4. Prefija la salida de cada proceso y los baja juntos: Ctrl-C (o que uno muera) mata al otro.
//
// El runtime y el web se descubren por convención de puertos (VITE_RUNTIME_URL='' → el shell usa
// el proxy de Vite, ver apps/web/.env.local y vite.config.ts), así que no hace falta cablear nada
// más. En prod NO se usa esto: el runtime (crates/server) sirve también el dist de Vite (HUB_WEB_DIR)
// y los módulos vienen del marketplace, no de un dir local.

import { spawn } from 'node:child_process';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const HUB_ROOT = join(HERE, '..');
const MONOREPO_ROOT = join(HUB_ROOT, '..');

// Defaults de dev (sobreescribibles: si la variable ya está exportada, se respeta).
const DEFAULTS = {
  // Postgres-only (ADR-0154): el runtime falla duro sin DSN. Default local para `pnpm dev`
  // (crea la BD con `createdb erplora_hub_dev`); sobreescribible exportando HUB_DATABASE_URL.
  HUB_DATABASE_URL: 'postgres://localhost/erplora_hub_dev',
  // Fuente de módulos de dev = el workspace del toolkit en el root del monorepo. El runtime los
  // instala al arrancar (los mismos que apps/web carga como WebComponents vía sync-modules.mjs).
  HUB_MODULES_DIR: join(MONOREPO_ROOT, 'modules-workspace', 'modules'),
  // Bind del runtime Axum.
  HUB_BIND: '127.0.0.1:8787',
  // Auth en modo sesión server-side (el ÚNICO flujo del frontend: login cloud/PIN → X-Hub-Session).
  // Con `HUB_AUTH=dev` el runtime no descarga la clave pública del Cloud y `/api/auth/cloud`
  // devuelve 503 ("login cloud no disponible (sin clave pública)") → la pantalla de login no funciona.
  // Desde hub#241 `session` es además el DEFAULT del runtime (fail-closed): el modo permisivo
  // (`dev`, que se cree las cabeceras X-User-Id/X-Permissions del navegador) hay que pedirlo
  // explícitamente con `HUB_AUTH=dev`. Aquí se deja fijado para que quede a la vista.
  HUB_AUTH: 'session',
  // Seed de dev: usuario "Demo" (PIN 0000) + dispositivo de confianza, para que el login local por
  // PIN funcione sin enrolar online (ADR-0065). Sin esto un arranque fresco no tiene usuario con PIN
  // y la pantalla de login no deja entrar. En prod/ECS el seed llega por HUB_SEED_SQL (terraform).
  HUB_SEED_SQL_PATH: join(HUB_ROOT, 'crates', 'server', 'seeds', 'demo.sql'),
};

const env = { ...process.env };
for (const [k, v] of Object.entries(DEFAULTS)) {
  if (!env[k]) env[k] = v;
}
// El shell web pega al runtime por el proxy de Vite (mismo origen :5173 → /api + /ws). Forzamos el
// default solo si no se ha fijado, para no pisar un override deliberado.
if (env.VITE_RUNTIME_URL === undefined) env.VITE_RUNTIME_URL = '';

const procs = [
  {
    name: 'runtime',
    color: '\x1b[36m', // cyan
    cmd: 'cargo',
    args: ['run', '-p', 'erplora-server'],
    cwd: HUB_ROOT,
  },
  {
    name: 'web',
    color: '\x1b[35m', // magenta
    cmd: 'pnpm',
    args: ['-F', '@erplora/web', 'dev'],
    cwd: HUB_ROOT,
  },
];

const RESET = '\x1b[0m';
const children = [];
let shuttingDown = false;

function log(name, color, line) {
  if (line.length === 0) return;
  process.stdout.write(`${color}[${name}]${RESET} ${line}\n`);
}

function pipe(name, color, stream) {
  let buf = '';
  stream.setEncoding('utf8');
  stream.on('data', (chunk) => {
    buf += chunk;
    const lines = buf.split('\n');
    buf = lines.pop() ?? '';
    for (const l of lines) log(name, color, l);
  });
  stream.on('end', () => {
    if (buf) log(name, color, buf);
  });
}

function shutdown(reason) {
  if (shuttingDown) return;
  shuttingDown = true;
  if (reason) process.stdout.write(`\n${reason}\n`);
  for (const c of children) {
    if (!c.killed) {
      try {
        c.kill('SIGTERM');
      } catch {
        /* ya muerto */
      }
    }
  }
  // Margen para terminar limpio; luego salimos.
  setTimeout(() => process.exit(reason ? 1 : 0), 1500);
}

log('dev', '\x1b[32m', `HUB_DATABASE_URL=${env.HUB_DATABASE_URL}`);
log('dev', '\x1b[32m', `HUB_MODULES_DIR=${env.HUB_MODULES_DIR}`);
log('dev', '\x1b[32m', `HUB_BIND=${env.HUB_BIND}  VITE_RUNTIME_URL='${env.VITE_RUNTIME_URL}'`);
log('dev', '\x1b[32m', 'runtime → http://127.0.0.1:8787   web → http://localhost:5173');

for (const p of procs) {
  const child = spawn(p.cmd, p.args, {
    cwd: p.cwd,
    env,
    stdio: ['inherit', 'pipe', 'pipe'],
  });
  children.push(child);
  pipe(p.name, p.color, child.stdout);
  pipe(p.name, p.color, child.stderr);
  child.on('error', (err) => {
    log(p.name, p.color, `error al lanzar: ${err.message}`);
    shutdown(`✗ ${p.name} no pudo arrancar`);
  });
  child.on('exit', (code, signal) => {
    if (shuttingDown) return;
    shutdown(`✗ ${p.name} terminó (code=${code ?? '-'} signal=${signal ?? '-'}) → bajando el resto`);
  });
}

for (const sig of ['SIGINT', 'SIGTERM']) {
  process.on(sig, () => shutdown(`\n${sig} recibido → bajando runtime + web`));
}
