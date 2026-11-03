// The e2e's start: it refuses local databases with unapplied migrations before the first spec. On
// 2026-10-16 the local `hub` lacked verifactu.0003–0005 and the specs failed with «not valid JSON» (the
// `post` helper got Django's HTML error page), a red that never said its cause. It checks the control
// database (`migrate --check`) and the hub databases (`migrate_hubs --check`; phase 1: the control
// database again) of the run's `DB_NAME` (`stack.ts`), and never migrates: other sessions share them.
// A stack's own e2e database that does not exist yet is said as such, with `database.ts`, which creates
// it (runserver cannot start without it, so the e2e cannot create it here). Then it checks that the local
// hubs `a` and `b` are ready in the registry (`seed_local_hubs --check`; without them every host is a 404), and last
// that the stack's SaaS has the demo accounts the specs sign in with (`demo_seed` of the SaaS; one select on its
// database, `STACK.saasDatabase`): on its fresh e2e database it has none, and every login failed on «The email address
// and/or password you specified are not correct.» after 30 s (2026-10-28). The command it offers is erplora.com's
// WhatsApp seed with this Hub's ids of `a` and `b`, never `demo_seed` alone, whose own ids that seed refuses.
// Before all that it refuses more than one worker: `--workers=N` overrides `workers: 1` of playwright.config.ts, and
// specs running at once on the one stack delete each other's data (2026-10-23: the agenda spec timed out).
// Once every check passes it starts this checkout's `manage.py run_worker --databases-only` on the run's databases
// (round 2026-10-30 of PLAN-DB, S2a: a business or a demo registered during the run is `requested` until the worker
// makes its database; the specs play the relay and the tasks themselves) and
// hands Playwright its stop as the run's teardown; a worker that never waits for work stops the run with what it said.
import { type ChildProcess, spawn as spawnProcess, spawnSync } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import type { FullConfig } from '@playwright/test';

import { isE2eDatabase, type Stack, STACK } from './stack.ts';

const HERE = dirname(fileURLToPath(import.meta.url));
const HUB_DIR = resolve(HERE, '..', '..');
/** Where compose.yaml lives: the root of erplora-next, above hub/ and every hub-wt-*. */
const REPO_DIR = resolve(HUB_DIR, '..');

/** What a `manage.py` command left: its exit status (`null` when it never ran or was killed) and output. */
export interface CommandResult {
  status: number | null;
  stdout: string;
  stderr: string;
}

/** Runs `manage.py` with `args` against the e2e's local databases. */
export type ManagePy = (args: string[]) => CommandResult;

/** `spawnSync` as `managePy` calls it. */
export type Spawn = (
  command: string,
  args: string[],
  options: { cwd: string; encoding: 'utf8'; env: NodeJS.ProcessEnv },
) => { status: number | null; stdout: string | null; stderr: string | null; error?: Error };

/** Each exits 1, listing what a run would apply, if anything is pending, and applies nothing. */
const CHECKS = [
  ['migrate', '--check', '--plan', '--no-color'],
  ['migrate_hubs', '--check', '--no-color'],
];

/** The migrations a check listed: its unindented `<app>.<migration>` lines (`--plan` indents the operations). */
function listedMigrations(output: string): string[] {
  return output.split(/\r?\n/).filter((line) => /^[A-Za-z_]\w*\.\w+$/.test(line));
}

/** Throws, without touching the databases, unless both checks find every migration applied. */
export function assertMigrationsApplied(manage: ManagePy, database: string): void {
  const where = `local databases of the e2e (DB_NAME=${database})`;
  for (const args of CHECKS) {
    const check = manage(args);
    if (check.status === 0) continue;
    const command = `manage.py ${args.join(' ')}`;
    const pending = listedMigrations(check.stdout);
    if (pending.length > 0) {
      const fix = ['migrate', 'migrate_hubs']
        .map((name) => `DB_NAME=${database} uv run python manage.py ${name}`)
        .join(' && ');
      throw new Error(
        `The ${where} have unapplied migrations (${pending.join(', ')}). ` +
          `Run \`${fix}\` from this checkout and retry.\n\n${command}:\n${check.stdout.trim()}`,
      );
    }
    const output = [check.stdout.trim(), check.stderr.trim()].filter(Boolean).join('\n');
    if (isE2eDatabase(database) && output.includes(`database "${database}" does not exist`)) {
      throw new Error(
        `The database of the e2e (DB_NAME=${database}) does not exist. Create and migrate it with ` +
          `\`DB_NAME=${database} node tests/e2e/database.ts\` from this checkout, then start its runserver and retry.`,
      );
    }
    const exit = check.status === null ? 'no status' : String(check.status);
    throw new Error(`Could not check the migrations of the ${where}: \`${command}\` exited with ${exit}:\n${output}`);
  }
}

/** Throws, writing nothing, unless the local hubs `a` and `b` are ready in the registry: the host gate answers 404 to
 * a slug without a row (`base.middleware`), so every spec would fail on a 404 that never says why. */
export function assertLocalHubsRegistered(manage: ManagePy, database: string): void {
  const check = manage(['seed_local_hubs', '--check', '--no-color']);
  if (check.status === 0) return;
  const output = [check.stdout.trim(), check.stderr.trim()].filter(Boolean).join('\n');
  throw new Error(
    `The local hubs a and b are not ready in the registry of the e2e (DB_NAME=${database}). Run ` +
      `\`DB_NAME=${database} uv run python manage.py seed_local_hubs\` from this checkout and retry.\n\n${output}`,
  );
}

/** The SaaS's `demo_seed` accounts the specs sign in with (`OWNER` and `EMPLOYEE` of helpers.ts), each with access to
 * the local hubs `a` and `b`. */
export const DEMO_ACCOUNTS = ['owner@example.com', 'employee@example.com'] as const;
const DEMO_HUBS = ['a', 'b'] as const;

/** Runs one SQL statement on the stack's SaaS database. */
export type SaasSql = (statement: string) => CommandResult;

/** `psql` in compose's Postgres, as its superuser `hub`, on `database`, stopping at the first error (`COMPOSE_FILE`
 * points at compose.yaml from a checkout elsewhere). */
export function psqlOn(
  database: string,
  spawn: Spawn = spawnSync,
  env: NodeJS.ProcessEnv = process.env,
): (statement: string) => CommandResult {
  return (statement) => {
    const args = ['compose', 'exec', '-T', 'postgres', 'psql', '-U', 'hub', '-d', database, '-v', 'ON_ERROR_STOP=1', '-At', '-c', statement];
    const result = spawn('docker', args, { cwd: REPO_DIR, encoding: 'utf8', env });
    return {
      status: result.status,
      stdout: result.stdout ?? '',
      stderr: [result.stderr, result.error?.message].filter(Boolean).join('\n'),
    };
  };
}

const quoted = (values: readonly string[]): string => values.map((value) => `'${value}'`).join(', ');

/** The demo accounts with access to every demo hub, one per line (`accounts.HubMembership` is what the jump checks). */
const SEEDED_ACCOUNTS =
  'select u.email from accounts_user u join accounts_hubmembership m on m.user_id = u.id ' +
  `where u.email in (${quoted(DEMO_ACCOUNTS)}) and m.hub_slug in (${quoted(DEMO_HUBS)}) ` +
  `group by u.email having count(distinct m.hub_slug) = ${DEMO_HUBS.length}`;

const RECIPE = 'tests/e2e/README.md, «Varias ejecuciones a la vez»';
const ELSEWHERE = 'export E2E_SAAS_DB=<its database>.';
const HUB_IDS = "this Hub's ids, which WhatsApp's specs need";

/** The command, from the SaaS's checkout, that seeds its `database` with the demo accounts and gives `a` and `b` the ids
 * they have in `hub`: erplora.com's WhatsApp seed (`tests/e2e/panel/whatsapp_hub_seed.py`), which runs `demo_seed` with
 * them. `demo_seed` alone gives them ids of its own, and that seed then refuses the database («drop this database»).
 * Its photo goes to `hub`'s port, which must not be listening yet: delivered, it puts `a` on erplora.com's Free plan
 * (one device) for every spec after it. */
function seedCommand(database: string, hub: Pick<Stack, 'database' | 'hubPort'>): string {
  const ids = `docker compose exec -T postgres psql -U hub -d ${hub.database} -At -c "select id from base_hub where slug in (${quoted(DEMO_HUBS)}) order by slug"`;
  return (
    `\`env DB_NAME=${database} HUB_INTERNAL_URL=http://127.0.0.1:${hub.hubPort} ` +
    `uv run python tests/e2e/panel/whatsapp_hub_seed.py $(${ids})\``
  );
}

/** Throws, writing nothing, unless the SaaS's `database` has every demo account with access to `a` and `b`; the command
 * it offers seeds them with the ids `a` and `b` have in `hub`, the Hub the SaaS runs beside. */
export function assertDemoAccountsSeeded(sql: SaasSql, database: string, hub: Pick<Stack, 'database' | 'hubPort'>): void {
  const seed = seedCommand(database, hub);
  const read = sql(SEEDED_ACCOUNTS);
  if (read.status === 0) {
    const seeded = new Set(read.stdout.split(/\r?\n/).map((line) => line.trim()));
    const missing = DEMO_ACCOUNTS.filter((email) => !seeded.has(email));
    if (missing.length === 0) return;
    throw new Error(
      `The SaaS of this stack (database ${database}) lacks the demo accounts the specs sign in with: ` +
        `${missing.join(', ')}, with access to the hubs ${DEMO_HUBS.join(' and ')}. Every login would fail with ` +
        "«The email address and/or password you specified are not correct.». Stop this Hub's runserver, seed them " +
        `from the SaaS's checkout with ${seed} (a and b take ${HUB_IDS}), start the runserver again and retry ` +
        `(${RECIPE}). If that SaaS runs on another database, ${ELSEWHERE}`,
    );
  }
  const output = [read.stdout.trim(), read.stderr.trim()].filter(Boolean).join('\n');
  // Only the SaaS's own e2e database comes from its database.ts, which names it after E2E_SAAS_PORT.
  const own = /^saas_e2e_(\d+)$/.exec(database);
  if (own && output.includes(`database "${database}" does not exist`)) {
    throw new Error(
      `The database of this stack's SaaS (${database}) does not exist. Stop this Hub's runserver and, from the SaaS's ` +
        `checkout, create and migrate it with \`env -u DB_NAME E2E_SAAS_PORT=${own[1]} node tests/e2e/database.ts\`, ` +
        `seed its demo accounts with ${seed} (a and b take ${HUB_IDS}), start that SaaS with DB_NAME=${database} and ` +
        `this runserver again, and retry (${RECIPE}). If it runs on another database, ${ELSEWHERE}`,
    );
  }
  const exit = read.status === null ? 'no status' : String(read.status);
  throw new Error(`Could not read the demo accounts of the SaaS of this stack (database ${database}): psql exited with ${exit}:\n${output}`);
}

/** `manage.py` from the Hub's checkout, with the environment the e2e's servers inherit and `DB_NAME` = `database`. */
export function managePy(database: string, spawn: Spawn = spawnSync, env: NodeJS.ProcessEnv = process.env): ManagePy {
  return (args) => {
    const result = spawn('uv', ['run', 'python', 'manage.py', ...args], {
      cwd: HUB_DIR,
      encoding: 'utf8',
      env: { ...env, DB_NAME: database },
    });
    return {
      status: result.status,
      stdout: result.stdout ?? '',
      stderr: [result.stderr, result.error?.message].filter(Boolean).join('\n'),
    };
  };
}

/** Throws unless the run has one worker: the specs share one server and one database, and one spec's cleanup deletes
 * the rows another is using (`appointment-employee.spec.ts` deletes `E2E Apt%`, `appointment-agenda.spec.ts`'s too). */
function assertSingleWorker(workers: number): void {
  if (workers <= 1) return;
  throw new Error(
    `This e2e runs ${workers} workers on one shared stack (one Hub server, one SaaS and one database): specs running ` +
      "at once delete each other's data. Run it with `--workers=1` or without `--workers` (playwright.config.ts sets " +
      'workers: 1). To run specs in parallel, start another stack with its own ports and database ' +
      '(tests/e2e/README.md, «Varias ejecuciones a la vez»).',
  );
}

/** What `run_worker` logs once it registered the apps and scheduled their tasks (`base/worker.py`). */
export const WORKER_READY = 'worker: waiting for work';
/** How long the worker gets to register the apps in the SaaS and schedule their tasks. */
export const WORKER_START_TIMEOUT_MS = 60_000;
/** How much of the worker's output a failure quotes. */
const WORKER_OUTPUT_TAIL = 4_000;

/** The run's worker, running: its stop, which sends it SIGTERM (as ECS does) and resolves once it exited. */
export type StopWorker = () => Promise<void>;
/** Starts the run's worker on `database` (the Hub's) and `saasDatabase` (where it registers the apps). */
export type StartWorker = (database: string, saasDatabase: string) => Promise<StopWorker>;
/** `spawn` as `startWorker` calls it. */
export type SpawnWorker = (
  command: string,
  args: string[],
  options: { cwd: string; env: NodeJS.ProcessEnv; stdio: ['ignore', 'pipe', 'pipe'] },
) => Pick<ChildProcess, 'kill' | 'exitCode' | 'once' | 'on'> & {
  stdout: Pick<NonNullable<ChildProcess['stdout']>, 'on'>;
  stderr: Pick<NonNullable<ChildProcess['stderr']>, 'on'>;
};

/** `manage.py run_worker --databases-only` of this checkout on the stack's databases, up once it says it waits for
 *  work: it makes the databases of the hubs and demos signed up during the run and drops the demos that ended; the
 *  specs play the relay and the tasks themselves (a worker relaying too would race them). */
export function startWorker(
  database: string,
  saasDatabase: string,
  spawn: SpawnWorker = spawnProcess as unknown as SpawnWorker,
  env: NodeJS.ProcessEnv = process.env,
): Promise<StopWorker> {
  const worker = spawn('uv', ['run', 'python', 'manage.py', 'run_worker', '--databases-only'], {
    cwd: HUB_DIR,
    env: { ...env, DB_NAME: database, SHARED_DB_NAME: saasDatabase },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  let output = '';
  let exited = worker.exitCode !== null;
  const done = new Promise<void>((resolve) => {
    worker.once('exit', () => {
      exited = true;
      resolve();
    });
  });
  const stop: StopWorker = async () => {
    if (!exited) worker.kill('SIGTERM');
    await done;
  };
  const said = (): string => output.slice(-WORKER_OUTPUT_TAIL).trim();
  const where = `run_worker of the e2e (DB_NAME=${database})`;
  return new Promise<StopWorker>((resolve, reject) => {
    const timer = setTimeout(() => {
      void stop();
      reject(new Error(`The ${where} did not wait for work within ${WORKER_START_TIMEOUT_MS / 1000} s:\n${said()}`));
    }, WORKER_START_TIMEOUT_MS);
    const heard = (chunk: Buffer | string): void => {
      output += chunk.toString();
      if (output.includes(WORKER_READY)) {
        clearTimeout(timer);
        resolve(stop);
      }
    };
    worker.stdout.on('data', heard);
    worker.stderr.on('data', heard);
    worker.once('exit', (code) => {
      clearTimeout(timer);
      reject(new Error(`The ${where} exited with ${code ?? 'a signal'} before it waited for work:\n${said()}`));
    });
  });
}

/** Playwright calls it with the resolved config (`--workers=N` already applied); `manage`, `saas` and `start` are for
 * the tests. Every check runs before the worker starts: a check that stops the run leaves no worker behind. */
export default function globalSetup(
  config: Pick<FullConfig, 'workers'>,
  manage: ManagePy = managePy(STACK.database),
  saas: SaasSql = psqlOn(STACK.saasDatabase),
  start: StartWorker = startWorker,
): Promise<StopWorker> {
  assertSingleWorker(config.workers);
  assertMigrationsApplied(manage, STACK.database);
  assertLocalHubsRegistered(manage, STACK.database);
  assertDemoAccountsSeeded(saas, STACK.saasDatabase, STACK);
  return start(STACK.database, STACK.saasDatabase);
}
