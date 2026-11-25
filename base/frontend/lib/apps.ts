// The rules of the Apps screen the browser
// applies to `base.app.list`, which already says each app's right, state and first screen: the server decides, this
// only chooses what each tab lists and how an app's company is named. Turning an app on or off is the
// server's too (`base.app.enable`, `base.app.disable`), and so is what else its switch changes (each row's
// `along_said`): here only when each is offered and what has to go off first.
import type { AppRow } from '../operations/apps';

/** «My apps», «Add apps» (the whole catalogue) and «Paid» (what is bought apart, on erplora.com). */
export type AppsTab = 'mine' | 'all' | 'paid';

/** Each tab's address hash: the old hub's, kept for its links (`/apps#all`). */
export const TAB_HASH: Readonly<Record<AppsTab, string>> = Object.freeze({ mine: '', all: '#all', paid: '#paid' });

/** The tab an address hash opens; an unknown one is «My apps». Without `paid` (nothing is sold apart)
 *  there is no «Paid», and its old link opens «Add apps», where whatever was sold apart would be. */
export function tabOf(hash: string, paid: boolean): AppsTab {
  if (hash === TAB_HASH.all) return 'all';
  if (hash === TAB_HASH.paid) return paid ? 'paid' : 'all';
  return 'mine';
}

/** Whether the catalogue sells any app apart (`premium`): with every app in every plan none is, and
 *  «Paid» and «Price» would say nothing but «Free». */
export function sellsApart(apps: readonly AppRow[]): boolean {
  return apps.some((app) => app.premium);
}

/** The states of an app the business turned on: on, or its tables still being made in the business's own database
 *  (`creating`) or failed to be (`failed`, tried again): the server's «wanted» (`base.activation`). */
const WANTED: ReadonlySet<AppRow['state']> = new Set(['on', 'creating', 'failed']);

/** The business turned it on: on, or on its way. */
export function isWanted(app: AppRow): boolean {
  return WANTED.has(app.state);
}

/** The rows of a tab: the apps the business turned on (on, or being set up), every app, or the paid ones (never a free
 *  one). */
export function appsOfTab(apps: readonly AppRow[], tab: AppsTab): AppRow[] {
  if (tab === 'mine') return apps.filter(isWanted);
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
  const on = new Set(apps.filter(isWanted).map((row) => row.id));
  return namesOf(
    app.required_by.filter((id) => on.has(id)),
    apps,
  );
}

function namesOf(ids: readonly string[], apps: readonly AppRow[]): string[] {
  const names = new Map(apps.map((row) => [row.id, row.name]));
  return ids.map((id) => names.get(id) ?? id).sort((a, b) => a.localeCompare(b));
}

/** «Turn on»: an app that is off (one without its right is bought on erplora.com, never turned on here) and that the
 *  server would not refuse (its `refusal`: the row says why instead, hub#694). */
export function canTurnOn(app: AppRow): boolean {
  return app.state === 'off' && !app.refusal;
}

/** «Turn off»: an app the business turned on: on, being set up or that could not be (it gives up on it; its tables, if
 *  any were made, stay), and that the server would not refuse (its `refusal`: the row says why instead, hub#618). */
export function canTurnOff(app: AppRow): boolean {
  return isWanted(app) && !app.refusal;
}

/** «Retry»: an app whose tables could not be made in the business's own database (`base.app.retry`). */
export function canRetry(app: AppRow): boolean {
  return app.state === 'failed';
}

/** The names of the apps to turn off before `app`: the chosen ones on (or on their way) that need it (what came along
 *  goes with them), else every one that does; none when nothing on does. */
export function offFirst(app: AppRow, apps: readonly AppRow[]): string[] {
  const byId = new Map(apps.map((row) => [row.id, row]));
  const needing = app.required_by.filter((id) => {
    const row = byId.get(id);
    return row !== undefined && isWanted(row);
  });
  const chosen = needing.filter((id) => byId.get(id)?.chosen);
  return namesOf(chosen.length ? chosen : needing, apps);
}
