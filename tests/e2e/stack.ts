// Where the browser PoC finds the dev stack. The shared one is runserver on :8000, its Vite on :5173,
// the SaaS on :8001 and the database `hub`; a branch checked out beside it (another session's
// runserver keeps :8000) starts its own with other ports and its own database, and points the specs
// at it with the same variables Django and Vite read: `E2E_HUB_PORT` (runserver's port, only the
// specs need it), `VITE_DEV_PORT` (`config/settings.py`, `vite.config.ts`), `SAAS_URL` and `DB_NAME`
// (`config/settings.py`). runserver restarted by a spec (`startRunserver`) inherits them.

type Env = Record<string, string | undefined>;

export interface Stack {
  /** runserver's port (`E2E_HUB_PORT`). */
  hubPort: number;
  /** Its Vite's port (`VITE_DEV_PORT`). */
  vitePort: number;
  /** The SaaS's origin, where every login goes (`SAAS_URL`). */
  saas: string;
  /** The hub's database, for `psql` (`DB_NAME`). */
  database: string;
  /** `http://127.0.0.1:<hubPort>/healthz`. */
  healthz: string;
  /** Vite's client module: it answers once Vite listens. */
  viteClient: string;
  /** The origin of the hub `slug`: `http://<slug>.localhost:<hubPort>`. */
  hub(slug: string): string;
}

function port(env: Env, name: string, fallback: number): number {
  const raw = env[name];
  if (raw === undefined || raw === '') return fallback;
  const value = Number(raw);
  if (!/^\d+$/.test(raw) || value <= 0 || value >= 65536) {
    throw new Error(`${name} must be a TCP port, not ${JSON.stringify(raw)}.`);
  }
  return value;
}

function origin(env: Env, name: string, fallback: string): string {
  const raw = env[name] || fallback;
  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    throw new Error(`${name} must be an http origin, not ${JSON.stringify(raw)}.`);
  }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') {
    throw new Error(`${name} must be an http origin, not ${JSON.stringify(raw)}.`);
  }
  return url.origin;
}

function database(env: Env, name: string, fallback: string): string {
  const raw = env[name] || fallback;
  // It goes into a shell command (`psql -d …`) as is.
  if (!/^[a-z_][a-z0-9_]*$/.test(raw)) {
    throw new Error(`${name} must be a plain database name, not ${JSON.stringify(raw)}.`);
  }
  return raw;
}

export function stackFrom(env: Env): Stack {
  const hubPort = port(env, 'E2E_HUB_PORT', 8000);
  const vitePort = port(env, 'VITE_DEV_PORT', 5173);
  return {
    hubPort,
    vitePort,
    saas: origin(env, 'SAAS_URL', 'http://localhost:8001'),
    database: database(env, 'DB_NAME', 'hub'),
    healthz: `http://127.0.0.1:${hubPort}/healthz`,
    viteClient: `http://localhost:${vitePort}/static/spa/@vite/client`,
    hub: (slug: string) => `http://${slug}.localhost:${hubPort}`,
  };
}

/** The stack of this run, from its environment. */
export const STACK = stackFrom(process.env);
