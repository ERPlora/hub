// Employees (APP-BASE-5; the old hub's EmployeesPage, HUB_SHELL-F80…F98): Personal, Roles, API keys and Approvals,
// each in the address hash so Back and a saved link open the same one; Personal when the hash names none. API keys and
// Approvals are only for who runs the business: for anyone else the tab does not exist and its hash opens Personal (the
// old hub left a blank page there). How each person gets in, and what a badge looks like before it is sent.
import type { HubRole, PersonWays } from '../operations';

export type EmployeesTab = 'personal' | 'roles' | 'apikeys' | 'approvals';

export const EMPLOYEES_TABS: readonly EmployeesTab[] = Object.freeze(['personal', 'roles', 'apikeys', 'approvals']);

export const EMPLOYEES_TAB_HASH: Readonly<Record<EmployeesTab, string>> = Object.freeze({
  personal: '',
  roles: '#roles',
  apikeys: '#apikeys',
  approvals: '#approvals',
});

const ADMIN_ONLY: ReadonlySet<EmployeesTab> = new Set(['apikeys', 'approvals']);

/** The tabs `admin` (who runs the business) sees, in order. */
export function employeesTabsFor(admin: boolean): EmployeesTab[] {
  return EMPLOYEES_TABS.filter((tab) => admin || !ADMIN_ONLY.has(tab));
}

/** The tab an address hash opens for `admin`; Personal for none, an unknown one or one this person does not have. */
export function employeesTabOf(hash: string, admin: boolean): EmployeesTab {
  const tab = employeesTabsFor(admin).find((candidate) => candidate !== 'personal' && EMPLOYEES_TAB_HASH[candidate] === hash);
  return tab ?? 'personal';
}

/** The catalogue keys of how a person gets in: the account always, then the PIN and the badge the hub keeps. */
export function accessKeys(ways: PersonWays): string[] {
  const keys = ['base.people.ways.account'];
  if (ways.pin) keys.push('base.people.ways.pin');
  if (ways.badge) keys.push('base.people.ways.badge');
  return keys;
}

/** The catalogue key of one of erplora.com's roles. */
export function roleKey(role: HubRole): string {
  return `base.people.roles.${role}`;
}

const BADGE = /^[A-Za-z0-9_-]{4,64}$/;

/** What is wrong with a badge typed or read, the server's rule (`base.access.clean_badge`); `null` when it is one. */
export function badgeProblem(raw: string): 'empty' | 'invalid' | null {
  const badge = raw.trim();
  if (badge === '') return 'empty';
  return BADGE.test(badge) ? null : 'invalid';
}
