// The three questions an installed app's card has to answer before it touches anything (hub#773).
//
// «Apps → My apps» ended each card in two unnamed pictograms — a power symbol and a bin — and no
// way to OPEN the app they belong to. Whatever the icons look like, the answers below are the part
// that must be right: which apps break if this one goes, which direction the switch moves in, and
// whether there is a screen to open at all. They live here, out of the screen, so the answers are
// held by tests rather than by a screenshot.

import type { ModuleNavItem } from './nav';
import type { InstalledModule } from './runtime';

/** The shell route that mounts a module's own screen. */
export function moduleRoutePath(id: string): string {
  return `/m/${id}`;
}

/**
 * Is there a screen to open for this app?
 *
 * Two conditions, and the second is not redundant. `/api/navigation` already answers only for
 * ACTIVE modules, so an app that is switched off is normally absent from `nav` — but that list is
 * refreshed asynchronously after a toggle, and for the moment it is stale a card would offer a door
 * that is bolted. A module missing from `nav` altogether is one that paints nothing (migrations,
 * events, a scheduled task): «Open» there leads to an empty page.
 */
export function canOpenModule(
  m: Pick<InstalledModule, 'id' | 'status'>,
  nav: readonly ModuleNavItem[],
): boolean {
  if (m.status !== 'active') return false;
  const path = moduleRoutePath(m.id);
  return nav.some((entry) => entry.path === path);
}

/** What pressing the switch would DO — the future state, which is what the label must say. */
export function toggleIntent(status: InstalledModule['status']): 'activate' | 'deactivate' {
  // `inactive_auto` (ADR-0128) is «off because something I depend on went off». The press still
  // moves towards on, and the cascade brings the dependency back with it.
  return status === 'active' ? 'deactivate' : 'activate';
}

/**
 * The apps that would break if `id` were uninstalled — transitively, whatever their status.
 *
 * Deliberately NOT the same set as the deactivation cascade. That one only looks at ACTIVE
 * dependants, because switching off what is already off changes nothing. Uninstalling removes the
 * package: an inactive dependant can never be switched back on afterwards, so it belongs in the
 * confirmation just as much.
 *
 * Breadth-first from `id`, tracking what has already fallen, so a manifest that declares a cycle
 * ends the walk instead of hanging the dialog.
 */
export function dependentsOf(id: string, installed: readonly InstalledModule[]): InstalledModule[] {
  const fallen = new Set([id]);
  const out: InstalledModule[] = [];
  let grew = true;
  while (grew) {
    grew = false;
    for (const m of installed) {
      if (fallen.has(m.id)) continue;
      if ((m.depends_on ?? []).some((d) => fallen.has(d))) {
        fallen.add(m.id);
        out.push(m);
        grew = true;
      }
    }
  }
  return out;
}
