// System's tabs go in the address hash, so Back and a saved link open the same one; «Usage and plan» opens when the
// hash names none, and also for the old `#resources` and `#plan`, whose links keep working. Logs is only for whoever
// runs the business: for anyone else `#logs` opens «Usage and plan». The reasons of a failed resend or discard are
// named from the error's code, never from the Hub's text.
export type SystemTab = 'usage' | 'updates' | 'events' | 'logs';

export const SYSTEM_TABS: readonly SystemTab[] = Object.freeze(['usage', 'updates', 'events', 'logs']);

export const TAB_HASH: Readonly<Record<SystemTab, string>> = Object.freeze({
  usage: '#usage',
  updates: '#updates',
  events: '#events',
  logs: '#logs',
});

/** The retired `#backups` tab: its copies now live in Settings › Data, where this hash leads. */
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
