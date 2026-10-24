// The rules of the Apps screen (BASE-G67…G74; the old hub's `AppsPage.vue` and `lib/apps-catalog.ts`) the browser
// applies to `base.app.list`, which already says each app's right, state and first screen: the server decides, this
// only chooses what each tab lists and how an app's company is named.
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
