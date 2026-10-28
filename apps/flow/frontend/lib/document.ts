// The editing model of an automation (WORKBOOK FLOW-F09 to F12), pure: no DOM, no network. The
// authority over what a valid document is stays on the server (apps/flow/schemas.py and the catalog
// of the active apps), which refuses a save by field; what lives here is how the editor builds it.
//
// The mapping rules mirror apps/flow/document.py: a value is a literal, a PATH (`input.total`,
// `steps.s1.id`, which keeps its type) or text with `{{path}}` inside (always text). They are mirrored
// because the editor applies them while the owner types.
import type { CatalogOut, Condition, FlowOut, Operator, Step, StepKind, Trigger } from '../operations';

/** What the editor holds: the automation's name, its switch, its trigger and its steps. */
export interface FlowDocument {
  name: string;
  enabled: boolean;
  trigger: Trigger;
  steps: Step[];
}

/** One piece of a composed value: typed text, or a picked field. */
export type ValuePart = { kind: 'text'; text: string } | { kind: 'field'; path: string };

/** One comparison of a condition, as a row of the editor. */
export interface ConditionRow {
  path: string;
  op: Operator;
  value: unknown;
}

/** A datum a step can insert: where it comes from (`input` or a step id) and a real example. */
export interface DataChoice {
  path: string;
  group: string;
  example: unknown;
}

export type DelayUnit = 'minutes' | 'hours' | 'days';

const PATH_RE = /^(input|steps)(\.[A-Za-z_][A-Za-z0-9_]*)+$/;
const TEMPLATE_RE = /\{\{\s*([^{}]*?)\s*\}\}/g;
const UNIT_SECONDS: Record<DelayUnit, number> = { days: 86400, hours: 3600, minutes: 60 };

export const OPERATORS: readonly Operator[] = ['eq', 'neq', 'in', 'exists', 'contains', 'gt', 'gte', 'lt', 'lte'];

/** A brand new automation: by hand (it says so), paused, without steps. */
export function emptyDocument(): FlowDocument {
  return { name: '', enabled: false, trigger: { kind: 'manual' }, steps: [] };
}

/** The trigger without the keys its kind does not use (a schedule's null weekday or day). */
export function cleanTrigger(trigger: Trigger): Trigger {
  if (trigger.kind === 'event') return { kind: 'event', event: trigger.event, ...(trigger.filter && Object.keys(trigger.filter).length ? { filter: trigger.filter } : {}) };
  if (trigger.kind === 'schedule') {
    const out: Trigger = { kind: 'schedule', every: trigger.every, time: trigger.time };
    if (trigger.every === 'week') out.weekday = trigger.weekday ?? 0;
    if (trigger.every === 'month') out.day = trigger.day ?? 1;
    return out;
  }
  if (trigger.kind === 'at') return { kind: 'at', at: trigger.at };
  return { kind: 'manual' };
}

/** The document of a saved automation. */
export function fromFlow(flow: FlowOut): FlowDocument {
  return { name: flow.name, enabled: flow.enabled, trigger: cleanTrigger(flow.trigger), steps: flow.steps.map((step) => ({ ...step })) };
}

/** What `flow.flow.create`/`flow.flow.update` take of the document: never the switch, which is
 *  `flow.flow.set_enabled`'s alone (the assistant confirms it). */
export function toPayload(doc: FlowDocument): { name: string; trigger: Trigger; steps: Step[] } {
  return { name: doc.name.trim(), trigger: cleanTrigger(doc.trigger), steps: doc.steps };
}

/** The first `sN` no step uses. */
export function newStepId(steps: readonly Step[]): string {
  const taken = new Set(steps.map((step) => step.id));
  for (let n = 1; ; n += 1) if (!taken.has(`s${n}`)) return `s${n}`;
}

function blankStep(id: string, kind: StepKind): Step {
  if (kind === 'query') return { id, kind, operation: '', params: {}, result: 'first' };
  if (kind === 'condition') return { id, kind, when: {} };
  // An hour: long enough to read as «later», short enough that a first try needs no patience.
  if (kind === 'delay') return { id, kind, seconds: 3600 };
  if (kind === 'http') return { id, kind, method: 'POST', url: '', headers: {}, body: '', timeout: 10 };
  // Whoever runs the business, three days, and a no stops it: the old module's defaults.
  if (kind === 'ask') return { id, kind, title: '', details: '', role: '', hours: 72, on_no: 'stop', on_timeout: 'no' };
  // A change waits for a yes, and six turns: the old hub's defaults.
  if (kind === 'assistant') return { id, kind, prompt: '', tools: [], mode: 'ask', max_rounds: 6 };
  return { id, kind: 'command', operation: '', params: {} };
}

export function addStep(doc: FlowDocument, kind: StepKind): FlowDocument {
  return { ...doc, steps: [...doc.steps, blankStep(newStepId(doc.steps), kind)] };
}

/** The WhatsApp inbox's narrow send (FLOW-F31): what «Send a message» runs, a «Do something» of its own form. */
export const NOTIFY_OPERATION = 'whatsapp_inbox.message.notify';

/** «Send a message»: a «Do something» step of the narrow send, to whom and what still to fill. */
export function addMessageStep(doc: FlowDocument): FlowDocument {
  const step: Step = { id: newStepId(doc.steps), kind: 'command', operation: NOTIFY_OPERATION, params: { phone: '', text: '' } };
  return { ...doc, steps: [...doc.steps, step] };
}

export function removeStep(doc: FlowDocument, index: number): FlowDocument {
  return { ...doc, steps: doc.steps.filter((_, i) => i !== index) };
}

export function moveStep(doc: FlowDocument, from: number, to: number): FlowDocument {
  const steps = [...doc.steps];
  const [moved] = steps.splice(from, 1);
  if (!moved) return doc;
  steps.splice(to, 0, moved);
  return { ...doc, steps };
}

export function patchStep(doc: FlowDocument, index: number, patch: Partial<Step>): FlowDocument {
  return { ...doc, steps: doc.steps.map((step, i) => (i === index ? ({ ...step, ...patch } as Step) : step)) };
}

// ── Values ─────────────────────────────────────────────────────────────────────────────────────

export function isPath(text: unknown): boolean {
  return typeof text === 'string' && PATH_RE.test(text);
}

/** Text the owner typed: a number or a yes/no is meant as one (a leading zero keeps it text). */
function scalar(text: string): string | number | boolean {
  if (text === 'true') return true;
  if (text === 'false') return false;
  if (text !== '' && String(Number(text)) === text) return Number(text);
  return text;
}

export function partsToValue(parts: readonly ValuePart[]): unknown {
  if (parts.length === 0) return '';
  if (parts.length === 1) {
    const only = parts[0];
    return only.kind === 'field' ? only.path : scalar(only.text);
  }
  return parts.map((part) => (part.kind === 'field' ? `{{${part.path}}}` : part.text)).join('');
}

export function valueToParts(value: unknown): ValuePart[] {
  if (value === undefined || value === null) return [];
  if (typeof value !== 'string') return [{ kind: 'text', text: typeof value === 'object' ? JSON.stringify(value) : String(value) }];
  if (isPath(value)) return [{ kind: 'field', path: value }];
  const parts: ValuePart[] = [];
  let last = 0;
  for (const match of value.matchAll(TEMPLATE_RE)) {
    const start = match.index ?? 0;
    if (start > last) parts.push({ kind: 'text', text: value.slice(last, start) });
    parts.push({ kind: 'field', path: match[1] });
    last = start + match[0].length;
  }
  if (last < value.length) parts.push({ kind: 'text', text: value.slice(last) });
  return parts;
}

// ── Permissions ────────────────────────────────────────────────────────────────────────────────

/** The origin of a call whose host is written by hand (`https://host[:port]`, lower case, no default
 *  port); `null` otherwise. Mirrors apps/flow/document.py `literal_origin`. */
export function callOrigin(url: string): string | null {
  const filled = url.trim().replace(TEMPLATE_RE, 'x');
  let parsed: URL;
  try {
    parsed = new URL(filled);
  } catch {
    return null;
  }
  if (parsed.protocol !== 'https:' || !parsed.hostname || parsed.username || parsed.password || filled.split('/')[2]?.includes('@')) return null;
  const head = url.trim().split('{{')[0];
  if (url.includes('{{') && !/^https:\/\/[^/?#{}]+[/?#]/i.test(head)) return null;
  return `https://${parsed.host}`;
}

/** The permission a call asks for (`http:https://host`), or `null` for an address not written by hand. */
export function httpGrant(url: string): string | null {
  const origin = callOrigin(url);
  return origin ? `http:${origin}` : null;
}

/** The actions, reads and calls' origins the steps need, once each and in order (a half-filled step asks
 *  nothing). */
export function requiredGrants(steps: readonly Step[]): string[] {
  const names: string[] = [];
  for (const step of steps) {
    if ((step.kind === 'command' || step.kind === 'query') && step.operation.trim() && !names.includes(step.operation)) {
      names.push(step.operation);
    } else if (step.kind === 'http') {
      const grant = httpGrant(step.url);
      if (grant && !names.includes(grant)) names.push(grant);
    } else if (step.kind === 'assistant') {
      for (const tool of step.tools) if (tool.trim() && !names.includes(tool)) names.push(tool);
    }
  }
  return names;
}

/** What a call can insert besides the automation's data: the secrets (by name) and its own key. */
export function callChoices(secrets: readonly string[]): DataChoice[] {
  return [
    ...secrets.map((name) => ({ path: `secret.${name}`, group: 'secret', example: undefined })),
    { path: 'run.idempotency_key', group: 'run', example: undefined },
  ];
}

/** Every value of a call is text: a datum alone (what `partsToValue` keeps bare) becomes `{{…}}`. */
export function asCallText(value: unknown): string {
  if (typeof value !== 'string') return value === undefined || value === null ? '' : String(value);
  return /^(input|steps|secret|run)(\.[A-Za-z_][A-Za-z0-9_]*)+$/.test(value) ? `{{${value}}}` : value;
}

export function missingGrants(steps: readonly Step[], grants: readonly string[]): string[] {
  return requiredGrants(steps).filter((name) => !grants.includes(name));
}

// ── Waits ──────────────────────────────────────────────────────────────────────────────────────

export function delayParts(seconds: number): { amount: number; unit: DelayUnit } {
  for (const unit of ['days', 'hours'] as const) {
    if (seconds % UNIT_SECONDS[unit] === 0) return { amount: seconds / UNIT_SECONDS[unit], unit };
  }
  return { amount: Math.max(1, Math.round(seconds / 60)), unit: 'minutes' };
}

export function secondsOf(amount: number, unit: DelayUnit): number {
  return Math.round(amount * UNIT_SECONDS[unit]);
}

// ── Conditions ─────────────────────────────────────────────────────────────────────────────────

export function conditionRows(condition: Condition | undefined): ConditionRow[] {
  return Object.entries(condition ?? {}).flatMap(([path, comparisons]) =>
    Object.entries(comparisons ?? {}).map(([op, value]) => ({ path, op: op as Operator, value })),
  );
}

export function rowsToCondition(rows: readonly ConditionRow[]): Condition {
  const condition: Condition = {};
  for (const row of rows) {
    if (!row.path) continue;
    condition[row.path] = { ...(condition[row.path] ?? {}), [row.op]: row.value };
  }
  return condition;
}

// ── The server's 422, next to its step ───────────────────────────────────────────────────────────

/** `steps.<n>.<kind>.<field>` (the schema's) and `steps.<n>.<field>` (the catalog's) both become the
 *  latter; a refusal of the trigger's kind becomes `trigger.<field>`, or `trigger` for the whole. */
export function fieldErrors(fields: Readonly<Record<string, string>> | undefined): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [key, message] of Object.entries(fields ?? {})) {
    let normal = key.replace(/^steps\.(\d+)\.(command|query|condition|delay|http|ask|assistant)\./, 'steps.$1.');
    normal = normal === 'trigger.schedule' ? 'trigger' : normal.replace(/^trigger\.(event|schedule|at|manual)\./, 'trigger.');
    out[normal] = message;
  }
  return out;
}

// ── The data a step can insert ─────────────────────────────────────────────────────────────────

function flatten(value: unknown, prefix: string, out: DataChoice[]): void {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) return;
  for (const [key, inner] of Object.entries(value as Record<string, unknown>)) {
    if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(key) || Array.isArray(inner)) continue;
    const path = `${prefix}.${key}`;
    if (inner !== null && typeof inner === 'object') flatten(inner, path, out);
    else out.push({ path, group: 'input', example: inner });
  }
}

/** What step `index` can insert: the fields the event brought (from a real one) and what the earlier
 *  actions and reads leave (from the catalog). A list is never offered: a path cannot index it. */
export function dataChoices(steps: readonly Step[], index: number, sample: Record<string, unknown> | null | undefined, catalog: CatalogOut | null | undefined): DataChoice[] {
  const out: DataChoice[] = [];
  flatten(sample ?? {}, 'input', out);
  for (const step of steps.slice(0, index)) {
    if (step.kind === 'condition' || step.kind === 'delay') continue;
    const outputs =
      step.kind === 'http'
        ? ['status', 'body']
        : step.kind === 'ask'
          ? ['approved', 'expired', 'note', 'answered_by']
          : step.kind === 'assistant'
            ? ['text', 'approved', 'note', 'answered_by']
            : (catalog?.actions.find((candidate) => candidate.name === step.operation)?.outputs ?? []);
    for (const field of outputs) out.push({ path: `steps.${step.id}.${field}`, group: step.id, example: undefined });
    // FLOW-F25: whether it was skipped, or failed and carried on.
    if (step.run_if) out.push({ path: `steps.${step.id}.skipped`, group: step.id, example: undefined });
    if (step.kind !== 'ask' && step.on_error === 'continue') {
      for (const field of ['failed', 'error_code']) out.push({ path: `steps.${step.id}.${field}`, group: step.id, example: undefined });
    }
  }
  return out;
}
