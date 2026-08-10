// hub#775 — the SHELL half of the `protects` route guard.
//
// The runtime enforces the contract AUTHORITATIVELY in the dispatcher (every `sales.*` command is
// refused while the drawer is closed, whatever surface calls it). This is the cosmetic half: the
// POS does not even MOUNT — the shell renders `component` (e.g. `erp-cashregister-open`) instead,
// and re-mounts the moment the `resume_on` event fires (`cash_register.session_opened`). Without
// it, the cashier would see the full POS, build a cart and only learn the drawer was closed at
// checkout — the authoritative refusal is correct but the UX it produces alone is hostile.
//
// The contract is cross-module on purpose (see `architecture/` and hub#775): `cash_register` does
// not `depends_on` `sales`, it protects a ROUTE the shell happens to serve with `sales`. So this
// util walks EVERY installed module's manifest for a `protects` block whose `route_setting`'s
// value covers the route we are about to mount, and asks the declaring module's settings + guard
// queries whether the precondition holds. Same resolution order as the runtime's
// `commands::enforce_protects`, so the two halves agree by construction.

import type { ErploraClient } from '@erplora/module-sdk';
import type { ModuleManifest, ModuleProtectsDef } from '@erplora/module-types';

import { loadManifest } from './module-loader';
import { listInstalledModules } from './runtime';

/** The active guard for a route, or `null` if the route is not protected right now. */
export interface ActiveProtectsGuard {
  /** The manifest block that armed the guard (carries `component`, `resume_on`, …). */
  def: ModuleProtectsDef;
  /** The module that declared the guard (e.g. `cash_register`). Used to render its WC. */
  declaringModule: string;
}

/** First row of a query result, or `undefined`. Normalises the single-object and list shapes. */
function firstRow(rows: unknown): Record<string, unknown> | undefined {
  if (Array.isArray(rows)) {
    const r = rows[0];
    return r && typeof r === 'object' ? (r as Record<string, unknown>) : undefined;
  }
  if (rows && typeof rows === 'object') return rows as Record<string, unknown>;
  return undefined;
}

/** Boolean column that may be stored as 0/1 (Postgres INTEGER) or a real boolean. */
function truthy(v: unknown): boolean {
  if (typeof v === 'boolean') return v;
  if (typeof v === 'number') return v !== 0;
  if (typeof v === 'string') return v === '1' || v === 'true';
  return false;
}

/**
 * Does `routeValue` (a declared `route_setting`) cover `currentPath`? The shell serves `/m/<module>`
 * and `/m/<module>/<navId>`; a guard declared as `/m/sales` or `/m/sales/pos` covers both
 * `/m/sales` and `/m/sales/pos`. Comparison is by path SEGMENT prefix so a trailing slash and a
 * deeper navId do not defeat a guard that protects the whole module's surface.
 */
export function routeCoversPath(routeValue: string, currentPath: string): boolean {
  if (!routeValue) return false;
  const norm = (p: string) => p.replace(/\/+$/, '').replace(/\/+/g, '/');
  const a = norm(routeValue);
  const b = norm(currentPath);
  if (a === b) return true;
  // `/m/sales` covers `/m/sales/pos` (a prefix by segment), but NOT `/m/salesforce`.
  return b.startsWith(a + '/');
}

/**
 * Resolves the active `protects` guard for mounting the module at `currentPath`, or `null` if the
 * route is unprotected. Mirrors the runtime's `commands::enforce_protects` resolution so the two
 * halves agree: it arms the guard only when the declaring module's `enabled_setting` is true and
 * its `route_setting` covers the path, and it reports the guard only when `guard_query` is unmet.
 *
 * Degrades OPEN (returns `null`) on any read failure: a till that refuses to render over a broken
 * read is a worse failure than one that renders and lets the authoritative dispatcher refuse. The
 * dispatcher is the load-bearing half; this is the UX.
 */
export async function resolveProtectsGuard(
  client: ErploraClient,
  currentPath: string,
): Promise<ActiveProtectsGuard | null> {
  // The set of modules to scan: installed AND active. `listInstalledModules` carries both.
  let installed: { id: string; status: string }[];
  try {
    installed = await listInstalledModules();
  } catch {
    return null;
  }
  for (const m of installed) {
    if (m.status !== 'active') continue;
    let manifest: ModuleManifest | null;
    try {
      manifest = await loadManifest(m.id);
    } catch {
      manifest = null;
    }
    if (!manifest?.protects?.length) continue;

    for (const def of manifest.protects) {
      // (1) settings row — system context is the runtime's default for these queries.
      let settings: Record<string, unknown> | undefined;
      try {
        settings = firstRow(await client.query(def.settings_query, {}));
      } catch {
        continue; // degrade open — the dispatcher is authoritative
      }
      if (!settings) continue;

      // (2) armed? `false`/absent → dormant.
      if (!truthy(settings[def.enabled_setting])) continue;

      // (3) does this guard cover the route we are mounting?
      const routeValue = String(settings[def.route_setting] ?? '');
      if (!routeCoversPath(routeValue, currentPath)) continue;

      // (4) precondition met? `non_empty` is satisfied by at least one row.
      let rows: unknown;
      try {
        rows = await client.query(def.guard_query, {});
      } catch {
        continue; // degrade open
      }
      const satisfied = def.expect === 'non_empty' ? Array.isArray(rows) && rows.length > 0 : true;
      if (satisfied) continue;

      return { def, declaringModule: m.id };
    }
  }
  return null;
}
