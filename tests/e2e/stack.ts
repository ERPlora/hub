// Where the browser PoC finds the dev stack. The shared one is runserver on :8000, its Vite on :5173,
// the SaaS on :8001 and the database `hub`; a branch checked out beside it (another session's
// runserver keeps :8000) starts its own with other ports and its own database, and points the specs
// at it with the same variables Django and Vite read: `E2E_HUB_PORT` (runserver's port, only the
// specs need it), `VITE_DEV_PORT` (`config/settings.py`, `vite.config.ts`), `SAAS_URL` and `DB_NAME`
// (`config/settings.py`). runserver restarted by a spec (`startRunserver`) inherits them. Its SaaS keeps its accounts
// in `saasDatabase` (`E2E_SAAS_DB`, by default `saas` on :8000 and `saas_e2e_<port + 1>` beside it).
//
// A stack beside the shared one runs on its own e2e database (`hub_e2e_<port>`, `database.ts` creates
// and migrates it): on 2026-10-16 two stacks (8030 and 8040) ran on the default `hub` and the cash sale
// of one fell into the other's open shift. Phase 1 keeps every hub's business in that one database, so
// `DB_NAME` is all a run needs to be on its own; without it, or with `hub`, the run is refused.

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
  /** The SaaS's database, where its demo accounts live: `E2E_SAAS_DB`, else `saas` beside the shared Hub on :8000 and
   *  `saas_e2e_<hubPort + 1>` for a stack of its own (README «Varias ejecuciones a la vez»). */
  saasDatabase: string;
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

/** runserver's port and database of the shared dev stack. */
const SHARED_PORT = 8000;
const SHARED_DATABASE = 'hub';

/** An e2e database: `hub_…` with `e2e` as one of its words (`hub_e2e_8030`, `hub_fix_e2e_a`). The only kind
 *  a stack beside the shared one runs on, and the only kind `database.ts` creates, migrates or drops. */
export function isE2eDatabase(name: string): boolean {
  return /^hub(?:_[a-z0-9]+)*_e2e(?:_[a-z0-9]+)*$/.test(name);
}

function database(env: Env, name: string, fallback: string): string {
  const raw = env[name] || fallback;
  // It goes into a shell command (`psql -d …`) as is.
  if (!/^[a-z_][a-z0-9_]*$/.test(raw)) {
    throw new Error(`${name} must be a plain database name, not ${JSON.stringify(raw)}.`);
  }
  return raw;
}

/** The run's database: the stack beside the shared one gets its own e2e database, or nothing runs. */
function databaseOf(env: Env, hubPort: number): string {
  const name = database(env, 'DB_NAME', SHARED_DATABASE);
  if (hubPort === SHARED_PORT || isE2eDatabase(name)) return name;
  const own = `hub_e2e_${hubPort}`;
  const given = env.DB_NAME ? `DB_NAME=${name}` : `the shared ${SHARED_DATABASE} (DB_NAME unset)`;
  throw new Error(
    `A stack beside the shared one (E2E_HUB_PORT=${hubPort}) runs on its own e2e database, not on ${given}: ` +
      `another run would write into it. Export DB_NAME=${own} for its runserver and its e2e, and create it with ` +
      `\`DB_NAME=${own} node tests/e2e/database.ts\` before starting runserver (tests/e2e/README.md).`,
  );
}

export function stackFrom(env: Env): Stack {
  const hubPort = port(env, 'E2E_HUB_PORT', SHARED_PORT);
  const vitePort = port(env, 'VITE_DEV_PORT', 5173);
  return {
    hubPort,
    vitePort,
    saas: origin(env, 'SAAS_URL', 'http://localhost:8001'),
    database: databaseOf(env, hubPort),
    saasDatabase: database(env, 'E2E_SAAS_DB', hubPort === SHARED_PORT ? 'saas' : `saas_e2e_${hubPort + 1}`),
    healthz: `http://127.0.0.1:${hubPort}/healthz`,
    viteClient: `http://localhost:${vitePort}/static/spa/@vite/client`,
    hub: (slug: string) => `http://${slug}.localhost:${hubPort}`,
  };
}

/** The stack of this run, from its environment. */
export const STACK = stackFrom(process.env);
