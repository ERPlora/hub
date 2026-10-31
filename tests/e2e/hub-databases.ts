// Where a spec's SQL goes (helpers.ts `psql`) since every hub has its own database (round 2026-10-30 of PLAN-DB, S2a;
// `seed_local_hubs` gives `a` and `b` theirs once every app can live in one). Control's tables — the registry
// (`base_hub`, `base_democode`, `control_*`), Django's users and sessions (`auth_*`, `django_*`) and the memberships
// and session owners of phase 1 (`base_membership`, `base_sessionowner`) — live in the stack's control database
// (`DB_NAME`); every other table in the hub's own, read from the registry once per hub (`db_name`; empty: it still
// shares control's). No statement crosses two databases, so one that names tables of both is refused, saying how to
// split it.

/** Control's tables: the registry, Django's own and phase 1's memberships and session owners (base/tenancy/inventory.py). */
const CONTROL_TABLE = /^(?:auth_\w+|django_\w+|control_\w+|base_hub|base_democode|base_membership|base_sessionowner)$/;
/** A spec's own scratch table (`e2e_…`, `"e2e-…"`): a copy kept while it runs, next to what it copies. */
const SCRATCH_TABLE = /^e2e/;
/** A table a statement names: after `from`, `join`, `into`, `update` or `table` (`if [not] exists` aside). */
const TABLE = /\b(?:from|join|into|update|table)\s+(?:if\s+(?:not\s+)?exists\s+)?"?([a-z_][a-z0-9_]*)"?/gi;

/** The tables `sql` names, in order (a subquery's too). */
export function tablesOf(sql: string): string[] {
  return [...sql.matchAll(TABLE)].map((match) => match[1].toLowerCase());
}

/** The database `sql` runs on: `control` for control's tables, `hubDatabase(hub)` for any other; both is an error. */
export function databaseFor(sql: string, hub: string, control: string, hubDatabase: (slug: string) => string): string {
  // A spec's own scratch tables (`e2e_…`) go where the tables they copy or restore are: they say nothing themselves.
  const tables = tablesOf(sql).filter((table) => !SCRATCH_TABLE.test(table));
  const ofControl = tables.filter((table) => CONTROL_TABLE.test(table));
  const ofHub = tables.filter((table) => !CONTROL_TABLE.test(table));
  if (ofControl.length && ofHub.length) {
    throw new Error(
      `This statement names control's tables (${[...new Set(ofControl)].join(', ')}) and the hub's ` +
        `(${[...new Set(ofHub)].join(', ')}): they live in two databases now. Read control's first and pass the ` +
        `values to the hub's statement.\n${sql}`,
    );
  }
  return ofControl.length ? control : hubDatabase(hub);
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
