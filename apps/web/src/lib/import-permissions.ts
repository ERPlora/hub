// What a template import leaves for the OWNER to decide: the permissions of the apps it brought
// (hub#1905).
//
// A downloaded template never grants a permission by itself — a grant is this owner's approval over
// the host's own primitives (the certificate, the printer), so the runtime refuses the grants of
// another hub's bundle on purpose (hub#473, `crates/runtime/src/import.rs`). What was missing was the
// other half: ASKING. The store already asks when one app is installed (`AppsPage`, pm#132); an
// import installs several at once and asked nothing, so a salon came out of its template with
// VeriFactu and Printing switched off and the first sale went out with no fiscal record.
//
// Pure on purpose: which apps, which permissions and what failed are decided here, where a test can
// argue with them; `ImportPermissionsConsent.vue` only paints and clicks.
import type { ImportReport, ModuleCapability } from './runtime';

/** The permissions still off for one app the import brought. */
export interface PermissionGroup {
  moduleId: string;
  capabilities: ModuleCapability[];
}

/**
 * The apps the import left INSTALLED — whether it installed them now or found them already here.
 * A blocked or failed app is not installed, so it has no switch to flip.
 */
export function appsToAsk(report: ImportReport | null | undefined): string[] {
  return (report?.installed_modules ?? [])
    .filter((m) => m.status === 'installed' || m.status === 'already_installed')
    .map((m) => m.id);
}

/**
 * The permissions each app declares and this hub has NOT granted, one group per app, in the order
 * of `moduleIds`. An app with nothing left is not listed.
 *
 * Best-effort: an app whose permissions cannot be read is left out rather than guessed — the
 * checklist still says it is waiting on a permission (`missing_capabilities`), and Settings →
 * Permissions still has the switch.
 */
export async function pendingPermissions(
  moduleIds: readonly string[],
  read: (moduleId: string) => Promise<ModuleCapability[]>,
): Promise<PermissionGroup[]> {
  const groups = await Promise.all(
    moduleIds.map(async (moduleId): Promise<PermissionGroup | null> => {
      try {
        const capabilities = (await read(moduleId)).filter((c) => c.requested && !c.granted);
        return capabilities.length ? { moduleId, capabilities } : null;
      } catch {
        return null;
      }
    }),
  );
  return groups.filter((g): g is PermissionGroup => g !== null);
}

/**
 * Grants every listed permission, one request per app (the runtime re-checks that the session is
 * an administrator and that the app declares each one). Returns the groups that were NOT granted,
 * so the screen never claims what did not happen.
 */
export async function grantPending(
  groups: readonly PermissionGroup[],
  put: (moduleId: string, grants: Record<string, boolean>) => Promise<void>,
): Promise<PermissionGroup[]> {
  const results = await Promise.all(
    groups.map(async (group) => {
      const grants = Object.fromEntries(group.capabilities.map((c) => [c.id, true]));
      return put(group.moduleId, grants).then(
        () => null,
        () => group,
      );
    }),
  );
  return results.filter((g): g is PermissionGroup => g !== null);
}
