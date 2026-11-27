// Types of base/schemas/access.py and base/schemas/support_access.py for the SDK (`useLive`, `useCommand`,
// `client.api.call`), written by hand: keep them in step with them and with `frontend/generated/operations.json`.

type NoInput = Record<string, never>;

/** `base.PinPersonOut`: a face of the PIN pad's grid; `id` is what a PIN entry names, never the account. */
export interface PinPerson {
  id: string;
  name: string;
  initials: string;
}

/** `base.AccessDoorOut`: what this browser offers to enter (`base.access.door`) or to switch user (`base.access.faces`). */
export interface AccessDoor {
  /** A shared device of the hub of a business that asks: the PIN pad. */
  pin: boolean;
  pin_length: number;
  people: PinPerson[];
  /** Seconds this address still waits after too many wrong PINs. */
  wait: number;
  /** erplora.com's plans («Upgrade plan» after another device's entry ended this one). */
  plan_url: string;
}

export type PinPolicy = 'always' | 'per_shift' | 'never';
export type IdleMinutes = 1 | 5 | 10 | 15 | 30;

/** `base.AccessSettingsOut`: how the business asks who is at the till. */
export interface AccessSettings {
  pin_policy: PinPolicy;
  pin_inactivity_minutes: IdleMinutes;
  pin_length: 4 | 6;
  can_change: boolean;
}

/** `base.GrantorsOut`: who can give the person a screen it may not open, by name only («No access»). */
export interface Grantors {
  grantors: { name: string }[];
}

/** `base.SessionAccessOut`: a key of the session's permissions, which changes exactly when they do. */
export interface SessionAccess {
  key: string;
}

/** `base.SessionIdleOut`: after how many idle minutes this device's till locks; null, it does not. */
export interface SessionIdle {
  idle_minutes: number | null;
}

/** `base.SupportVisitOut`: one time a person of ERPlora's support came into the business. */
export interface SupportVisit {
  person: string;
  entered_at: string;
}

/** `base.SupportAccessOut`: whether ERPlora's support may come into the business, and who of support came in. */
export interface SupportAccess {
  enabled: boolean;
  can_change: boolean;
  /** Empty if nobody has changed it. */
  updated_by: string;
  updated_at: string | null;
  /** The most recent first. */
  visits: SupportVisit[];
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'base.access.grantors': { input: NoInput; output: Grantors };
    'base.session.access': { input: NoInput; output: SessionAccess };
    'base.session.idle': { input: NoInput; output: SessionIdle };
    'base.access.door': { input: NoInput; output: AccessDoor };
    'base.access.faces': { input: NoInput; output: AccessDoor };
    'base.access.settings': { input: NoInput; output: AccessSettings };
    'base.access.settings_update': {
      input: Partial<Pick<AccessSettings, 'pin_policy' | 'pin_inactivity_minutes' | 'pin_length'>>;
      output: AccessSettings;
    };
    'base.support_access.get': { input: NoInput; output: SupportAccess };
    'base.support_access.update': { input: { enabled: boolean }; output: SupportAccess };
  }
}
