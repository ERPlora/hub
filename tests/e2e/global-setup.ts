// The e2e's start: it refuses local databases with unapplied migrations before the first spec. On
// 2026-10-16 the local `hub` lacked verifactu.0003–0005 and the specs failed with «not valid JSON» (the
// `post` helper got Django's HTML error page), a red that never said its cause. It checks the control
// database (`migrate --check`) and the hub databases (`migrate_hubs --check`; phase 1: the control
// database again) of the run's `DB_NAME` (`stack.ts`), and never migrates: other sessions share them.
import { spawnSync } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { STACK } from './stack';

const HERE = dirname(fileURLToPath(import.meta.url));
const HUB_DIR = resolve(HERE, '..', '..');

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
    const exit = check.status === null ? 'no status' : String(check.status);
    throw new Error(`Could not check the migrations of the ${where}: \`${command}\` exited with ${exit}:\n${output}`);
  }
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

export default function globalSetup(): void {
  assertMigrationsApplied(managePy(STACK.database), STACK.database);
}
