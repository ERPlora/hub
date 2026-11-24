// Types of base/schemas/usage.py for the SDK (`useLive`, `useCommand`, `client.api.call`), written by
// hand: keep them in step with it and with `frontend/generated/operations.json`.
// `AssistantUsage` is base/schemas/assistant.py's: it is one more figure of System › «Usage and plan».

type NoInput = Record<string, never>;

/** `base.LimitOut`: what is in use (null: the Hub does not count it) against the plan's limit (null: none). */
export interface PlanLimit {
  used: number | null;
  limit: number | null;
}

/** `base.DatabaseUsageOut`: the size of the business's own database, as the last night measured it (BASE-F40). */
export interface DatabaseUsage {
  /** Its size in bytes; null before the first night measured it. */
  bytes: number | null;
  /** The day (UTC, `YYYY-MM-DD`) it was measured; null before the first night. */
  day: string | null;
}

/** `base.FilesUsageOut`: what the business's files and those of its apps take up, as the last night measured it. */
export interface FilesUsage {
  /** What they take up, in bytes; null before the first night. */
  bytes: number | null;
  /** The day (UTC, `YYYY-MM-DD`) it was measured; null before the first night. */
  day: string | null;
  /** The space the plan includes, in bytes; null: no limit, or the plan is not known. */
  limit: number | null;
  /** How much of that space they take up; null without a limit or a figure. */
  percent: number | null;
  /** Null without a limit or a figure. */
  status: 'within' | 'near' | 'full' | null;
}

/** `base.ConnectionsUsageOut`: the business's capacity, what it does at once in its database against what it really has. */
export interface ConnectionsUsage {
  /** The most connections at once today; null: not measured today yet. */
  peak_today: number | null;
  /** What its plan includes or, if less, what the service gives; null: the plan is not known. */
  limit: number | null;
  /** The times in the last 7 days somebody got an error because there was no room; null: never counted yet. */
  busy_last_7_days: number | null;
  /** Since when they are counted (`YYYY-MM-DD`), when that is less than the 7 days. */
  busy_since: string | null;
  /** Whether a bigger plan would give it more at once. */
  bigger_plan_gives_more: boolean;
}

/** `base.RequestsUsageOut`: the requests the business has served this calendar month (UTC). */
export interface RequestsUsage {
  /** How many; null: never counted yet. */
  this_month: number | null;
  /** Since when they are counted (`YYYY-MM-DD`), when that is after day 1. */
  since: string | null;
}

/** `base.ActivityUsageOut`: the people with activity in the business. */
export interface ActivityUsage {
  /** With activity in the last 5 minutes; null in a demo. */
  active_now: number | null;
  /** In the 30 days the last night measured ends; null before the first night. */
  last_30_days: number | null;
  /** The day (UTC, `YYYY-MM-DD`) that night measured; null before the first night. */
  day: string | null;
}

/** `base.PlanMeterOut`: what an app on says its plan includes this month (`base.home.plan_meters.plan_meters`). */
export interface PlanMeter {
  /** The app it is of. */
  key: string;
  /** What it is called, in the person's language. */
  label: string;
  /** How much of it is spent; null: not measured yet, or it could not be read. */
  used: number | null;
  /** How much the plan includes; 0: the plan includes none; null: as above. */
  limit: number | null;
  /** False when its app could not be read now. */
  available: boolean;
}

/** `base.PlanUsageOut`: System › «Usage and plan». A figure not measured yet is null, never a zero. */
export interface PlanUsage {
  /** Whether the Hub has the business's plan from erplora.com yet. */
  known: boolean;
  /** A demo: nothing of it is measured. */
  demo: boolean;
  /** The plan the business is on (`free`, `starter`…); null: not known. */
  plan_slug: string | null;
  people: PlanLimit;
  devices: PlanLimit;
  apps: PlanLimit;
  database: DatabaseUsage;
  files: FilesUsage;
  connections: ConnectionsUsage;
  requests: RequestsUsage;
  activity: ActivityUsage;
  meters: PlanMeter[];
}

/** `base.AssistantUsageOut`: this month's messages of the assistant, as erplora.com counts them. */
export interface AssistantUsage {
  used: number;
  /** 0: the plan has no assistant. */
  limit: number;
  resets_at: string | null;
  demo: boolean;
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'base.plan.usage': { input: NoInput; output: PlanUsage };
    'base.assistant.usage': { input: NoInput; output: AssistantUsage };
  }
}
