// System's tabs (BASE-G87; the old hub's lib/system-tabs.ts): Resources, Plan and limits, Updates, Failed events and
// Logs, each in the address hash so Back and a saved link open the same one; Resources when the hash names none.
// Logs is only for who runs the business (hub#2519): for anyone else the tab does not exist and `#logs` opens
// Resources. The old `#backups` is no tab any more: its copies live in Settings › Data. And the reasons of a failed
// resend or discard (BASE-G92…G94), named from the error's code, never from the Hub's text.
export type SystemTab = 'resources' | 'plan' | 'updates' | 'events' | 'logs';

export const SYSTEM_TABS: readonly SystemTab[] = Object.freeze(['resources', 'plan', 'updates', 'events', 'logs']);

export const TAB_HASH: Readonly<Record<SystemTab, string>> = Object.freeze({
  resources: '#resources',
  plan: '#plan',
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

/** The tab an address hash opens for `admin`; Resources for none, an unknown one or one this person does not have. */
export function tabOf(hash: string, admin: boolean): SystemTab {
  const tab = tabsFor(admin).find((candidate) => TAB_HASH[candidate] === hash);
  return tab ?? 'resources';
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
