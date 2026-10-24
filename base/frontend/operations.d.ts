// Types of base's operations for the SDK (`useLive`, `useCommand`, `client.api.call`), from base/schemas.py. Written by
// hand, as the apps', until V3 generates them from `/api/openapi.json`. Keep it in step with schemas.py and
// `frontend/generated/operations.json`. The Home's take no input: each one answers for the person and the hub of the request.

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

// ── Apps (APP-BASE-4) ──────────────────────────────────────────────────────────────────────────────────────

/** Where a module's right comes from (`base.entitlement`): free, the plan, a purchase, with an app that needs it,
 *  or none (it needs a subscription, bought on erplora.com). */
export type AppRight = 'free' | 'plan' | 'purchase' | 'required' | 'missing';

/** `base.AppOut`: a module of the deployment as the Apps screen paints it. */
export interface AppRow {
  id: string;
  name: string;
  icon: string;
  category: string;
  category_label: string;
  summary: string;
  /** Bought on erplora.com; the Store has its price. */
  premium: boolean;
  right: AppRight;
  /** «blocked»: no right to it (phase 2 adds turned off, activating and failed). */
  state: 'on' | 'blocked';
  /** The first screen of its menu this person may open; null: no «Open». */
  path: string | null;
  /** What it needs, transitively (it comes along with it), and the apps that need it: ids. */
  requires: string[];
  required_by: string[];
}

/** `base.AppListOut`. */
export interface AppList {
  apps: AppRow[];
  /** erplora.com's Store of this business's modules. */
  store_url: string;
}

/** `base.LimitOut`: what is in use (null: the Hub does not count it) against the plan's limit (null: none). */
export interface PlanLimit {
  used: number | null;
  limit: number | null;
}

/** `base.PlanUsageOut`: «Plan and limits» of System. */
export interface PlanUsage {
  /** Whether the Hub has the business's plan from erplora.com yet. */
  known: boolean;
  people: PlanLimit;
  devices: PlanLimit;
}

// ── Data: blueprints, imports and reset (APP-BASE-2) ──

export type BlueprintPurpose = 'backup' | 'template';
/** How a dataset of a load went (`base.DatasetStatus`). */
export type DatasetStatus = 'applied' | 'partial' | 'already' | 'failed' | 'empty' | 'discarded';
/** How an app of a load went (`base.AppLoadStatus`). */
export type AppLoadStatus = DatasetStatus | 'inactive' | 'unknown' | 'not_selected';
export type ImportStatus = 'complete' | 'partial' | 'failed';

export interface BlueprintApp {
  id: string;
  label: string;
}

/** «<app>.<what>»: a dataset, e.g. «inventory.product». */
export interface BlueprintPart {
  key: string;
  label: string;
  rows: number;
}

/** `base.TemplateOut`: a seed of the catalogue. */
export interface Template {
  /** «<vertical>.<language>». */
  key: string;
  name: string;
  description: string;
  language: string;
  /** ISO 3166. */
  country: string;
  vertical: string;
  version: string;
  apps: BlueprintApp[];
  contents: BlueprintPart[];
}

export interface BlueprintDataset extends BlueprintPart {
  personal: boolean;
  /** False: left out of this load (personal data in a template). */
  travels: boolean;
}

export interface BlueprintAppSummary extends BlueprintApp {
  status: 'on' | 'inactive' | 'unknown';
  datasets: BlueprintDataset[];
}

/** `base.BlueprintSummaryOut`: what a template or a file brings, before loading it. */
export interface BlueprintSummary {
  name: string;
  language: string;
  country: string;
  purpose: BlueprintPurpose;
  /** Empty for a template of the catalogue. */
  created_at: string;
  /** Empty for a file. */
  version: string;
  source: 'catalog' | 'file';
  apps: BlueprintAppSummary[];
  /** Parts of the file this hub never loads (people, fiscal data…), already in words. */
  dropped: string[];
}

export interface DatasetLoad extends BlueprintPart {
  status: DatasetStatus;
  created: number;
  already: number;
  failed: number;
  problems: string[];
}

export interface AppLoad extends BlueprintApp {
  status: AppLoadStatus;
  datasets: DatasetLoad[];
}

export interface LoadReport {
  status: ImportStatus;
  apps: AppLoad[];
  dropped: string[];
}

export type RetryBlocked = '' | 'file' | 'version_gone' | 'complete' | 'undone';

/** `base.ImportOut`: one load and its report. */
export interface ImportRow {
  id: string;
  name: string;
  source: 'catalog' | 'file';
  template_key: string;
  status: ImportStatus;
  created_at: string;
  created_by: string;
  /** Rows it created. */
  rows: number;
  undone: boolean;
  undoable: boolean;
  retry: boolean;
  retry_blocked: RetryBlocked;
  report: LoadReport;
}

export interface BlueprintSource {
  template?: string;
  file_base64?: string;
}

export interface BlueprintImportInput extends BlueprintSource {
  /** The apps to load; none = every app of the blueprint. */
  apps?: string[] | null;
  /** A load that did not go in whole: load again what did not. */
  retry_of?: string | null;
}

export interface BlueprintExportInput {
  name: string;
  language: string;
  purpose: BlueprintPurpose;
  apps: string[];
  data: string[];
  /** Of the apps whose data travels, the datasets chosen; an app none of whose datasets is named takes all. */
  datasets: string[];
}

export interface DatasetCount extends BlueprintPart {
  personal: boolean;
}

export interface AppDatasets extends BlueprintApp {
  icon: string;
  /** Empty: the app travels, with nothing of its own to copy. */
  datasets: DatasetCount[];
}

export interface Removal extends BlueprintApp {
  removed: number;
  failed: number;
  problems: string[];
}

export interface ResetSection extends BlueprintApp {
  rows: number;
  datasets: BlueprintPart[];
}

/** `base.HubResetOut`. */
export interface HubReset {
  dry_run: boolean;
  /** What to type to confirm: the business's name. */
  confirm_with: string;
  /** False in phase 1: the business shares its database with other hubs. */
  available: boolean;
  sections: ResetSection[];
  apps: Removal[];
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
    // Apps (APP-BASE-4)
    'base.app.list': { input: NoInput; output: AppList };
    'base.plan.usage': { input: NoInput; output: PlanUsage };
    // ── Data (APP-BASE-2) ──
    'base.blueprint.list': { input: NoInput; output: { templates: Template[]; empty: boolean } };
    'base.blueprint.inspect': { input: BlueprintSource; output: BlueprintSummary };
    'base.blueprint.import': { input: BlueprintImportInput; output: ImportRow };
    'base.blueprint.export': {
      input: BlueprintExportInput;
      output: { filename: string; content_type: string; content_base64: string };
    };
    'base.import.list': { input: NoInput; output: { imports: ImportRow[]; unfinished: ImportRow | null } };
    'base.import.undo': { input: { id: string }; output: { id: string; apps: Removal[] } };
    'base.dataset.list': { input: NoInput; output: { apps: AppDatasets[] } };
    'base.hub.reset': {
      input: { apps?: string[]; confirm?: string; dry_run?: boolean };
      output: HubReset;
    };

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
