// Types of base/schemas/home.py for the SDK (`useLive`, `useCommand`, `client.api.call`), written by
// hand: keep them in step with it and with `frontend/generated/operations.json`.
// The Home's take no input: each one answers for the person and the hub of the request.

type NoInput = Record<string, never>;

/** `base.SetupItemOut`: one step of «Finish setting up your business». */
export interface SetupItem {
  /** «<app>.<step>»: «base.apps», «base.mandatory.<app>» (turn on an app mandatory in the business's country),
   *  «base.team» or a module's own step. */
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

/** `base.SystemCardOut`: a card an app on puts in System › «Usage and plan» for this person (hub#683). */
export interface SystemCardDef {
  /** «<app>.<card>». */
  key: string;
  app: string;
  /** The Vue component of the app's frontend/components/ that paints it, without «.vue». */
  component: string;
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

/** What an app says of itself in the Home's health row; `unknown` is base's, when it could not tell. */
export type HomeHealthState = 'ok' | 'no_signal' | 'not_configured' | 'unknown';

/** `base.HealthItemOut`: one app of the Home's health row, its words already in the person's language. */
export interface HomeHealthItem {
  key: string;
  app: string;
  state: HomeHealthState;
  title: string;
  /** What fixes it, with `route`: only for `no_signal` and `not_configured`. */
  action: string | null;
  route: string | null;
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'base.setup.status': { input: NoInput; output: SetupStatus };
    'base.widget.list': { input: NoInput; output: { widgets: WidgetDef[] } };
    'base.notice.list': { input: NoInput; output: { notices: DeviceNoticeRow[]; sources: string[] } };
    'base.system.cards': { input: NoInput; output: { cards: SystemCardDef[] } };
    'base.health.list': { input: NoInput; output: { items: HomeHealthItem[] } };
  }
}
