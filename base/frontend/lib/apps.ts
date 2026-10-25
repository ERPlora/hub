// The rules of the Apps screen (BASE-G67…G74; the old hub's `AppsPage.vue` and `lib/apps-catalog.ts`) the browser
// applies to `base.app.list`, which already says each app's right, state and first screen: the server decides, this
// only chooses what each tab lists and how an app's company is named. Turning an app on or off (PLAN-HUB §9) is the
// server's too (`base.app.enable`, `base.app.disable`): here only when each is offered and what the dialog names —
// what comes along, what goes with it, and what has to go off first.
import type { AppRow } from '../operations';

/** «My apps», «Add apps» (the whole catalogue) and «Paid» (what is bought apart, on erplora.com). */
export type AppsTab = 'mine' | 'all' | 'paid';

/** Each tab's address hash: the old hub's, kept for its links (`/apps#all`). */
export const TAB_HASH: Readonly<Record<AppsTab, string>> = Object.freeze({ mine: '', all: '#all', paid: '#paid' });

/** The tab an address hash opens; an unknown one is «My apps». */
export function tabOf(hash: string): AppsTab {
  if (hash === TAB_HASH.all) return 'all';
  if (hash === TAB_HASH.paid) return 'paid';
  return 'mine';
}

/** The rows of a tab: the apps on, every app, or the paid ones (never a free one: hub#2655). */
export function appsOfTab(apps: readonly AppRow[], tab: AppsTab): AppRow[] {
  if (tab === 'mine') return apps.filter((app) => app.state === 'on');
  if (tab === 'paid') return apps.filter((app) => app.premium);
  return [...apps];
}

/** «Open» leads somewhere: the app is on and has a screen this person may open. */
export function canOpen(app: AppRow): boolean {
  return app.state === 'on' && !!app.path;
}

/** The names of what `app` needs (it comes along with it), sorted; an id the list lacks is named by its id. */
export function comesWith(app: AppRow, apps: readonly AppRow[]): string[] {
  return namesOf(app.requires, apps);
}

/** The apps on that need `app`: what gives a paid app its right when it is not bought itself. */
export function includedWith(app: AppRow, apps: readonly AppRow[]): string[] {
  const on = new Set(apps.filter((row) => row.state === 'on').map((row) => row.id));
  return namesOf(
    app.required_by.filter((id) => on.has(id)),
    apps,
  );
}

function namesOf(ids: readonly string[], apps: readonly AppRow[]): string[] {
  const names = new Map(apps.map((row) => [row.id, row.name]));
  return ids.map((id) => names.get(id) ?? id).sort((a, b) => a.localeCompare(b));
}

/** «Turn on»: an app that is off (one without its right is bought on erplora.com, never turned on here). */
export function canTurnOn(app: AppRow): boolean {
  return app.state === 'off';
}

/** «Turn off»: an app that is on. */
export function canTurnOff(app: AppRow): boolean {
  return app.state === 'on';
}

/** The names of what turning `app` on also turns on: what it needs that is off. */
export function turnsOnWith(app: AppRow, apps: readonly AppRow[]): string[] {
  const off = new Set(apps.filter((row) => row.state === 'off').map((row) => row.id));
  return namesOf(
    app.requires.filter((id) => off.has(id)),
    apps,
  );
}

/** The names of what turning `app` off also turns off: what came along with it (on, not chosen) that no app left on
 *  needs any more — the server's rule (`base.activation.disabling`), for the dialog. */
export function goesOffWith(app: AppRow, apps: readonly AppRow[]): string[] {
  const byId = new Map(apps.map((row) => [row.id, row]));
  const off = new Set([app.id]);
  let changed = true;
  while (changed) {
    changed = false;
    for (const id of app.requires) {
      const row = byId.get(id);
      if (!row || off.has(id) || row.state !== 'on' || row.chosen) continue;
      if (row.required_by.every((other) => off.has(other))) {
        off.add(id);
        changed = true;
      }
    }
  }
  off.delete(app.id);
  return namesOf([...off], apps);
}

/** The names of the apps to turn off before `app`: the chosen ones on that need it (what came along goes with them),
 *  else every app on that needs it; none when nothing on does. */
export function offFirst(app: AppRow, apps: readonly AppRow[]): string[] {
  const byId = new Map(apps.map((row) => [row.id, row]));
  const needing = app.required_by.filter((id) => byId.get(id)?.state === 'on');
  const chosen = needing.filter((id) => byId.get(id)?.chosen);
  return namesOf(chosen.length ? chosen : needing, apps);
}
