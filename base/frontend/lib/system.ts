// System's tabs (BASE-F39, BASE-G87): «Usage and plan», Updates, Failed events and Logs, each in the address hash so Back
// and a saved link open the same one; «Usage and plan» when the hash names none, and so also for the two tabs it took over
// (`#resources` and `#plan`, BASE-F40), whose old links keep working. Logs is only for who runs the business (hub#2519):
// for anyone else the tab does not exist and `#logs` opens «Usage and plan». The old `#backups` is no tab any more: its
// copies live in Settings › Data. And the reasons of a failed resend or discard (BASE-G92…G94), named from the error's
// code, never from the Hub's text.
export type SystemTab = 'usage' | 'updates' | 'events' | 'logs';

export const SYSTEM_TABS: readonly SystemTab[] = Object.freeze(['usage', 'updates', 'events', 'logs']);

export const TAB_HASH: Readonly<Record<SystemTab, string>> = Object.freeze({
  usage: '#usage',
  updates: '#updates',
  events: '#events',
  logs: '#logs',
});

/** Where the retired `#backups` goes: Settings › Data (APP-BASE-2). */
export const BACKUPS_HASH = '#backups';
export const BACKUPS_TARGET = Object.freeze({ path: '/settings', hash: '#data' });

const ADMIN_ONLY: ReadonlySet<SystemTab> = new Set(['logs']);

/** The tabs `admin` (who runs the business) sees, in order. */
export function tabsFor(admin: boolean): SystemTab[] {
  return SYSTEM_TABS.filter((tab) => admin || !ADMIN_ONLY.has(tab));
}

/** The tab an address hash opens for `admin`; «Usage and plan» for none, an unknown one or one this person does not have. */
export function tabOf(hash: string, admin: boolean): SystemTab {
  const tab = tabsFor(admin).find((candidate) => TAB_HASH[candidate] === hash);
  return tab ?? 'usage';
}

const REASONS: Readonly<Record<string, string>> = Object.freeze({
  not_found: 'gone',
  'base.failed_event_app_off': 'appOff',
  permission_denied: 'denied',
});

/** The catalogue key of why a resend or a discard failed, from the error's code. */
export function failureKey(code: string | undefined): string {
  return `base.system.failed.reasons.${(code && REASONS[code]) ?? 'unknown'}`;
}
