// How a demo of the stack was born, as demo.spec.ts checks it (hub#1061): a fact in its databases instead of a clock.
// The spec waited 15 s for a demo («the worker's 5 s tick and PLAN-DB §6's 5 s aim with room for a loaded machine»),
// and a sign-up that made its tables again was to fail there; on a machine loaded far beyond its cores a demo took
// 15.3 s with nothing broken and failed it. What those 15 s stood for is a fact the sign-up leaves behind: a demo's
// database is the clone of its template (base/tenancy/provision.py, PLAN-DB §6), kept current by `migrate_hubs` (which
// global-setup.ts checks), so its sign-up applies no migration, and every row of its `django_migrations` is its
// template's, applied at the same instant. A sign-up that makes its tables again (an empty database migrated, the
// template skipped) leaves rows of its own, however fast or slow the machine is.
//
// It reads compose's Postgres as its superuser (`psqlOn` of global-setup.ts): the registry in the stack's control
// database (`base_hub`), then the demo's own database and its template's, which `psql()` of helpers.ts never reaches
// (`django_migrations` is control's table for it).
import { type CommandResult, psqlOn } from './global-setup';

/** Runs one statement on `database` (`psqlOn` of global-setup.ts, which `sql` replaces in the tests). */
export type SqlOn = (database: string) => (statement: string) => CommandResult;

/** The template a hub is cloned from: `<control>_template[_<vertical>]`, as base/tenancy/names.py `template_db_name`. */
export function templateOf(control: string, vertical: string): string {
  return `${control}_template${vertical ? `_${vertical}` : ''}`;
}

/** The rows of `hub` (`<app>.<migration> <applied>`) its template does not have: what was applied to it after its
 *  clone. A migration its template got after the clone is no row of the hub's, and so never listed. */
export function notFromItsTemplate(hub: readonly string[], template: readonly string[]): string[] {
  const cloned = new Set(template);
  return hub.filter((row) => !cloned.has(row));
}

/** The lines `statement` printed on `database`; a read that failed throws, saying where and why. */
function rows(sql: SqlOn, database: string, statement: string): string[] {
  const result = sql(database)(statement);
  if (result.status !== 0) throw new Error(`Could not read ${database}: ${result.stderr.trim() || `psql exited with ${result.status}`}`);
  return result.stdout.split('\n').filter(Boolean);
}

/** `<app>.<migration> <applied, in UTC>` of every migration of `database`, in the order they were applied. */
function migrationsOf(sql: SqlOn, database: string): string[] {
  const found = rows(
    sql,
    database,
    "select app || '.' || name || ' ' || (applied at time zone 'UTC')::text from django_migrations order by id",
  );
  if (found.length === 0) throw new Error(`There are no migrations in ${database}: it is no hub's database.`);
  return found;
}

/** The migrations the sign-up of the demo `slug` applied to its database (registry of `control`): `[]` when it was born
 *  as the clone of its template, as every sign-up is (PLAN-DB §6). */
export function migrationsAppliedAtSignUp(slug: string, control: string, sql: SqlOn = psqlOn): string[] {
  const [row = ''] = rows(
    sql,
    control,
    `select coalesce(db_name, '') || '|' || coalesce(vertical, '') from base_hub where slug = '${slug}'`,
  );
  const [database = '', vertical = ''] = row.split('|');
  if (!database) throw new Error(`There is no demo '${slug}' with a database of its own in the registry of ${control}.`);
  return notFromItsTemplate(migrationsOf(sql, database), migrationsOf(sql, templateOf(control, vertical)));
}

/** A demo of the registry, as its preparation left it. */
export interface DemoRow {
  slug: string;
  status: string;
  lastError: string;
}

/** The newest demo of the registry of `control` (a run has one stack and one worker of Playwright: it is the one the
 *  door is waiting for), or `null` when there is none. */
export function demoBeingPrepared(control: string, sql: SqlOn = psqlOn): DemoRow | null {
  const [row] = rows(
    sql,
    control,
    "select slug || '|' || status || '|' || coalesce(last_error, '') from base_hub where slug like 'demo-%' order by created_at desc limit 1",
  );
  if (!row) return null;
  const [slug = '', status = '', ...error] = row.split('|');
  return { slug, status, lastError: error.join('|') };
}
