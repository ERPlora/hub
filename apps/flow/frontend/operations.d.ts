// Types of the flow app's operations for the SDK (`useLive`, `useCommand`, `client.api.call`), from
// apps/flow/schemas.py. Written by hand, as `frontend/sdk-types.d.ts` is for the PoC, until V3
// generates them from `/api/openapi.json`. Keep it in step with schemas.py and with
// `frontend/generated/operations.json`. One input per operation (ninja's parity): no path parameters,
// an automation's `id` (or its name, `flow`) travels in the input. Dates are ISO strings.
import type { Page } from '../../../frontend/sdk-types';
import type { AssistantField } from '../../../base/frontend/lib/assistant-card';

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

/** «Only if…» and «If it fails, carry on» (FLOW-F25): absent, the step always runs and a failure stops the run. */
export interface StepOptions {
  run_if?: Condition;
  on_error?: 'stop' | 'continue';
}
export interface CommandStep extends StepOptions {
  id: string;
  kind: 'command';
  operation: string;
  params: Record<string, unknown>;
}
export interface QueryStep extends StepOptions {
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
  run_if?: Condition;
}
/** «Call another system» (FLOW-F27): its texts may read `{{secret.NAME}}` and `{{run.idempotency_key}}`. */
export interface HttpStep extends StepOptions {
  id: string;
  kind: 'http';
  method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  url: string;
  headers: Record<string, string>;
  body: string;
  timeout: number;
}
/** «Ask someone first» (FLOW-F28): the run waits for a person's yes or no. */
export interface AskStep {
  id: string;
  kind: 'ask';
  /** The question; `{{…}}` data are filled in when it is asked. */
  title: string;
  details: string;
  /** Who answers: '' whoever runs the business, `manager` or `employee`. */
  role: QuestionRole;
  /** How long to wait: 1 to 720 hours. */
  hours: number;
  on_no: 'stop' | 'continue';
  on_timeout: 'no' | 'stop' | 'continue';
  run_if?: Condition;
}
export type QuestionRole = '' | 'manager' | 'employee';
/** «Ask the assistant» (FLOW-F37): it does the task with nobody in front, with what the step names and was granted. */
export interface AssistantStep extends StepOptions {
  id: string;
  kind: 'assistant';
  /** What it is asked; `{{…}}` data are filled in when it runs. */
  prompt: string;
  /** The reads and actions it may use, by name: each one a permission of the automation. */
  tools: string[];
  /** Data a tool always gets, `{tool: {input: value}}`, filled in when it runs: the assistant never sees them nor
   *  changes them. Absent: none. */
  pinned?: Record<string, Record<string, unknown>>;
  /** `ask`: a change waits for a yes in «Waiting for your answer»; `auto`: it makes it on its own. */
  mode: 'ask' | 'auto';
  /** Most turns: 1 to 10. */
  max_rounds: number;
}
export type Step = CommandStep | QueryStep | ConditionStep | DelayStep | HttpStep | AskStep | AssistantStep;
export type StepKind = Step['kind'];

export type RunStatus = 'running' | 'waiting' | 'calling' | 'asking' | 'succeeded' | 'stopped' | 'failed' | 'cancelled';

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
  outcome:
    | 'done'
    | 'found'
    | 'not_found'
    | 'passed'
    | 'stopped'
    | 'waiting'
    | 'waited'
    | 'failed'
    | 'resumed'
    | 'skipped'
    | 'calling'
    | 'called'
    | 'asking'
    | 'answered'
    | 'expired'
    | 'thinking'
    | 'assistant_used'
    | 'assistant_answered'
    | 'assistant_proposed'
    | 'assistant_pinned_empty';
  /** Whether a read or an action the assistant used went well (`assistant_used`). */
  ok?: boolean;
  /** The data the step fixes that were empty, so the tool was not used (`assistant_pinned_empty`). */
  fields?: string[];
  /** What the assistant answered (`assistant_answered`). */
  text?: string;
  /** Who a question was asked of (`asking`). */
  role?: QuestionRole;
  /** The answer (`answered`) and its note. */
  approved?: boolean;
  note?: string;
  /** The host a call went to (`calling`, `called`). */
  host?: string;
  /** What a call answered (`called`). */
  status?: number;
  /** A failure of a step with «If it fails, carry on»: the run went on. */
  continued?: boolean;
  at: string;
  /** Who resumed it (`resumed`) or answered it (`answered`). */
  by?: string;
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
  /** It stopped by an error at a step and can still be resumed there (`flow.run.retry`). */
  resumable: boolean;
}

export interface RunRefIn {
  id: string;
}

/** A run read by its id also says the words it is named by, in the caller's language: its automation and when it
 *  started, as the History says it (the assistant's card says them). */
export interface RunDetailOut extends RunOut {
  label: string;
}

/** A question an automation asked and waits on (FLOW-F29), as «Waiting for your answer» shows it. */
export interface QuestionOut {
  id: string;
  flow_id: string;
  flow_name: string;
  run_id: string;
  title: string;
  details: string;
  role: QuestionRole;
  on_no: 'stop' | 'continue';
  on_timeout: 'no' | 'stop' | 'continue';
  expires_at: string;
  created_at: string;
  /** What the change the assistant wants (FLOW-F38) does, as the History names it, in the language of whoever asks
   *  («Cancel a reservation»); '' for a question an «Ask someone first» step asks. */
  action: string;
  /** The data of the change the assistant wants (FLOW-F38), as its card in the chat says them, read for whoever
   *  asks (BASE-F97 step 2); none for a question an «Ask someone first» step asks. */
  fields: AssistantField[];
}
export interface QuestionPageOut {
  rows: QuestionOut[];
}
export interface QuestionRefIn {
  id: string;
}
export interface AnswerIn extends QuestionRefIn {
  approve: boolean;
  note?: string;
}
export interface AnsweredOut {
  id: string;
  run_id: string;
  status: RunStatus;
}

/** A secret (FLOW-F26): its name, never its value. */
export interface SecretOut {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
  updated_by: string;
}
export interface SecretPageOut {
  rows: SecretOut[];
  /** Whether this server can keep secrets (it has its key). */
  available: boolean;
}
export interface SecretSetIn {
  name: string;
  value: string;
}
export interface SecretRefIn {
  name: string;
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
  /** Whether «Ask the assistant» may use it (absent: it may not). */
  assistant?: boolean;
  /** Whether it needs a person's yes first: only «Ask the assistant» with «Ask me first» may use it (absent: no). */
  ask_first?: boolean;
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
  | 'skipped'
  | 'would_call'
  | 'would_ask'
  | 'would_ask_assistant'
  | 'high_risk'
  | 'would_run'
  | 'stops_here'
  | 'cannot_tell'
  | 'waits'
  | 'refused'
  | 'not_allowed'
  | 'unavailable'
  | 'not_reached';

/** A datum an «Ask the assistant» step fixes, as «Try it» would fill it in. */
export interface PinnedOut {
  tool: string;
  field: string;
  /** What it would be, as the card of the change says it (a record by its name); `null` when empty, unknown or a
   *  record the person trying it may not read (the card leaves it out). */
  said: AssistantField | null;
  /** `empty`: its tool would not be used; `unknown`: it reads a step that does not run here. */
  state: 'filled' | 'empty' | 'unknown';
}

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
  /** The data an «Ask the assistant» step fixes, tool by tool; absent or empty for any other step. */
  pinned?: PinnedOut[];
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

/** A ready-made automation an app brings (FLOW-F33 to F36): `<app>/<id>`. */
export interface RecipeRefIn {
  recipe: string;
}
export interface RecipeGrantOut {
  operation: string;
  /** Why it asks for it, in the words of the app that brings it. */
  reason: string;
}
export interface RecipeInstalledOut {
  flow_id: string;
  name: string;
  enabled: boolean;
  /** Its app brings a newer version than the one it was built or restored from. */
  outdated: boolean;
  missing_grants: string[];
  /** The «Only when…» clauses its app added since; empty: nothing to repair. */
  repair: Condition;
}
export interface RecipeOut {
  ref: string;
  app: string;
  app_name: string;
  icon: string;
  id: string;
  name: string;
  summary: string;
  description: string;
  trigger: Trigger;
  steps: Step[];
  grants: RecipeGrantOut[];
  installed: RecipeInstalledOut | null;
}
export interface RecipeSetAsideOut {
  ref: string;
  app: string;
  app_name: string;
  name: string;
  code: 'flow.recipe_needs_apps' | 'flow.recipe_invalid';
  message: string;
  apps: string[];
}
export interface RecipeListOut {
  recipes: RecipeOut[];
  set_aside: RecipeSetAsideOut[];
}
export interface RecipeEnabledOut {
  created: boolean;
  flow: FlowOut;
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
    'flow.run.get': { input: RunRefIn; output: RunDetailOut };
    'flow.run.retry': { input: RunRefIn; output: RunOut };
    'flow.secret.list': { input: Record<string, never>; output: SecretPageOut };
    'flow.secret.set': { input: SecretSetIn; output: SecretOut };
    'flow.secret.delete': { input: SecretRefIn; output: DeletedOut };
    'flow.question.list': { input: Record<string, never>; output: QuestionPageOut };
    'flow.question.get': { input: QuestionRefIn; output: QuestionOut };
    'flow.question.answer': { input: AnswerIn; output: AnsweredOut };
    'flow.draft.list': { input: DraftListIn; output: Page<DraftOut> };
    'flow.draft.get': { input: DraftRefIn; output: DraftOut };
    'flow.draft.propose': { input: DraftProposeIn; output: DraftOut };
    'flow.draft.dismiss': { input: DraftRefIn; output: DraftOut };
    'flow.catalog.read': { input: Record<string, never>; output: CatalogOut };
    'flow.event.sample': { input: SampleIn; output: SampleOut };
    'flow.recipe.list': { input: Record<string, never>; output: RecipeListOut };
    'flow.recipe.enable': { input: RecipeRefIn; output: RecipeEnabledOut };
    'flow.recipe.disable': { input: RecipeRefIn; output: FlowOut };
    'flow.recipe.restore': { input: RecipeRefIn; output: FlowOut };
    'flow.recipe.repair': { input: RecipeRefIn; output: FlowOut };
  }
}
