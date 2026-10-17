// The e2e's start (global-setup.ts) refuses local databases with unapplied migrations: on 2026-10-16 the
// local `hub` lacked verifactu.0003–0005 and the specs failed with «not valid JSON» (the `post` helper got
// Django's HTML error page), a red that never said its cause. The check never applies anything: the
// database is shared with other sessions.
// flow: ninguno — FIX de proceso (guardarraíl del e2e)
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import { assertLocalHubsRegistered, assertMigrationsApplied, managePy, type CommandResult, type Spawn } from './global-setup';

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
