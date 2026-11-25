// Types of base/schemas/people.py and roles.py for the SDK (`useLive`, `useCommand`, `client.api.call`), written by
// hand: keep them in step with it and with `frontend/generated/operations.json`.

type NoInput = Record<string, never>;

/** `base.PersonWaysOut`: the account always; at the shared tills, a PIN and a badge. */
export interface PersonWays {
  account: boolean;
  pin: boolean;
  badge: boolean;
}

export type HubRole = 'hub_owner' | 'hub_admin' | 'hub_manager' | 'hub_employee' | 'hub_accountant';

/** `base.PersonOut`: a person of the business (Employees › Personal). */
export interface Person {
  /** Their account's local name in the hub (`saas:<id>`). */
  id: string;
  name: string;
  initials: string;
  /** Null for whoever does not see the team's contact details (`base.view_team_contact`). */
  email: string | null;
  role: HubRole;
  ways: PersonWays;
  /** False: erplora.com names them and they have not entered yet. */
  entered: boolean;
  me: boolean;
}

/** `base.SeatsOut`: the plan's places. */
export interface Seats {
  known: boolean;
  used: number;
  limit: number | null;
  full: boolean;
}

/** `base.PersonDetailOut`: a person's page (who runs the business). */
export interface PersonDetail extends Person {
  pin_set_at: string | null;
  badge_set_at: string | null;
  may: { remove_pin: boolean; set_badge: boolean };
}

/** `base.RoleOut`: one of erplora.com's roles (`basic`, its `HubRole`) or one the business made (`own`, its id). */
export interface HubRoleInfo {
  key: string;
  label: string;
  description: string;
  origin: 'basic' | 'own';
  members: number;
  /** An own one: an app turned on or a permission added after it was saved is still to look at. */
  to_review: boolean;
}

/** `base.RoleRowOut`: a role as the list shows it. */
export interface HubRoleRow extends HubRoleInfo {
  permissions: number;
}

/** What a role does with a permission: on, it holds it; approval, a manager approves it there and then with their
 *  PIN; off, not at all. */
export type RoleState = 'on' | 'approval' | 'off';

/** `base.RolePermissionOut`: a permission in business words, and what the role does with it. */
export interface RolePermission {
  permission: string;
  phrase: string;
  state: RoleState;
}

/** `base.RoleAppOut`: one panel of «What it allows»: the business, an app that is on, or the sensitive data. */
export interface RoleApp {
  app: string;
  name: string;
  permissions: RolePermission[];
}

/** `base.RoleDetailOut`: «What it allows» of a role. */
export interface RoleDetail extends HubRoleInfo {
  apps: RoleApp[];
}

/** `base.RoleUpdateIn`: only what is sent changes. */
export interface RoleChange {
  role: string;
  name?: string;
  description?: string;
  states?: Record<string, RoleState>;
}

/** `base.RoleAssignOut`: the role the person has now, the business's own or the one of their invitation. */
export interface RoleGiven {
  person: string;
  name: string;
  role: string;
  label: string;
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'base.person.list': { input: NoInput; output: { people: Person[]; seats: Seats } };
    'base.person.detail': { input: { person: string }; output: PersonDetail };
    'base.person.pin_remove': { input: { person: string }; output: PersonDetail };
    'base.person.badge_set': { input: { person: string; badge: string }; output: PersonDetail };
    'base.person.badge_remove': { input: { person: string }; output: PersonDetail };
    'base.role.list': { input: NoInput; output: { roles: HubRoleRow[] } };
    'base.role.detail': { input: { role: string }; output: RoleDetail };
    'base.role.create': { input: { based_on: string; name: string; description?: string }; output: HubRoleRow };
    'base.role.update': { input: RoleChange; output: HubRoleRow };
    'base.role.delete': { input: { role: string }; output: { key: string } };
    'base.role.assign': { input: { person: string; role: string }; output: RoleGiven };
  }
}
