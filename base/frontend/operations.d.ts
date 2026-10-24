// Types of base's Home queries for the SDK (`useLive`, `client.api.call`), from base/schemas.py. Written by
// hand, as the apps', until V3 generates them from `/api/openapi.json`. Keep it in step with schemas.py and
// `frontend/generated/operations.json`. No input: each one answers for the person and the hub of the request.

type NoInput = Record<string, never>;

/** `base.SetupItemOut`: one step of «Finish setting up your business». */
export interface SetupItem {
  /** «<app>.<step>»: «base.apps», «base.team» or a module's own step. */
  key: string;
  app: string;
  /** «unavailable»: ours, not the person's task. */
  state: 'done' | 'pending' | 'unavailable';
  /** «legal» (⛔, needed to invoice), «functional» (🔴) or «recommended» (🟡). */
  level: 'legal' | 'functional' | 'recommended';
  required: boolean;
  /** False: a pending ⛔ that this person cannot set up (an administrator must). */
  actionable: boolean;
  title: string;
  description: string;
  icon: string;
  /** The screen that completes it. */
  route: string;
  order: number;
}

/** `base.SetupStatusOut`. */
export interface SetupStatus {
  total: number;
  pending: number;
  unavailable: number;
  /** Pending ⛔ steps: the invoice is refused until they are done. */
  blocking_pending: number;
  items: SetupItem[];
}

export type WidgetKind = 'kpi' | 'stat' | 'sparkline' | 'bar-list' | 'timeline' | 'chart';

/** `base.WidgetOut`: a panel this person may put on the dashboard. */
export interface WidgetDef {
  /** «<app>.<panel>». */
  key: string;
  app: string;
  title: string;
  icon: string;
  /** The group of the picker. */
  category: string;
  size: 'sm' | 'md' | 'lg';
  /** On by default, before the person chooses. */
  default: boolean;
  kind: WidgetKind | null;
  operation: string | null;
  params: Record<string, unknown>;
  /** Prop of the panel → field of the operation's result. */
  map: Record<string, string>;
  /** Literal props of the panel. */
  options: Record<string, unknown>;
  /** A Vue component of the app's frontend/components/, without «.vue». */
  component: string | null;
  refresh_on: string[];
  /** Its operation is a live query: followed, else asked once. */
  live: boolean;
}

/** `base.BellCounterOut`. */
export interface BellCounter {
  /** «<app>.<counter>», or «base.failed_events». */
  key: string;
  app: string;
  count: number;
  route: string;
  label: string;
  icon: string;
}

/** `base.DeviceNoticeOut`: a row the device is told once (APPOINTMENT-F28). */
export interface DeviceNoticeRow {
  /** «<app>.<notice>». */
  key: string;
  app: string;
  id: string;
  at: string;
  title: string;
  body: string;
  /** The screen a tap opens; empty when it names none. */
  route: string;
}

// ── The way in (APP-BASE-3) ────────────────────────────────────────────────────────────────────────────────────

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

export type DeviceMode = 'shared' | 'personal';

/** `base.DeviceCurrentOut`: the device in hand. */
export interface DeviceCurrent {
  known: boolean;
  mode: DeviceMode;
  mode_set_by: string;
  mode_set_at: string | null;
}

/** `base.DeviceOut`: a device someone entered this hub on. */
export interface DeviceRow {
  id: string;
  name: string;
  agent: string;
  mode: DeviceMode;
  current: boolean;
  in_use: boolean;
  session_until: string | null;
  last_entry_at: string;
  last_user: string;
  created_at: string;
  unused: boolean;
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

export type ProfileLanguage = '' | 'es' | 'en';
export type ProfileThemeMode = '' | 'system' | 'light' | 'dark';

/** `base.ProfileOut`: «My profile». Empty language, mode or palette: the business's. */
export interface Profile {
  first_name: string;
  last_name: string;
  contact_email: string;
  avatar_url: string;
  language: ProfileLanguage;
  theme_mode: ProfileThemeMode;
  palette: string;
  role: string;
  has_pin: boolean;
  pin_length: number;
}

/** `base.PreferencesIn` / `PreferencesOut`. */
export interface Preferences {
  language: ProfileLanguage;
  theme_mode: ProfileThemeMode;
  palette: string;
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'base.setup.status': { input: NoInput; output: SetupStatus };
    'base.widget.list': { input: NoInput; output: { widgets: WidgetDef[] } };
    'base.bell.counters': { input: NoInput; output: { counters: BellCounter[] } };
    'base.notice.list': { input: NoInput; output: { notices: DeviceNoticeRow[]; sources: string[] } };
    // The way in (APP-BASE-3)
    'base.access.door': { input: NoInput; output: AccessDoor };
    'base.access.faces': { input: NoInput; output: AccessDoor };
    'base.pin.set': { input: { pin: string; current?: string }; output: { set: boolean } };
    'base.device.current': { input: NoInput; output: DeviceCurrent };
    'base.device.mode_set': { input: { mode: DeviceMode }; output: DeviceCurrent };
    'base.device.list': { input: NoInput; output: { devices: DeviceRow[]; unused: number } };
    'base.device.rename': { input: { id: string; name: string }; output: { id: string } };
    'base.device.remove': { input: { id: string }; output: { removed: number; yours: boolean } };
    'base.device.prune': { input: NoInput; output: { removed: number } };
    'base.access.settings': { input: NoInput; output: AccessSettings };
    'base.access.settings_update': {
      input: Partial<Pick<AccessSettings, 'pin_policy' | 'pin_inactivity_minutes' | 'pin_length'>>;
      output: AccessSettings;
    };
    'base.profile.get': { input: NoInput; output: Profile };
    'base.profile.update': { input: { first_name: string; last_name: string; contact_email: string }; output: Profile };
    'base.profile.preferences_set': { input: Preferences; output: Preferences };
    'base.profile.avatar_set': {
      input: { content_type: 'image/jpeg' | 'image/png' | 'image/webp'; data_base64: string };
      output: { avatar_url: string };
    };
    'base.profile.avatar_remove': { input: NoInput; output: { avatar_url: string } };
  }
}
