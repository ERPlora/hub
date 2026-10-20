// Words for what an automation does (WORKBOOK «Cómo son las páginas»). The server says WHICH events and
// actions exist (`flow.catalog.read`, already in the person's language for the app names); this file
// says what they are CALLED. Layered, as in the old module: a hand-written phrase for the known ones
// (`flow.events.*`, `flow.actions.*`), composed from the app and a dictionary of facts and verbs for the
// rest, and the raw words for what nobody wrote down yet. An event or action without a phrase is still
// offered: hiding it would be a gap, naming it plainly is only cosmetic.
import type { StatusPillTone } from '@erplora/ui/components';

import type { CatalogOut, ClauseOut, LogEntry, RunStatus, Step, Trigger } from '../operations';
import { delayParts, isPath } from './document';

/** The translator the phrasing needs: `t` and `te` of the app, and its language. */
export interface Phrasing {
  t: (key: string, named?: Record<string, unknown>) => string;
  te: (key: string) => boolean;
  locale: string;
}

const key = (name: string): string => name.replaceAll('.', '__');

function humanize(text: string): string {
  return text.replaceAll('_', ' ');
}

function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function appName(label: string, catalog: CatalogOut | null | undefined): string {
  return (
    catalog?.events.find((event) => event.app === label)?.app_name ??
    catalog?.actions.find((action) => action.app === label)?.app_name ??
    label
  );
}

/** «a sale is charged», or «Customers: group deleted» for an event without a phrase. */
export function eventLabel(name: string, catalog: CatalogOut | null | undefined, p: Phrasing): string {
  const curated = `flow.events.${key(name)}`;
  if (p.te(curated)) return p.t(curated);
  const [app = name, entity = '', fact = ''] = name.split('.');
  const factKey = `flow.facts.${fact}`;
  const factWord = p.te(factKey) ? p.t(factKey) : humanize(fact);
  return `${appName(app, catalog)}: ${humanize(entity)} ${factWord}`.trim();
}

/** «Create a task», or «Create · Reservations (waitlist)» for an action without a phrase. */
export function actionLabel(name: string, catalog: CatalogOut | null | undefined, p: Phrasing): string {
  const curated = `flow.actions.${key(name)}`;
  if (p.te(curated)) return p.t(curated);
  const [app = name, entity = '', verb = ''] = name.split('.');
  const verbKey = `flow.verbs.${verb}`;
  const verbWord = p.te(verbKey) ? p.t(verbKey) : humanize(verb);
  return `${verbWord} · ${appName(app, catalog)} (${humanize(entity)})`;
}

/** «Title», or «Party size» for a field without a word. */
export function fieldLabel(name: string, p: Phrasing): string {
  const known = `flow.fields.${name}`;
  return p.te(known) ? p.t(known) : capitalize(humanize(name));
}

/** Where a datum comes from: «Customer › Name», «1. Create a task › Number». */
export function pathLabel(path: string, steps: readonly Step[], catalog: CatalogOut | null | undefined, p: Phrasing): string {
  const [root, ...rest] = path.split('.');
  if (root === 'input' && rest.length) return rest.map((part) => fieldLabel(part, p)).join(' › ');
  if (root === 'steps' && rest.length >= 2) {
    const index = steps.findIndex((step) => step.id === rest[0]);
    const step = steps[index];
    if (!step || (step.kind !== 'command' && step.kind !== 'query')) return path;
    return `${index + 1}. ${actionLabel(step.operation, catalog, p)} › ${rest.slice(1).map((part) => fieldLabel(part, p)).join(' › ')}`;
  }
  return path;
}

function formatDate(iso: string, locale: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Europe/Madrid' }).format(date);
}

/** «When a sale is charged», «Every Friday at 18:00», «Only when you press Run»… */
export function describeTrigger(trigger: Trigger, catalog: CatalogOut | null | undefined, p: Phrasing): string {
  if (trigger.kind === 'event') {
    return trigger.event ? p.t('flow.trigger.describe.event', { event: eventLabel(trigger.event, catalog, p) }) : p.t('flow.trigger.describe.noEvent');
  }
  if (trigger.kind === 'schedule') {
    if (trigger.every === 'week') {
      return p.t('flow.trigger.describe.week', { weekday: p.t(`flow.trigger.weekdays.${trigger.weekday ?? 0}`), time: trigger.time });
    }
    if (trigger.every === 'month') return p.t('flow.trigger.describe.month', { day: trigger.day ?? 1, time: trigger.time });
    return p.t('flow.trigger.describe.day', { time: trigger.time });
  }
  if (trigger.kind === 'at') return trigger.at ? p.t('flow.trigger.describe.at', { date: formatDate(trigger.at, p.locale) }) : p.t('flow.trigger.describe.noDate');
  return p.t('flow.trigger.describe.manual');
}

/** «1 hour», «90 minutes», «2 days». */
export function describeDuration(seconds: number, p: Phrasing): string {
  const { amount, unit } = delayParts(seconds);
  return `${amount} ${p.t(`flow.steps.units.${unit}.${amount === 1 ? 'one' : 'many'}`)}`;
}

/** «Wait 1 hour». */
export function describeDelay(seconds: number, p: Phrasing): string {
  const { amount, unit } = delayParts(seconds);
  return p.t('flow.steps.wait', { amount, unit: p.t(`flow.steps.units.${unit}.${amount === 1 ? 'one' : 'many'}`) });
}

function valueText(value: unknown, p: Phrasing): string {
  if (value === true) return p.t('flow.steps.yes');
  if (value === false) return p.t('flow.steps.no');
  if (Array.isArray(value)) return value.map((item) => valueText(item, p)).join(', ');
  if (value === null || value === undefined) return '—';
  return typeof value === 'object' ? JSON.stringify(value) : String(value);
}

/** «Total greater than or equal to 10000», «Customer present: yes». */
export function describeClause(clause: Pick<ClauseOut, 'path' | 'op' | 'value'>, steps: readonly Step[], catalog: CatalogOut | null | undefined, p: Phrasing): string {
  const what = pathLabel(clause.path, steps, catalog, p);
  const op = p.t(`flow.steps.operators.${clause.op}`);
  if (clause.op === 'exists') return `${what} ${op}: ${valueText(clause.value, p)}`;
  // Another datum is named in words, never by its path (hub#1712).
  const named = (value: unknown): unknown => (isPath(value) ? pathLabel(String(value), steps, catalog, p) : value);
  const value = Array.isArray(clause.value) ? clause.value.map(named) : named(clause.value);
  return `${what} ${op} ${valueText(value, p)}`;
}

/** What a step does, in one line (the card's title). */
export function describeStep(step: Step, steps: readonly Step[], catalog: CatalogOut | null | undefined, p: Phrasing): string {
  if (step.kind === 'delay') return describeDelay(step.seconds, p);
  if (step.kind === 'condition') {
    const clauses = Object.entries(step.when ?? {}).flatMap(([path, comparisons]) =>
      Object.entries(comparisons ?? {}).map(([op, value]) => describeClause({ path, op: op as ClauseOut['op'], value }, steps, catalog, p)),
    );
    return clauses.length ? clauses.join('; ') : p.t('flow.steps.describe.noCondition');
  }
  if (!step.operation) return p.t('flow.steps.noAction');
  const action = actionLabel(step.operation, catalog, p);
  return step.kind === 'query' ? p.t('flow.steps.describe.query', { action }) : action;
}

/** How a run ended, with the tone of what it means (a condition that stopped it is no error). */
export function runStatusPill(status: RunStatus, p: Phrasing): { tone: StatusPillTone; label: string } {
  const tones: Record<RunStatus, StatusPillTone> = {
    running: 'info',
    waiting: 'warning',
    succeeded: 'success',
    stopped: 'info',
    failed: 'danger',
    cancelled: 'neutral',
  };
  return { tone: tones[status], label: p.t(`flow.history.statuses.${status}`) };
}

/** Active, paused, or on without the permissions it asks for («Unfinished»). */
export function statePill(flow: { enabled: boolean; missing_grants: readonly string[] }, p: Phrasing): { tone: StatusPillTone; label: string } {
  if (!flow.enabled) return { tone: 'neutral', label: p.t('flow.paused') };
  if (flow.missing_grants.length) return { tone: 'warning', label: p.t('flow.unfinished') };
  return { tone: 'success', label: p.t('flow.active') };
}

/** One line of a run's history, in words. */
export function describeLog(entry: LogEntry, steps: readonly Step[], catalog: CatalogOut | null | undefined, p: Phrasing): string {
  const action = entry.operation ? actionLabel(entry.operation, catalog, p) : '';
  switch (entry.outcome) {
    case 'done':
      return p.t('flow.history.log.done', { action });
    case 'found':
      return p.t('flow.history.log.found', { n: entry.count ?? 1 });
    case 'not_found':
      return p.t('flow.history.log.not_found');
    case 'passed':
      return p.t('flow.history.log.passed');
    case 'stopped':
      return p.t('flow.history.log.stopped', {
        clauses: (entry.failed ?? []).map((clause) => describeClause(clause, steps, catalog, p)).join('; '),
      });
    case 'waiting':
      return p.t('flow.history.log.waiting', { date: formatDate(entry.until ?? entry.at, p.locale) });
    case 'waited':
      return p.t('flow.history.log.waited', { duration: describeDuration(entry.seconds ?? 0, p) });
    case 'resumed':
      return p.t('flow.history.log.resumed');
    default:
      return p.t('flow.history.log.failed', { action: action || entry.step, message: entry.error?.message ?? '' });
  }
}
