// The e2e's start (global-setup.ts) refuses local databases with unapplied migrations: on 2026-10-16 the
// local `hub` lacked verifactu.0003–0005 and the specs failed with «not valid JSON» (the `post` helper got
// Django's HTML error page), a red that never said its cause. The check never applies anything: the
// database is shared with other sessions.
// flow: ninguno — FIX de proceso (guardarraíl del e2e)
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import globalSetup, {
  assertDemoAccountsSeeded,
  assertLocalHubsRegistered,
  assertMigrationsApplied,
  DEMO_ACCOUNTS,
  managePy,
  psqlOn,
  type CommandResult,
  type Spawn,
} from './global-setup';

const HUB_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');

const UP_TO_DATE: CommandResult = { status: 0, stdout: 'Planned operations:\n  No planned migration operations.\n', stderr: '' };

const CONTROL_PENDING: CommandResult = {
  status: 1,
  stdout:
    'Planned operations:\nverifactu.0003_live_paid\n    Add field hub_status to config\n    Add field live_paid to config\n' +
    'verifactu.0004_multiple_taxpayers_always\n    Remove field multiple_taxpayers from config\n',
  stderr: '',
};

const HUBS_UP_TO_DATE: CommandResult = {
  status: 0,
  stdout: 'migrate_hubs: the control database is up to date (phase 1: no hub databases yet).\n',
  stderr: '',
};

const HUBS_PENDING: CommandResult = {
  status: 1,
  stdout: 'migrate_hubs: unapplied migrations in the control database:\ninvoice.0004_platform_ref\n',
  stderr: '',
};

const UNREACHABLE: CommandResult = {
  status: 1,
  stdout: '',
  stderr: 'django.db.utils.OperationalError: connection to server at "127.0.0.1", port 5432 failed: Connection refused\n',
};

const FIX = 'DB_NAME=hub uv run python manage.py migrate && DB_NAME=hub uv run python manage.py migrate_hubs';

/** A `manage.py` double that answers by command (`migrate` or `migrate_hubs`) and records every call. */
function fakeManagePy(answers: { migrate: CommandResult; migrate_hubs?: CommandResult }): {
  calls: string[][];
  run: (args: string[]) => CommandResult;
} {
  const calls: string[][] = [];
  return {
    calls,
    run: (args) => {
      calls.push(args);
      const answer = args[0] === 'migrate_hubs' ? answers.migrate_hubs : answers.migrate;
      if (!answer) throw new Error(`unexpected manage.py ${args.join(' ')}`);
      return answer;
    },
  };
}

describe('assertMigrationsApplied', () => {
  it('passes when the control database and the hub databases are up to date, checking both', () => {
    const manage = fakeManagePy({ migrate: UP_TO_DATE, migrate_hubs: HUBS_UP_TO_DATE });

    expect(() => assertMigrationsApplied(manage.run, 'hub')).not.toThrow();
    expect(manage.calls.map((args) => args[0])).toEqual(['migrate', 'migrate_hubs']);
  });

  it('stops the run naming the pending migrations of the control database and the command that applies them', () => {
    const manage = fakeManagePy({ migrate: CONTROL_PENDING, migrate_hubs: HUBS_UP_TO_DATE });

    expect(() => assertMigrationsApplied(manage.run, 'hub')).toThrow(
      'The local databases of the e2e (DB_NAME=hub) have unapplied migrations ' +
        '(verifactu.0003_live_paid, verifactu.0004_multiple_taxpayers_always). ' +
        `Run \`${FIX}\` from this checkout and retry.`,
    );
    expect(() => assertMigrationsApplied(manage.run, 'hub')).toThrow(CONTROL_PENDING.stdout.trim());
  });

  it('stops the run when only the hub databases are behind (migrate_hubs --check)', () => {
    const manage = fakeManagePy({ migrate: UP_TO_DATE, migrate_hubs: HUBS_PENDING });

    expect(() => assertMigrationsApplied(manage.run, 'hub')).toThrow(
      `have unapplied migrations (invoice.0004_platform_ref). Run \`${FIX}\` from this checkout and retry.`,
    );
    expect(() => assertMigrationsApplied(manage.run, 'hub')).toThrow(HUBS_PENDING.stdout.trim());
  });

  it("names the run's own database in the message and in the command", () => {
    const manage = fakeManagePy({ migrate: CONTROL_PENDING });

    expect(() => assertMigrationsApplied(manage.run, 'hub_e2e')).toThrow(
      '(DB_NAME=hub_e2e) have unapplied migrations',
    );
    expect(() => assertMigrationsApplied(manage.run, 'hub_e2e')).toThrow(
      'Run `DB_NAME=hub_e2e uv run python manage.py migrate && DB_NAME=hub_e2e uv run python manage.py migrate_hubs`',
    );
  });

  it('only ever runs migrate and migrate_hubs with --check, so nothing is applied', () => {
    const answers = [
      { migrate: UP_TO_DATE, migrate_hubs: HUBS_UP_TO_DATE },
      { migrate: UP_TO_DATE, migrate_hubs: HUBS_PENDING },
      { migrate: CONTROL_PENDING },
      { migrate: UNREACHABLE },
    ];
    for (const answer of answers) {
      const manage = fakeManagePy(answer);

      try {
        assertMigrationsApplied(manage.run, 'hub');
      } catch {
        // The failures are covered above; here only the commands matter.
      }

      expect(manage.calls.length).toBeGreaterThan(0);
      for (const args of manage.calls) {
        expect(['migrate', 'migrate_hubs']).toContain(args[0]);
        expect(args).toContain('--check');
      }
    }
  });

  it('does not blame migrations when the check itself cannot run', () => {
    const manage = fakeManagePy({ migrate: UNREACHABLE });

    expect(() => assertMigrationsApplied(manage.run, 'hub')).toThrow(
      /^Could not check the migrations of the local databases of the e2e \(DB_NAME=hub\): `manage\.py migrate --check --plan --no-color` exited with 1/,
    );
    expect(() => assertMigrationsApplied(manage.run, 'hub')).toThrow('Connection refused');
    expect(() => assertMigrationsApplied(manage.run, 'hub')).not.toThrow('unapplied migrations');
  });

  // flow: ninguno — FIX de la infraestructura e2e del Hub (aislar los datos de cada ejecución)
  it('says how to create the e2e database of a stack beside the shared one when it does not exist yet', () => {
    const missing: CommandResult = {
      status: 1,
      stdout: '',
      stderr:
        "WARNING psycopg.pool error connecting in 'pool-1': connection failed: connection to server at \"127.0.0.1\", " +
        'port 5432 failed: FATAL:  database "hub_e2e_8030" does not exist\n' +
        "django.db.utils.OperationalError: couldn't get a connection after 5.00 sec\n",
    };
    const manage = fakeManagePy({ migrate: missing });

    expect(() => assertMigrationsApplied(manage.run, 'hub_e2e_8030')).toThrow(
      'The database of the e2e (DB_NAME=hub_e2e_8030) does not exist. Create and migrate it with ' +
        '`DB_NAME=hub_e2e_8030 node tests/e2e/database.ts` from this checkout, then start its runserver and retry.',
    );
    expect(() => assertMigrationsApplied(manage.run, 'hub_e2e_8030')).not.toThrow('unapplied migrations');
    expect(manage.calls.every((args) => args.includes('--check'))).toBe(true);

    // An e2e database that exists but cannot be checked (Postgres down) is the generic failure too.
    const down = fakeManagePy({ migrate: UNREACHABLE });
    expect(() => assertMigrationsApplied(down.run, 'hub_e2e_8030')).toThrow(/^Could not check the migrations[^\n]*\n[^\n]*Connection refused$/);

    // database.ts prepares only e2e databases: a missing `hub` is the generic failure, with what Postgres said.
    const shared = fakeManagePy({ migrate: { ...missing, stderr: 'FATAL:  database "hub" does not exist\n' } });
    expect(() => assertMigrationsApplied(shared.run, 'hub')).toThrow(/^Could not check the migrations[^\n]*\nFATAL: {2}database "hub" does not exist$/);
  });

  it('reports a migrate_hubs --check that fails without listing anything', () => {
    const manage = fakeManagePy({
      migrate: UP_TO_DATE,
      migrate_hubs: { status: 1, stdout: '', stderr: 'CommandError: migrate_hubs --check: the control database could not be read: timeout\n' },
    });

    expect(() => assertMigrationsApplied(manage.run, 'hub')).toThrow(
      /^Could not check the migrations[^\n]*`manage\.py migrate_hubs --check --no-color` exited with 1:\nCommandError: migrate_hubs --check: the control database could not be read: timeout$/,
    );
  });

  it('reports a check that never started (uv missing, killed)', () => {
    const manage = fakeManagePy({ migrate: { status: null, stdout: '', stderr: 'spawnSync uv ENOENT' } });

    expect(() => assertMigrationsApplied(manage.run, 'hub')).toThrow(
      /^Could not check the migrations[^\n]*exited with no status:\nspawnSync uv ENOENT$/,
    );
  });
});

describe('managePy', () => {
  it("runs manage.py with uv from the Hub's checkout, against the run's database and with the rest of the environment", () => {
    const seen: { command: string; args: string[]; cwd: string; env: NodeJS.ProcessEnv }[] = [];
    const spawn: Spawn = (command, args, options) => {
      seen.push({ command, args, cwd: options.cwd, env: options.env });
      return { status: 0, stdout: 'out', stderr: 'err' };
    };

    const result = managePy('hub_e2e', spawn, { PATH: '/usr/bin', DB_NAME: 'hub' })(['migrate', '--check']);

    expect(result).toEqual({ status: 0, stdout: 'out', stderr: 'err' });
    expect(seen).toEqual([
      {
        command: 'uv',
        args: ['run', 'python', 'manage.py', 'migrate', '--check'],
        cwd: HUB_DIR,
        env: { PATH: '/usr/bin', DB_NAME: 'hub_e2e' },
      },
    ]);
  });

  it('turns a process that never started into a result without status that says why', () => {
    const spawn: Spawn = () => ({ status: null, stdout: null, stderr: null, error: new Error('spawnSync uv ENOENT') });

    expect(managePy('hub', spawn, {})(['migrate', '--check'])).toEqual({
      status: null,
      stdout: '',
      stderr: 'spawnSync uv ENOENT',
    });
  });
});

// The host gate answers 404 to a slug the registry does not have (plan 2026-10-17, §1.3): without `a` and `b` every
// spec would fail on a 404 that never says why. `seed_local_hubs --check` writes nothing.
describe('assertLocalHubsRegistered', () => {
  it('passes when a and b are ready, asking only the check', () => {
    const calls: string[][] = [];
    assertLocalHubsRegistered((args) => (calls.push(args), { status: 0, stdout: 'a: ready\nb: ready\n', stderr: '' }), 'hub');
    expect(calls).toEqual([['seed_local_hubs', '--check', '--no-color']]);
  });

  it('stops the run naming what is missing and the command that seeds them', () => {
    const missing: CommandResult = {
      status: 1,
      stdout: '',
      stderr: 'CommandError: Not ready in the registry: a (missing), b (missing). Run `manage.py seed_local_hubs`.\n',
    };
    expect(() => assertLocalHubsRegistered(() => missing, 'hub_e2e_8030')).toThrow(
      'The local hubs a and b are not ready in the registry of the e2e (DB_NAME=hub_e2e_8030). Run ' +
        '`DB_NAME=hub_e2e_8030 uv run python manage.py seed_local_hubs` from this checkout and retry.\n\n' +
        'CommandError: Not ready in the registry: a (missing), b (missing). Run `manage.py seed_local_hubs`.',
    );
  });
});

// flow: ninguno — arnés e2e del Hub (FIX-HUB-E2E-README-PARALLEL-STACK-MISSES-DEMO-SEED)
// The specs sign in with the SaaS's demo accounts (`login` of helpers.ts), which only `manage.py demo_seed` of the SaaS
// creates. A stack's own SaaS on its fresh database (`saas_e2e_<port>`, the SaaS's tests/e2e/database.ts) has none: on
// 2026-10-28 the README's recipe never said it, and every login waited 30 s to fail with «The email address and/or
// password you specified are not correct.». The run stops before the first spec with the command that seeds them,
// reading the SaaS's database with one select (it writes nothing there).
describe('assertDemoAccountsSeeded', () => {
  const SEEDED: CommandResult = { status: 0, stdout: 'employee@example.com\nowner@example.com\n', stderr: '' };
  const NONE: CommandResult = { status: 0, stdout: '', stderr: '' };
  /** The local demo hubs `a` and `b` (`seed_local_hubs`), both of which every demo account must reach. */
  const DEMO_HUBS_COUNT = 2;

  /** A psql double on the SaaS's database: one answer, and every statement it got. */
  function fakeSaasSql(answer: CommandResult): { statements: string[]; run: (statement: string) => CommandResult } {
    const statements: string[] = [];
    return { statements, run: (statement) => (statements.push(statement), answer) };
  }

  it('are the accounts the specs sign in with: the owner and the employee of a and b', () => {
    expect(DEMO_ACCOUNTS).toEqual(['owner@example.com', 'employee@example.com']);
  });

  it('passes when both demo accounts have access to a and b, asking it with one select', () => {
    const saas = fakeSaasSql(SEEDED);

    expect(() => assertDemoAccountsSeeded(saas.run, 'saas_e2e_8031')).not.toThrow();
    expect(saas.statements).toHaveLength(1);
    expect(saas.statements[0]).toMatch(/^select /);
    for (const word of ["'owner@example.com'", "'employee@example.com'", "'a'", "'b'", 'accounts_user', 'accounts_hubmembership']) {
      expect(saas.statements[0]).toContain(word);
    }
  });

  // An account with access to one demo hub only is not seeded: the select keeps an email only with every demo hub
  // (`having count(distinct …) = 2`). A psql double cannot run SQL, so this pins the clause the mutant `>= 1` lost.
  it('counts an account as seeded only with access to every demo hub, a and b', () => {
    const saas = fakeSaasSql(SEEDED);

    assertDemoAccountsSeeded(saas.run, 'saas_e2e_8031');
    expect(saas.statements[0]).toContain(`having count(distinct m.hub_slug) = ${DEMO_HUBS_COUNT}`);
  });

  it('stops the run naming the missing accounts and the exact command that seeds them', () => {
    expect(() => assertDemoAccountsSeeded(fakeSaasSql(NONE).run, 'saas_e2e_8031')).toThrow(
      'The SaaS of this stack (database saas_e2e_8031) lacks the demo accounts the specs sign in with: ' +
        'owner@example.com, employee@example.com, with access to the hubs a and b. Every login would fail with ' +
        '«The email address and/or password you specified are not correct.». Seed them with ' +
        "`env DB_NAME=saas_e2e_8031 uv run python manage.py demo_seed` from the SaaS's checkout and retry " +
        '(tests/e2e/README.md, «Varias ejecuciones a la vez»). If that SaaS runs on another database, export ' +
        'E2E_SAAS_DB=<its database>.',
    );
  });

  it('names only the account that is missing, on the database it read', () => {
    const run = fakeSaasSql({ status: 0, stdout: 'owner@example.com\n', stderr: '' }).run;

    expect(() => assertDemoAccountsSeeded(run, 'saas')).toThrow(
      '(database saas) lacks the demo accounts the specs sign in with: employee@example.com, with access',
    );
    expect(() => assertDemoAccountsSeeded(run, 'saas')).toThrow('`env DB_NAME=saas uv run python manage.py demo_seed`');
  });

  it("says how to create the stack's SaaS database when it does not exist yet", () => {
    const missing: CommandResult = {
      status: 2,
      stdout: '',
      stderr:
        'psql: error: connection to server on socket "/var/run/postgresql/.s.PGSQL.5432" failed: FATAL:  database ' +
        '"saas_e2e_8031" does not exist\n',
    };

    expect(() => assertDemoAccountsSeeded(fakeSaasSql(missing).run, 'saas_e2e_8031')).toThrow(
      "The database of this stack's SaaS (saas_e2e_8031) does not exist. From the SaaS's checkout, create and migrate " +
        'it with `env -u DB_NAME E2E_SAAS_PORT=8031 node tests/e2e/database.ts`, seed its demo accounts with ' +
        '`env DB_NAME=saas_e2e_8031 uv run python manage.py demo_seed`, start that SaaS with DB_NAME=saas_e2e_8031 and ' +
        'retry (tests/e2e/README.md, «Varias ejecuciones a la vez»). If it runs on another database, export ' +
        'E2E_SAAS_DB=<its database>.',
    );
  });

  it('reports what psql said when it cannot read the accounts (not migrated, Postgres down, a database of its own)', () => {
    const unmigrated: CommandResult = {
      status: 1,
      stdout: '',
      stderr: 'ERROR:  relation "accounts_user" does not exist\nLINE 1: select u.email from accounts_user u\n',
    };
    expect(() => assertDemoAccountsSeeded(fakeSaasSql(unmigrated).run, 'saas_e2e_8031')).toThrow(
      /^Could not read the demo accounts of the SaaS of this stack \(database saas_e2e_8031\): psql exited with 1:\nERROR: {2}relation "accounts_user" does not exist\nLINE 1: select u\.email from accounts_user u$/,
    );

    expect(() => assertDemoAccountsSeeded(fakeSaasSql(UNREACHABLE).run, 'saas')).toThrow(/^Could not read[^\n]*\n[^\n]*Connection refused$/);

    // Only `saas_e2e_<port>` comes from the SaaS's database.ts with E2E_SAAS_PORT: any other missing one is what psql said.
    const own: CommandResult = { status: 2, stdout: '', stderr: 'FATAL:  database "saas_fix_e2e_a" does not exist\n' };
    expect(() => assertDemoAccountsSeeded(fakeSaasSql(own).run, 'saas_fix_e2e_a')).toThrow(
      /^Could not read[^\n]*\(database saas_fix_e2e_a\): psql exited with 2:\nFATAL: {2}database "saas_fix_e2e_a" does not exist$/,
    );

    const never: CommandResult = { status: null, stdout: '', stderr: 'spawnSync docker ENOENT' };
    expect(() => assertDemoAccountsSeeded(fakeSaasSql(never).run, 'saas')).toThrow(/psql exited with no status:\nspawnSync docker ENOENT$/);
  });
});

describe('psqlOn', () => {
  it("runs one statement with psql in compose's Postgres, on the database it names, from erplora-next's root", () => {
    const seen: { command: string; args: string[]; cwd: string; env: NodeJS.ProcessEnv }[] = [];
    const spawn: Spawn = (command, args, options) => {
      seen.push({ command, args, cwd: options.cwd, env: options.env });
      return { status: 0, stdout: 'owner@example.com\n', stderr: '' };
    };

    expect(psqlOn('saas_e2e_8031', spawn, { COMPOSE_FILE: '/x/compose.yaml' })('select 1')).toEqual({
      status: 0,
      stdout: 'owner@example.com\n',
      stderr: '',
    });
    expect(seen).toEqual([
      {
        command: 'docker',
        args: ['compose', 'exec', '-T', 'postgres', 'psql', '-U', 'hub', '-d', 'saas_e2e_8031', '-v', 'ON_ERROR_STOP=1', '-At', '-c', 'select 1'],
        cwd: resolve(HUB_DIR, '..'),
        env: { COMPOSE_FILE: '/x/compose.yaml' },
      },
    ]);
  });

  it('turns a docker that never started into a result without status that says why', () => {
    const spawn: Spawn = () => ({ status: null, stdout: null, stderr: null, error: new Error('spawnSync docker ENOENT') });

    expect(psqlOn('saas', spawn, {})('select 1')).toEqual({ status: null, stdout: '', stderr: 'spawnSync docker ENOENT' });
  });
});

// flow: ninguno — infraestructura del e2e del Hub (`tests/e2e/global-setup.ts`): una pila compartida no admite `--workers` > 1
// `--workers=N` on the command line overrides `workers: 1` of playwright.config.ts, and Playwright hands globalSetup the
// resolved count (`--workers=2` → 2, `50%` → half the cores). On 2026-10-23 `--workers=2` ran two specs at once on the one
// stack: appointment-employee.spec.ts deleted `E2E Apt%`, the rows appointment-agenda.spec.ts was using, and the agenda
// spent its 180 s waiting for them. The run stops before any check touches a database.
describe('globalSetup', () => {
  const READY: CommandResult = { status: 0, stdout: 'a: ready\nb: ready\n', stderr: '' };

  /** A `manage.py` double where every check passes, recording each call. */
  function readyManagePy(): { calls: string[][]; run: (args: string[]) => CommandResult } {
    const calls: string[][] = [];
    return {
      calls,
      run: (args) => {
        calls.push(args);
        if (args[0] === 'migrate') return UP_TO_DATE;
        if (args[0] === 'migrate_hubs') return HUBS_UP_TO_DATE;
        if (args[0] === 'seed_local_hubs') return READY;
        throw new Error(`unexpected manage.py ${args.join(' ')}`);
      },
    };
  }

  /** A psql double on the SaaS's database where both demo accounts are seeded, recording each statement. */
  function seededSaasSql(): { statements: string[]; run: (statement: string) => CommandResult } {
    const statements: string[] = [];
    return {
      statements,
      run: (statement) => (statements.push(statement), { status: 0, stdout: 'employee@example.com\nowner@example.com\n', stderr: '' }),
    };
  }

  it.each([2, 7])('stops a run of %i workers before checking anything, saying why and how to run it', (workers) => {
    const manage = readyManagePy();
    const saas = seededSaasSql();

    expect(() => globalSetup({ workers }, manage.run, saas.run)).toThrow(
      `This e2e runs ${workers} workers on one shared stack`,
    );
    expect(() => globalSetup({ workers }, manage.run, saas.run)).toThrow('Run it with `--workers=1` or without `--workers`');
    expect(manage.calls).toEqual([]);
    expect(saas.statements).toEqual([]);
  });

  it("runs the database checks with a single worker, the SaaS's demo accounts last", () => {
    const manage = readyManagePy();
    const saas = seededSaasSql();

    expect(() => globalSetup({ workers: 1 }, manage.run, saas.run)).not.toThrow();
    expect(manage.calls.map((args) => args[0])).toEqual(['migrate', 'migrate_hubs', 'seed_local_hubs']);
    expect(saas.statements).toHaveLength(1);
  });

  it("stops the run before the first spec when the stack's SaaS has no demo accounts", () => {
    const manage = readyManagePy();

    expect(() => globalSetup({ workers: 1 }, manage.run, () => ({ status: 0, stdout: '', stderr: '' }))).toThrow(
      'lacks the demo accounts the specs sign in with: owner@example.com, employee@example.com',
    );
  });
});
