// The dev server the specs run on (runserver + Vite): who listens on a port, whether it answers, starting runserver
// again and the connection it keeps listening on the run's database.
import { execSync, spawn } from 'node:child_process';

import { HUB_DIR, REPO_DIR } from './helpers';
import { STACK } from './stack';

const RUNSERVER_LOG = `/tmp/erplora-hub-runserver-${STACK.hubPort}.log`;

/** Pids LISTENING on a TCP port (never the browser's client sockets). */
export function listeningPids(port: number): number[] {
  try {
    return execSync(`lsof -ti tcp:${port} -sTCP:LISTEN`, { encoding: 'utf8' })
      .split(/\s+/)
      .filter(Boolean)
      .map(Number);
  } catch {
    return [];
  }
}

export async function healthy(): Promise<boolean> {
  try {
    const res = await fetch(STACK.healthz, { signal: AbortSignal.timeout(1500) });
    return res.ok;
  } catch {
    return false;
  }
}

/**
 * runserver's Vite (`pnpm run dev` in hub-next) answers. It starts after Django: `healthy()` alone
 * lets a page load HTML whose module scripts point at a Vite that is not listening yet, and that page
 * stays blank (nothing retries a failed module script).
 */
export async function viteReady(): Promise<boolean> {
  try {
    const res = await fetch(STACK.viteClient, { signal: AbortSignal.timeout(1500) });
    return res.ok;
  } catch {
    return false;
  }
}

export async function waitFor(check: () => Promise<boolean> | boolean, timeoutMs: number, stepMs = 250): Promise<number> {
  const start = Date.now();
  for (;;) {
    if (await check()) return Date.now() - start;
    if (Date.now() - start > timeoutMs) throw new Error(`condition not met within ${timeoutMs} ms`);
    await new Promise((r) => setTimeout(r, stepMs));
  }
}

/**
 * Starts `manage.py runserver 127.0.0.1:<E2E_HUB_PORT>` detached (it outlives the test run), with this
 * run's environment (`VITE_DEV_PORT`, `SAAS_URL`, `DB_NAME`).
 */
export function startRunserver(): void {
  const child = spawn(
    '/bin/bash',
    ['-c', `cd '${HUB_DIR}' && nohup uv run python manage.py runserver 127.0.0.1:${STACK.hubPort} >> ${RUNSERVER_LOG} 2>&1 &`],
    { detached: true, stdio: 'ignore' },
  );
  child.unref();
}

/**
 * Rows of `pg_stat_activity` named `live-listener` (the process-level LISTEN connection) on this run's
 * database: another stack beside it (another checkout's runserver) has its own.
 */
export function listenerRows(): { pid: number; backend_start: string }[] {
  const out = execSync(
    `docker compose exec -T postgres psql -U hub -d ${STACK.database} -At -F '|' -c "select pid, backend_start from pg_stat_activity where application_name='live-listener' and datname = current_database() order by pid"`,
    { cwd: REPO_DIR, encoding: 'utf8' },
  );
  return out
    .split('\n')
    .filter(Boolean)
    .map((line) => {
      const [pid, start] = line.split('|');
      return { pid: Number(pid), backend_start: start };
    });
}
