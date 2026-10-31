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

/** `base.BellCountersOut`: the counters above zero, and how often the bell reads them again (none: only on a change). */
export interface BellCounters {
  counters: BellCounter[];
  refresh_every: number | null;
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
  /** «off»: the business turned it off (or never on); «blocked»: no right to it (phase 2 adds activating and failed). */
  state: 'on' | 'off' | 'blocked';
  /** Turned on by the business itself (what the plan's limit counts); what came along with another app is not. */
  chosen: boolean;
  /** The first screen of its menu this person may open; null: no «Open». */
  path: string | null;
  /** What it needs, transitively (it comes along with it), and the apps on that need it (they go off first): ids. */
  requires: string[];
  required_by: string[];
}

/** `base.AppListOut`. */
export interface AppList {
  apps: AppRow[];
  /** erplora.com's Store of this business's modules. */
  store_url: string;
  /** erplora.com's plans of this business, where a higher limit of apps is bought. */
  plan_url: string;
  /** How many apps the plan lets the business choose; null: no limit. */
  max_apps: number | null;
  /** How many it chose and are on (what came along with them does not count). */
  enabled: number;
}

/** `base.AppChangeIn`: one app of the business, by its name as the person says it or by its id. */
export interface AppChangeIn {
  app: string;
}

/** `base.AppChangeOut`: the app as it is now, and the apps that went on (or off) with it. */
export interface AppChange {
  app: string;
  state: 'on' | 'off';
  chosen: boolean;
  along: { id: string; name: string }[];
  /** It was on already (turning it on) or off already (turning it off): nothing went on or off. */
  already: boolean;
}

/** `base.AppRefIn`: one app of the business, by its name or its id. */
export interface AppRefIn {
  app: string;
}

/** `base.AppRefOut`: which app a name names, with its state as the Apps screen says it. */
export interface AppRef {
  id: string;
  name: string;
  state: 'on' | 'off' | 'blocked';
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
  /** «turns_on»: off here, the load turns it on first and then loads it (round 2026-10-27); «inactive»: left off. */
  status: 'on' | 'turns_on' | 'inactive' | 'unknown';
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
  /** Why an app of the blueprint that was off could not be turned on («inactive»), in words; empty otherwise. */
  reason?: string;
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

// ── Business settings (APP-BASE-6) ──

/** `base.BusinessOut`: the business as erplora.com registered it, each value named in the person's language. */

// ── The shared image library (round 2026-10-30, base/image_catalog.py) ──

/** An image of the library: what a product, a service or a set menu keeps is its `reference`. */
export interface CatalogImage {
  /** `catalog:<folder>/<name>`. */
  reference: string;
  folder: string;
  name: string;
  /** In the business's language (in English when it is not Spanish); in the person's for `.get`. */
  title: string;
  /** `/p/catalog/<folder>/<name>.webp`, cached for a year. */
  url: string;
}

export interface CatalogImageSearchIn {
  /** Spanish or English; empty: the whole library (or folder) by title. */
  query?: string;
  /** beauty_body, beauty_hair, fitness, hospitality, retail or wellness_spa. */
  folder?: string | null;
  /** 1 to 100; 60 by default. */
  limit?: number;
  offset?: number;
}

export interface CatalogImagePage {
  rows: CatalogImage[];
  total: number;
  limit: number;
  offset: number;
}

export interface Business {
  /** On ERPlora's own hub, its issuer's legal name; empty in a demo. */
  name: string;
  /** ISO 3166-1 alpha-2; empty in a demo. */
  country: string;
  country_name: string;
  /** IANA zone: the business's clock. */
  timezone: string;
  language: string;
  language_name: string;
  /** ISO 4217: the country's (the euro without a country). */
  currency: string;
  /** «EUR · Euro». */
  currency_label: string;
  currency_decimals: number;
  demo: boolean;
  /** The business's settings on erplora.com; empty in a demo and on ERPlora's own hub. */
  settings_url: string;
}

// ── System (APP-BASE-7) ──

/** `base.SystemStatusOut`: the release running and where the business's data lives. */
export interface SystemStatus {
  /** The commit, short; `dev` locally. */
  version: string;
  /** When it was published (ISO 8601), or null: never made up. */
  released_at: string | null;
  /** Phase 1: the database every business shares. */
  shared_database: boolean;
}

/** `base.EventLogEntryOut`: an event between apps as System › Logs shows it. */
export interface EventLogEntry {
  id: string;
  at: string;
  level: 'info' | 'warning' | 'error';
  name: string;
  app: string;
  app_name: string;
  detail: string;
}

/** `base.FailedEventOut`: a delivery the relay gave up on. */
export interface FailedEvent {
  /** The delivery: what is resent or discarded. */
  id: string;
  event_id: string;
  name: string;
  source_app: string;
  source_app_name: string;
  target_app: string;
  target_app_name: string;
  attempts: number;
  occurred_at: string;
  last_error: string;
  /** False: the app it was for is no longer on in this business. */
  retryable: boolean;
}

/** `base.FailedEventListOut`. */
export interface FailedEventPage {
  items: FailedEvent[];
  total: number;
}

// ── Files (APP-BASE-8) ──

/** How the screen shows a file (`base.schemas.FilePreview`); `''`: it does not, it is downloaded. */
export type FilePreview = 'image' | 'pdf' | 'text' | 'table' | 'json' | 'audio' | 'video' | '';

/** `base.FileFolderOut`: a folder of the business's files and the folders in it. */
export interface FileFolder {
  /** «Facturas/2026». */
  path: string;
  name: string;
  children: FileFolder[];
}

/** `base.FileItemOut`: a file of the open folder. */
export interface FileItem {
  path: string;
  name: string;
  size: number;
  /** ISO time it was last written; `null` when the store keeps none. */
  modified: string | null;
  /** The type `base.file.read` serves it with. */
  content_type: string;
  preview: FilePreview;
}

/** `base.FileListOut`. */
export interface FilesListing {
  folder: string;
  crumbs: { path: string; name: string }[];
  folders: FileFolder[];
  files: FileItem[];
  /** What the hub's files take, against the plan's space (`limit_bytes: null`: no limit). */
  space: { used_bytes: number; limit_bytes: number | null };
  /** Upload, new folder and rename; delete (moving takes both). */
  can: { upload: boolean; delete: boolean };
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

// ── People and permissions (APP-BASE-5) ──

/** `base.PersonWaysOut`: the account always; at the shared tills, a PIN and a badge. */
export interface PersonWays {
  account: boolean;
  pin: boolean;
  badge: boolean;
}

export type HubRole = 'hub_owner' | 'hub_admin' | 'hub_manager' | 'hub_employee';

/** `base.PersonOut`: a person of the business (Employees › Personal). */
export interface Person {
  /** Their account's local name in the hub (`saas:<id>`). */
  id: string;
  name: string;
  initials: string;
  /** Empty for whom does not run the business (their own, always). */
  email: string;
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

/** `base.RoleOut`: one of erplora.com's four roles. */
export interface HubRoleRow {
  key: HubRole;
  label: string;
  origin: 'basic';
  members: number;
  permissions: number;
}

/** `base.ApiKeyOut`: a key of the business (never its whole token). */
export type ApiKeyMode = 'full' | 'read' | 'write' | 'per_app';
export type ApiKind = 'read' | 'write';

export interface ApiKeyRow {
  id: string;
  name: string;
  /** The token's first characters, to tell it apart. */
  prefix: string;
  mode: ApiKeyMode;
  scopes: Record<string, ApiKind[]>;
  rate_per_minute: number;
  created_by: string;
  created_at: string;
  rotated_at: string | null;
  last_used_at: string | null;
  revoked_at: string | null;
}

/** `base.ApiAppOut`: an app this business has that publishes its API. */
export interface ApiApp {
  id: string;
  name: string;
  read: boolean;
  write: boolean;
}

/** `base.ApiKeyListOut`. */
export interface ApiKeyList {
  /** False while the business shares its database with others: no key yet. */
  available: boolean;
  keys: ApiKeyRow[];
  apps: ApiApp[];
}

export interface ApiKeyInput {
  name: string;
  rate_per_minute: number;
  mode: ApiKeyMode;
  scopes: Record<string, ApiKind[]>;
}

/** `base.ApprovalOut`: one approval of the record (Employees › Approvals). */
export interface ApprovalRow {
  id: string;
  at: string;
  /** What was approved, in words, with the figures of what was done («Discount a line by 50 %»). */
  action: string;
  /** What the action is called, without figures: what the «Action» filter offers. */
  operation_label: string;
  operation: string;
  requested_by: string;
  approved_by: string;
  way: 'pin' | 'badge';
  used: boolean;
  used_at: string | null;
}

/** `base.ApprovalExportIn`: the search and the filters Employees › Approvals keeps on screen, as its table holds them
 *  (only the active ones; `used` is `'true'` or `'false'`). */
export interface ApprovalExportQuery {
  search?: string;
  at_from?: string;
  at_to?: string;
  operation?: string;
  way?: string;
  used?: string;
}

/** `base.ApprovalExportOut`: the CSV the server wrote. */
export interface ApprovalExport {
  filename: string;
  content_type: string;
  rows: number;
  csv: string;
}

/** `base.ApproverOut`: somebody who can approve the action, by name. */
export interface Approver {
  id: string;
  name: string;
  initials: string;
}

/** `base.ApprovalIn`: their person and PIN, or their badge. */
export interface ApprovalInput {
  operation: string;
  fingerprint: string;
  person?: string;
  pin?: string;
  badge?: string;
}

/** `base.ApprovalPassOut`: the pass of one use, and who approved. */
export interface ApprovalPass {
  token: string;
  approver: string;
  expires_in: number;
}

// ── Assistant (APP-BASE-9) ──

/** `base.AssistantUsageOut`: this month's messages of the assistant, as erplora.com counts them. */
export interface AssistantUsage {
  used: number;
  /** 0: the plan has no assistant. */
  limit: number;
  resets_at: string | null;
  demo: boolean;
}

/** `base.SupportReportIn` («Report a problem» of the user menu, BASE-F108). */
export interface SupportReportInput {
  subject: string;
  description: string;
  /** The hub's screen the person was on. */
  page?: string | null;
}

/** `base.AssistantReportIn`. */
export interface AssistantReportInput {
  message_id: string;
  reason: 'incorrect' | 'harmful' | 'instructions' | 'other';
  comment?: string;
  question?: string;
  answer: string;
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'base.setup.status': { input: NoInput; output: SetupStatus };
    'base.widget.list': { input: NoInput; output: { widgets: WidgetDef[] } };
    'base.bell.counters': { input: NoInput; output: BellCounters };
    'base.notice.list': { input: NoInput; output: { notices: DeviceNoticeRow[]; sources: string[] } };
    // Apps (APP-BASE-4)
    'base.app.list': { input: NoInput; output: AppList };
    'base.app.enable': { input: AppChangeIn; output: AppChange };
    'base.app.disable': { input: AppChangeIn; output: AppChange };
    'base.app.get': { input: AppRefIn; output: AppRef };
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
    // ── Business settings (APP-BASE-6) ──
    'base.business.get': { input: NoInput; output: Business };
    // The shared image library (round 2026-10-30): 503 `base.image_library_unavailable` when it cannot be read.
    'base.catalog_image.search': { input: CatalogImageSearchIn; output: CatalogImagePage };
    'base.catalog_image.get': { input: { reference: string }; output: CatalogImage };
    // System (APP-BASE-7)
    'base.system.status': { input: NoInput; output: SystemStatus };
    'base.event.list': { input: NoInput; output: { entries: EventLogEntry[] } };
    'base.failed_event.list': { input: { limit?: number; offset?: number }; output: FailedEventPage };
    'base.failed_event.retry': { input: { id: string }; output: { id: string } };
    'base.failed_event.retry_all': { input: NoInput; output: { count: number } };
    'base.failed_event.discard': { input: { id: string; reason?: string }; output: { id: string } };
    // ── Files (APP-BASE-8) ──
    'base.file.list': { input: { folder?: string }; output: FilesListing };
    'base.file.read': {
      input: { path: string; inline?: boolean };
      output: { path: string; name: string; size: number; content_type: string; preview: FilePreview };
    };
    'base.file.upload': {
      input: { folder?: string; name: string; content_base64: string };
      output: { path: string; name: string; size: number };
    };
    'base.file.create_folder': { input: { parent?: string; name: string }; output: { path: string; name: string } };
    'base.file.rename': { input: { path: string; name: string }; output: { path: string; name: string } };
    'base.file.move': { input: { path: string; to?: string }; output: { path: string; name: string } };
    'base.file.delete': { input: { path: string }; output: { path: string; folder: boolean } };

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

    // People and permissions (APP-BASE-5)
    'base.person.list': { input: NoInput; output: { people: Person[]; seats: Seats } };
    'base.person.detail': { input: { person: string }; output: PersonDetail };
    'base.person.pin_remove': { input: { person: string }; output: PersonDetail };
    'base.person.badge_set': { input: { person: string; badge: string }; output: PersonDetail };
    'base.person.badge_remove': { input: { person: string }; output: PersonDetail };
    'base.role.list': { input: NoInput; output: { roles: HubRoleRow[] } };
    'base.api_key.list': { input: NoInput; output: ApiKeyList };
    'base.api_key.create': { input: ApiKeyInput; output: { key: ApiKeyRow; token: string } };
    'base.api_key.rotate': { input: { id: string }; output: { key: ApiKeyRow; token: string } };
    'base.api_key.revoke': { input: { id: string }; output: { key: ApiKeyRow } };
    'base.approval.list': { input: NoInput; output: { approvals: ApprovalRow[] } };
    'base.approval.approvers': { input: { operation: string }; output: { people: Approver[]; pin_length: number } };
    'base.approval.export': { input: ApprovalExportQuery; output: ApprovalExport };
    'base.approval.approve': { input: ApprovalInput; output: ApprovalPass };
    'base.api_doc.get': { input: NoInput; output: { document: Record<string, unknown>; apps: ApiApp[]; keys_available: boolean } };
    'base.api_doc.settings': { input: NoInput; output: { docs_enabled: boolean; can_change: boolean } };
    'base.api_doc.settings_update': { input: { docs_enabled: boolean }; output: { docs_enabled: boolean; can_change: boolean } };
    // Assistant (APP-BASE-9); its turn is a stream the shared panel reads itself (@erplora/ui, Assistant/stream.ts).
    'base.assistant.usage': { input: NoInput; output: AssistantUsage };
    'base.assistant.report': { input: AssistantReportInput; output: { sent: boolean; duplicate: boolean } };
    'base.assistant.transcribe': {
      input: { audio: string; mime_type: string; language?: string };
      output: { text: string; language: string };
    };
    // «Report a problem» of the user menu (BASE-F108): erplora.com answers the address support writes back to.
    'base.support.report': { input: SupportReportInput; output: { reply_to: string } };
  }
}
