// Types of base/schemas/people.py for the SDK (`useLive`, `useCommand`, `client.api.call`), written by
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

/** `base.RoleOut`: one of erplora.com's roles. */
export interface HubRoleRow {
  key: HubRole;
  label: string;
  origin: 'basic';
  members: number;
  permissions: number;
}

/** `base.RolePermissionOut`: a permission in business words, and what the role does with it. */
export interface RolePermission {
  permission: string;
  phrase: string;
  /** on: the role holds it; approval: a manager approves it there and then with their PIN; off: not at all. */
  state: 'on' | 'approval' | 'off';
}

/** `base.RoleAppOut`: one panel of «What it allows»: the business, an app that is on, or the sensitive data. */
export interface RoleApp {
  app: string;
  name: string;
  permissions: RolePermission[];
}

/** `base.RoleDetailOut`: «What it allows» of a basic role. */
export interface RoleDetail {
  key: HubRole;
  label: string;
  origin: 'basic';
  members: number;
  apps: RoleApp[];
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
  }
}
