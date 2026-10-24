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

declare module '@erplora/ui/sdk' {
  interface Operations {
    'base.setup.status': { input: NoInput; output: SetupStatus };
    'base.widget.list': { input: NoInput; output: { widgets: WidgetDef[] } };
    'base.bell.counters': { input: NoInput; output: { counters: BellCounter[] } };
    'base.notice.list': { input: NoInput; output: { notices: DeviceNoticeRow[]; sources: string[] } };
    // Apps (APP-BASE-4)
    'base.app.list': { input: NoInput; output: AppList };
    'base.plan.usage': { input: NoInput; output: PlanUsage };
    // System (APP-BASE-7)
    'base.system.status': { input: NoInput; output: SystemStatus };
    'base.event.list': { input: NoInput; output: { entries: EventLogEntry[] } };
    'base.failed_event.list': { input: { limit?: number; offset?: number }; output: FailedEventPage };
    'base.failed_event.retry': { input: { id: string }; output: { id: string } };
    'base.failed_event.retry_all': { input: NoInput; output: { count: number } };
    'base.failed_event.discard': { input: { id: string; reason?: string }; output: { id: string } };
  }
}
