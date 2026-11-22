// Types of base/schemas/access.py for the SDK (`useLive`, `useCommand`, `client.api.call`), written by
// hand: keep them in step with it and with `frontend/generated/operations.json`.

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

declare module '@erplora/ui/sdk' {
  interface Operations {
    'base.access.grantors': { input: NoInput; output: Grantors };
    'base.session.access': { input: NoInput; output: SessionAccess };
    'base.access.door': { input: NoInput; output: AccessDoor };
    'base.access.faces': { input: NoInput; output: AccessDoor };
    'base.access.settings': { input: NoInput; output: AccessSettings };
    'base.access.settings_update': {
      input: Partial<Pick<AccessSettings, 'pin_policy' | 'pin_inactivity_minutes' | 'pin_length'>>;
      output: AccessSettings;
    };
  }
}
