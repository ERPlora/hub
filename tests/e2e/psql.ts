// SQL on the stack's databases, each statement where its tables live, and the people of a hub read with it.
import { execSync } from 'node:child_process';

import { type BrowserContext, expect } from '@playwright/test';

import { api } from './hub-api';
import { hubDatabases, plan } from './hub-databases';
import { A, REPO_DIR, STACK } from './stack';

/** `sql` on the database `database` of compose's Postgres, as its superuser `hub`. */
function psqlOn(database: string, sql: string): string {
  return execSync(`docker compose exec -T postgres psql -U hub -d ${database} -At -c "${sql}"`, {
    cwd: REPO_DIR,
    encoding: 'utf8',
  }).trim();
}

/** Each hub's own database, from the stack's registry (read once per hub; one that shares control's is control's). */
const hubDatabase = hubDatabases(STACK.database, (sql) => psqlOn(STACK.database, sql));

/** Where each scratch table of this run's specs was made (`hub-databases.ts`), kept between calls. */
const scratchTables = new Map<string, string>();

/** The database the scratch table `table` is in, control's or `hub`'s, when this process never noted it: Playwright
 * starts a new worker process after a failed test, and a spec's `afterAll` there must still find its copy. */
function scratchTableOf(table: string, hub: string): string | undefined {
  return [STACK.database, hubDatabase(hub)].find(
    (database) => psqlOn(database, `select to_regclass('\\"${table}\\"') is not null`) === 't',
  );
}

/** `sql` where its tables live (`hub-databases.ts`): each statement on control's tables in the stack's control
 * database, on any other in `hub`'s own (`a` unless the spec names another), the
 * ones in a row on one database in one call; what they print, in order. A statement that names both is refused. */
export function psql(sql: string, hub = 'a'): string {
  return plan(sql, hub, STACK.database, hubDatabase, scratchTables, (table) => scratchTableOf(table, hub))
    .map((run) => psqlOn(run.database, run.sql))
    .filter(Boolean)
    .join('\n');
}

/**
 * The username of whoever is signed in on `context`. Not by email: a hub database kept from a stack whose SaaS was
 * created again holds an older account with the same email (a new SaaS, new users), and the email names both.
 */
export async function usernameOf(context: BrowserContext): Promise<string> {
  const me = await api<{ user: { id: string } | null }>(context, A, 'GET', '/me');
  expect(me.status, 'GET /api/me').toBe(200);
  const id = me.data.user?.id ?? '';
  expect(id, 'the person signed in').not.toBe('');
  // `/api/me` names the person of the business's database (base.HubUser), whose username is the session's.
  return psql(`SELECT username FROM base_hubuser WHERE id = '${id}'`);
}

/** The usernames of every account of `email` (control's ``auth_user``), quoted for the `in (…)` of a statement on a
 * hub's tables, which cannot read control's; `null` when it has none, which matches nothing. */
export function usernamesOf(email: string): string {
  return psql(`select string_agg(quote_literal(username), ',') from auth_user where email = '${email}'`) || 'null';
}

/** The person (``base.HubUser``) of the account `email` in `hub`'s database: its username is control's (``auth_user``),
 * the person the hub's; '' when it has none yet. */
export function hubUserIdOf(email: string, hub = 'a'): string {
  return psql(`select id from base_hubuser where username in (${usernamesOf(email)})`, hub);
}
