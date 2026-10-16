// Types of the flow app's operations for the SDK (`useLive`, `useCommand`, `client.api.call`), from
// apps/flow/schemas.py. Written by hand, as `frontend/sdk-types.d.ts` is for the PoC, until V3
// generates them from `/api/openapi.json`. Keep it in step with schemas.py and with
// `frontend/generated/operations.json`. One input per operation (ninja's parity): no path parameters,
// an automation's `id` (or its name, `flow`) travels in the input. Dates are ISO strings.
import type { Page } from '../../../frontend/sdk-types';

export type TriggerKind = 'event' | 'schedule' | 'at' | 'manual';
export type Operator = 'eq' | 'neq' | 'in' | 'exists' | 'contains' | 'gt' | 'gte' | 'lt' | 'lte';
/** `{path: {operator: value}}`, every comparison at once. */
export type Condition = Record<string, Partial<Record<Operator, unknown>>>;

export interface EventTrigger {
  kind: 'event';
  event: string;
  filter?: Condition;
}
export interface ScheduleTrigger {
  kind: 'schedule';
  every: 'day' | 'week' | 'month';
  time: string;
  /** 0 = Monday … 6 = Sunday. */
  weekday?: number | null;
  day?: number | null;
}
export interface AtTrigger {
  kind: 'at';
  at: string;
}
export interface ManualTrigger {
  kind: 'manual';
}
export type Trigger = EventTrigger | ScheduleTrigger | AtTrigger | ManualTrigger;

export interface CommandStep {
  id: string;
  kind: 'command';
  operation: string;
  params: Record<string, unknown>;
}
export interface QueryStep {
  id: string;
  kind: 'query';
  operation: string;
  params: Record<string, unknown>;
  result: 'first' | 'count';
}
export interface ConditionStep {
  id: string;
  kind: 'condition';
  when: Condition;
}
export interface DelayStep {
  id: string;
  kind: 'delay';
  seconds: number;
}
export type Step = CommandStep | QueryStep | ConditionStep | DelayStep;
export type StepKind = Step['kind'];

export type RunStatus = 'running' | 'waiting' | 'succeeded' | 'stopped' | 'failed' | 'cancelled';

export interface FlowRefIn {
  id?: string;
  flow?: string;
}

export interface FlowListIn {
  search?: string;
  enabled?: boolean;
  trigger_kind?: TriggerKind;
  sort?: '-updated_at' | 'updated_at' | 'name' | '-name';
  limit?: number;
  offset?: number;
}

export interface LastRunOut {
  id: string;
  status: RunStatus;
  started_at: string;
}

export interface FlowOut {
  id: string;
  name: string;
  enabled: boolean;
  /** As the document writes it; a schedule carries `weekday` and `day` (null when they do not apply). */
  trigger: Trigger;
  steps: Step[];
  grants: string[];
  required_grants: string[];
  missing_grants: string[];
  version: number;
  next_fire_at: string | null;
  created_at: string;
  updated_at: string;
  created_by: string;
  updated_by: string;
  last_run: LastRunOut | null;
}

export interface CreateIn {
  name?: string;
  trigger?: Trigger;
  steps?: Step[];
  draft_id?: string | null;
}

export interface UpdateIn extends FlowRefIn {
  name?: string;
  trigger?: Trigger;
  steps?: Step[];
}

export interface EnabledIn extends FlowRefIn {
  enabled: boolean;
}

export interface GrantIn extends FlowRefIn {
  operations: string[];
}

export interface RunIn extends FlowRefIn {
  input?: Record<string, unknown>;
}

/** One entry of a run's log, as the engine writes it. */
export interface LogEntry {
  step: string;
  kind: StepKind;
  operation?: string;
  outcome: 'done' | 'found' | 'not_found' | 'passed' | 'stopped' | 'waiting' | 'waited' | 'failed';
  at: string;
  count?: number;
  seconds?: number;
  until?: string;
  failed?: { path: string; op: Operator; value: unknown }[];
  error?: { code: string; message: string; fields?: Record<string, string>; technical?: string };
}

export interface RunOut {
  id: string;
  flow_id: string;
  flow_version: number;
  status: RunStatus;
  trigger_kind: TriggerKind;
  event_name: string;
  input: Record<string, unknown>;
  step_index: number;
  steps_total: number;
  log: LogEntry[];
  error_code: string;
  error_message: string;
  resume_at: string | null;
  started_at: string;
  finished_at: string | null;
  started_by: string;
}

export interface RunListIn {
  flow_id: string;
  status?: RunStatus;
  limit?: number;
  offset?: number;
}

export interface RunPageOut extends Page<RunOut> {
  failed: number;
}

export interface DraftOut {
  id: string;
  name: string;
  definition: { trigger?: Trigger; steps?: Step[] };
  notes: string[];
  status: 'pending' | 'used' | 'dismissed';
  flow_id: string | null;
  created_at: string;
  created_by: string;
}

export interface DraftListIn {
  limit?: number;
  offset?: number;
}

export interface DraftRefIn {
  id: string;
}

export interface DraftProposeIn {
  name: string;
  definition: { trigger?: Trigger; steps: Step[] };
  notes?: string[];
}

export interface CatalogEventOut {
  name: string;
  app: string;
  app_name: string;
}

export interface FieldOut {
  name: string;
  type: string;
  required: boolean;
  description: string;
  choices: string[];
}

export interface CatalogActionOut {
  name: string;
  kind: 'command' | 'query';
  app: string;
  app_name: string;
  description: string;
  fields: FieldOut[];
  outputs: string[];
}

export interface CatalogOut {
  events: CatalogEventOut[];
  actions: CatalogActionOut[];
}

export interface SampleIn {
  event: string;
}

export interface SampleOut {
  found: boolean;
  event: string;
  at: string | null;
  payload: Record<string, unknown>;
}

export interface StatusIn {
  event: string;
  operation: string;
}

export interface StatusOut {
  total: number;
  enabled: number;
  unfinished: number;
}

export interface TestIn {
  id?: string;
  /** `{trigger, steps}` as JSON text. */
  document: string;
}

export interface ClauseOut {
  path: string;
  op: Operator;
  value: unknown;
}

export type TestOutcome =
  | 'high_risk'
  | 'would_run'
  | 'stops_here'
  | 'cannot_tell'
  | 'waits'
  | 'refused'
  | 'not_allowed'
  | 'unavailable'
  | 'not_reached';

export interface TestStepOut {
  id: string;
  kind: StepKind;
  outcome: TestOutcome;
  operation: string;
  params: Record<string, unknown>;
  empty: string[];
  unknown: string[];
  errors: Record<string, string>;
  failed: ClauseOut[];
  seconds: number | null;
}

export interface TestOut {
  sample: SampleOut;
  starts: boolean;
  trigger_failed: ClauseOut[];
  steps: TestStepOut[];
}

export interface DeletedOut {
  id: string;
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'flow.flow.list': { input: FlowListIn; output: Page<FlowOut> };
    'flow.flow.detail': { input: FlowRefIn; output: FlowOut };
    'flow.flow.status': { input: StatusIn; output: StatusOut };
    'flow.flow.test': { input: TestIn; output: TestOut };
    'flow.flow.create': { input: CreateIn; output: FlowOut };
    'flow.flow.update': { input: UpdateIn; output: FlowOut };
    'flow.flow.set_enabled': { input: EnabledIn; output: FlowOut };
    'flow.flow.duplicate': { input: FlowRefIn; output: FlowOut };
    'flow.flow.delete': { input: FlowRefIn; output: DeletedOut };
    'flow.flow.grant': { input: GrantIn; output: FlowOut };
    'flow.flow.run': { input: RunIn; output: RunOut };
    'flow.run.list': { input: RunListIn; output: RunPageOut };
    'flow.draft.list': { input: DraftListIn; output: Page<DraftOut> };
    'flow.draft.propose': { input: DraftProposeIn; output: DraftOut };
    'flow.draft.dismiss': { input: DraftRefIn; output: DraftOut };
    'flow.catalog.read': { input: Record<string, never>; output: CatalogOut };
    'flow.event.sample': { input: SampleIn; output: SampleOut };
  }
}
