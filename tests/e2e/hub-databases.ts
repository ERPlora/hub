// Where a spec's SQL goes (helpers.ts `psql`) since every hub has its own database (round 2026-10-30 of PLAN-DB, S2a;
// `seed_local_hubs` gives `a` and `b` theirs once every app can live in one). Control's tables — the registry
// (`base_hub`, `base_democode`, `control_*`), Django's users and sessions (`auth_*`, `django_*`) and the memberships
// and session owners of phase 1 (`base_membership`, `base_sessionowner`) — live in the stack's control database
// (`DB_NAME`); every other table in the hub's own, read from the registry once per hub (`db_name`; empty: it still
// shares control's). Each statement of a spec's SQL runs where its tables live, the ones in a row on one database
// together; a spec's own scratch tables (`e2e…`) go where they were made. No statement crosses two databases, so one
// that names tables of both is refused, saying how to split it.

/** Control's tables: the registry, Django's own and phase 1's memberships and session owners (base/tenancy/inventory.py). */
const CONTROL_TABLE = /^(?:auth_\w+|django_\w+|control_\w+|base_hub|base_democode|base_membership|base_sessionowner)$/;
/** A spec's own scratch table (`e2e_…`, `"e2e-…"`): a copy kept while it runs, next to what it copies. */
const SCRATCH_TABLE = /^e2e/;
/** A table's name: quoted (`"e2e-x"`, `\"e2e-x\"` inside the shell's quotes) or bare. */
const NAME = String.raw`(?:\\?"([^"\\]+)\\?"|([a-z_][a-z0-9_]*))`;
/** A table a statement names: after `from`, `join`, `into`, `update` or `table` (`if [not] exists` aside); after `from`
 * or `join`, a name followed by `(` is a function's (`jsonb_array_elements(…)`), not a table. */
const TABLE = new RegExp(
  String.raw`\b(from|join|into|update|table)\s+(?:if\s+(?:not\s+)?exists\s+)?${NAME}(\s*\()?`,
  'gi',
);
/** A table a statement asks about by name: `to_regclass('e2e_x')`, whether a scratch table is still there. */
const ASKED = /\bto_regclass\(\s*'([a-z_][a-z0-9_-]*)'/gi;
/** Words that follow `update` or `from` without being a table (`… do update set`). */
const KEYWORD = new Set(['set', 'only', 'lateral']);
/** The scratch table a statement makes or drops. */
const MADE = new RegExp(String.raw`^\s*create\s+(?:unlogged\s+)?table\s+(?:if\s+not\s+exists\s+)?${NAME}`, 'i');
const DROPPED = new RegExp(String.raw`^\s*drop\s+table\s+(?:if\s+exists\s+)?${NAME}`, 'i');

/** One run of `psql`: statements in a row that live on one database. */
export interface Run {
  database: string;
  sql: string;
}

/** The tables `sql` names, in order (a subquery's too), then those it asks about by name (`to_regclass`). */
export function tablesOf(sql: string): string[] {
  return [
    ...[...sql.matchAll(TABLE)]
      .filter(([, word, , , call]) => !(call && /^(?:from|join)$/i.test(word)))
      .map(([, , quoted, bare]) => (quoted ?? bare).toLowerCase())
      .filter((table) => !KEYWORD.has(table)),
    ...[...sql.matchAll(ASKED)].map(([, name]) => name.toLowerCase()),
  ];
}

/** `sql`'s statements: split at each `;` outside a quoted string (`'…'`) or name (`"…"`), the empty ones dropped. */
export function statementsOf(sql: string): string[] {
  const statements: string[] = [];
  let quote: string | null = null;
  let start = 0;
  for (let at = 0; at < sql.length; at++) {
    const char = sql[at];
    if (quote) {
      if (char === quote) quote = null;
    } else if (char === "'" || char === '"') {
      quote = char;
    } else if (char === ';') {
      statements.push(sql.slice(start, at));
      start = at + 1;
    }
  }
  statements.push(sql.slice(start));
  return statements.map((statement) => statement.trim()).filter(Boolean);
}

/** The database `statement` runs on from what it names: control's tables, the hub's or the scratch tables it knows
 * were made (`made`); `undefined` when it names only scratch tables nobody made yet (it goes with its neighbours). */
function databaseOf(
  statement: string,
  hub: string,
  control: string,
  hubDatabase: (slug: string) => string,
  made: Map<string, string>,
): string | undefined {
  const tables = tablesOf(statement);
  const scratch = tables.filter((table) => SCRATCH_TABLE.test(table));
  const ofControl = tables.filter((table) => !SCRATCH_TABLE.test(table) && CONTROL_TABLE.test(table));
  const ofHub = tables.filter((table) => !SCRATCH_TABLE.test(table) && !CONTROL_TABLE.test(table));
  if (ofControl.length && ofHub.length) {
    throw new Error(
      `This statement names control's tables (${[...new Set(ofControl)].join(', ')}) and the hub's ` +
        `(${[...new Set(ofHub)].join(', ')}): they live in two databases now. Read control's first and pass the ` +
        `values to the hub's statement.\n${statement}`,
    );
  }
  const named = ofControl.length ? control : ofHub.length ? hubDatabase(hub) : undefined;
  const known = [...new Set(scratch.filter((table) => made.has(table)))];
  const places = new Set([...(named ? [named] : []), ...known.map((table) => made.get(table) as string)]);
  if (places.size > 1) {
    const where = known.map((table) => `${table} in ${made.get(table)}`).join(', ');
    throw new Error(`This statement names tables of two databases (${where}; the rest in ${named}).\n${statement}`);
  }
  return [...places][0] ?? (scratch.length ? undefined : hubDatabase(hub));
}

/** Note in `made` the scratch table `statement` makes (where it runs) or, unless `madeOnly`, forget the one it drops. */
function remember(statement: string, database: string, made: Map<string, string>, madeOnly = false): void {
  const created = statement.match(MADE);
  const dropped = statement.match(DROPPED);
  const name = (match: RegExpMatchArray) => (match[1] ?? match[2]).toLowerCase();
  if (created && SCRATCH_TABLE.test(name(created))) made.set(name(created), database);
  if (dropped && !madeOnly && SCRATCH_TABLE.test(name(dropped))) made.delete(name(dropped));
}

/** Where each statement of `sql` runs (`hub`'s tables in its database, control's in `control`), the ones in a row on
 * one database in one run, in order. `made` remembers, across calls, the database each scratch table was made in: a
 * statement that names only scratch tables nobody made yet goes with the next statement that says where (else the
 * last one, else the hub's). A statement whose tables live in two databases is refused. */
export function plan(
  sql: string,
  hub: string,
  control: string,
  hubDatabase: (slug: string) => string,
  made: Map<string, string>,
): Run[] {
  const statements = statementsOf(sql);
  const places = statements.map((statement) => {
    const database = databaseOf(statement, hub, control, hubDatabase, made);
    if (database) remember(statement, database, made);
    return database;
  });
  places.forEach((database, at) => {
    if (database) return;
    const next = places.slice(at + 1).find(Boolean);
    const last = places.slice(0, at).reverse().find(Boolean);
    places[at] = next ?? last ?? hubDatabase(hub);
    // It named no table anybody had made when it came: what it drops was not noted, what came after it may have been.
    remember(statements[at], places[at] as string, made, true);
  });
  const runs: Run[] = [];
  statements.forEach((statement, at) => {
    const database = places[at] as string;
    const previous = runs[runs.length - 1];
    if (previous?.database === database) previous.sql += `; ${statement}`;
    else runs.push({ database, sql: statement });
  });
  return runs;
}

/** `hub` → its database, from the registry of `control` (`read` runs a statement there), each read once. */
export function hubDatabases(control: string, read: (sql: string) => string): (hub: string) => string {
  const known = new Map<string, string>();
  return (hub) => {
    const kept = known.get(hub);
    if (kept !== undefined) return kept;
    const row = read(`select 'db:' || db_name from base_hub where slug = '${hub}'`).trim();
    if (!row.startsWith('db:')) throw new Error(`There is no hub '${hub}' in the registry of ${control}.`);
    const database = row.slice('db:'.length) || control;
    known.set(hub, database);
    return database;
  };
}
