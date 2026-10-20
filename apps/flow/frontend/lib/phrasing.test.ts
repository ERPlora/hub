// Words for what an automation does (WORKBOOK «Cómo son las páginas»): the events and actions of the
// active apps, its trigger, its steps, a condition, a wait and each line of a run's history, never a
// technical name where a phrase exists. Hand-written phrases for the known ones, composed for the rest.
import { createShellI18n } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';

import en from '../locale/en.json';
import es from '../locale/es.json';
import type { CatalogOut, LogEntry, Step } from '../operations';
import {
  actionLabel,
  describeClause,
  describeDelay,
  describeLog,
  describeStep,
  describeTrigger,
  eventLabel,
  fieldLabel,
  pathLabel,
  runStatusPill,
  statePill,
  type Phrasing,
} from './phrasing';

function phrasing(locale: 'en' | 'es' = 'en'): Phrasing {
  const i18n = createShellI18n({ locale, messages: { en, es } });
  const g = i18n.global as unknown as { t: (key: string, named?: Record<string, unknown>) => string; te: (key: string) => boolean };
  return { t: (key, named) => (named ? g.t(key, named) : g.t(key)), te: (key) => g.te(key), locale };
}

const CATALOG = {
  events: [
    { name: 'sale.sale.completed', app: 'sale', app_name: 'Sales' },
    { name: 'customer.group.deleted', app: 'customer', app_name: 'Customers' },
  ],
  actions: [
    { name: 'task.task.create', kind: 'command', app: 'task', app_name: 'Tasks', description: '', fields: [], outputs: ['id', 'number'] },
    { name: 'reservation.waitlist.convert', kind: 'command', app: 'reservation', app_name: 'Reservations', description: '', fields: [], outputs: [] },
    { name: 'customer.customer.detail', kind: 'query', app: 'customer', app_name: 'Customers', description: '', fields: [], outputs: ['name'] },
  ],
} as CatalogOut;

describe('events and actions in words', () => {
  it('a known event has its phrase, in each language', () => {
    expect(eventLabel('sale.sale.completed', CATALOG, phrasing())).toBe('a sale is charged');
    expect(eventLabel('sale.sale.completed', CATALOG, phrasing('es'))).toBe('se cobra una venta');
  });

  it('another one is composed from its app, its subject and what happened', () => {
    expect(eventLabel('customer.group.deleted', CATALOG, phrasing())).toBe('Customers: group deleted');
    expect(eventLabel('customer.group.deleted', CATALOG, phrasing('es'))).toBe('Customers: group borrado');
    expect(eventLabel('spa.sauna.overheated', CATALOG, phrasing())).toBe('spa: sauna overheated');
  });

  it('a known action has its phrase; another says its verb, app and subject', () => {
    expect(actionLabel('task.task.create', CATALOG, phrasing())).toBe('Create a task');
    expect(actionLabel('task.task.create', CATALOG, phrasing('es'))).toBe('Crear una tarea');
    expect(actionLabel('reservation.waitlist.convert', CATALOG, phrasing())).toBe('convert · Reservations (waitlist)');
    expect(actionLabel('reservation.waitlist.create', CATALOG, phrasing('es'))).toBe('Crear · Reservations (waitlist)');
  });

  it('a field has its word or is made readable', () => {
    expect(fieldLabel('title', phrasing('es'))).toBe('Título');
    expect(fieldLabel('party_size', phrasing())).toBe('Party size');
  });

  it('a path says where it comes from', () => {
    const steps: Step[] = [{ id: 's1', kind: 'command', operation: 'task.task.create', params: {} }];
    expect(pathLabel('input.customer_name', steps, CATALOG, phrasing())).toBe('Customer name');
    expect(pathLabel('input.customer.name', steps, CATALOG, phrasing())).toBe('Customer › Name');
    expect(pathLabel('steps.s1.number', steps, CATALOG, phrasing())).toBe('1. Create a task › Number');
    expect(pathLabel('steps.s9.id', steps, CATALOG, phrasing())).toBe('steps.s9.id');
  });
});

describe('the trigger', () => {
  it('in words, for each way of starting', () => {
    const p = phrasing();
    expect(describeTrigger({ kind: 'event', event: 'sale.sale.completed' }, CATALOG, p)).toBe('When a sale is charged');
    expect(describeTrigger({ kind: 'event', event: '' }, CATALOG, p)).toBe('Choose what has to happen for it to start');
    expect(describeTrigger({ kind: 'manual' }, CATALOG, p)).toBe('Only when you press Run');
    expect(describeTrigger({ kind: 'schedule', every: 'day', time: '09:00' }, CATALOG, p)).toBe('Every day at 09:00');
    expect(describeTrigger({ kind: 'schedule', every: 'week', weekday: 4, time: '18:00' }, CATALOG, p)).toBe('Every Friday at 18:00');
    expect(describeTrigger({ kind: 'schedule', every: 'month', day: 1, time: '08:30' }, CATALOG, p)).toBe('Every month on day 1 at 08:30');
    expect(describeTrigger({ kind: 'at', at: '2026-11-01T09:00:00+01:00' }, CATALOG, p)).toMatch(/^Once, on .*2026/);
    expect(describeTrigger({ kind: 'schedule', every: 'week', weekday: 4, time: '18:00' }, CATALOG, phrasing('es'))).toBe(
      'Todos los viernes a las 18:00',
    );
  });
});

describe('steps', () => {
  const p = phrasing();

  it('an action, a read, a condition and a wait', () => {
    expect(describeStep({ id: 's1', kind: 'command', operation: 'task.task.create', params: {} }, [], CATALOG, p)).toBe('Create a task');
    expect(describeStep({ id: 's1', kind: 'command', operation: '', params: {} }, [], CATALOG, p)).toBe('Choose what this step does');
    expect(describeStep({ id: 's1', kind: 'query', operation: 'customer.customer.detail', params: {}, result: 'first' }, [], CATALOG, p)).toBe(
      'Look up: Read a customer',
    );
    expect(describeStep({ id: 's2', kind: 'condition', when: { 'input.total': { gte: 10000 } } }, [], CATALOG, p)).toBe(
      'Total greater than or equal to 10000',
    );
    expect(describeStep({ id: 's2', kind: 'condition', when: {} }, [], CATALOG, p)).toBe('nothing yet');
    expect(describeStep({ id: 's3', kind: 'delay', seconds: 86400 }, [], CATALOG, p)).toBe('Wait 1 day');
  });

  it('a wait in its largest unit, singular or plural', () => {
    expect(describeDelay(7200, p)).toBe('Wait 2 hours');
    expect(describeDelay(60, phrasing('es'))).toBe('Esperar 1 minuto');
  });

  it('a comparison names its data, its operator and its value', () => {
    expect(describeClause({ path: 'input.customer_id', op: 'exists', value: true }, [], CATALOG, p)).toBe('Customer present: yes');
    expect(describeClause({ path: 'input.party_size', op: 'in', value: [6, 8] }, [], CATALOG, p)).toBe('Party size one of 6, 8');
  });

  it('a comparison with another datum names that datum, never its path (hub#1712)', () => {
    const clause = describeClause({ path: 'input.total', op: 'eq', value: 'input.customer_id' }, [], CATALOG, p);
    expect(clause).toContain('Customer');
    expect(clause).not.toContain('input.');
    expect(describeClause({ path: 'input.total', op: 'in', value: ['input.customer_id', 5] }, [], CATALOG, p)).not.toContain('input.');
  });
});

describe('pills', () => {
  it('a run says how it ended, with the tone of what it means', () => {
    const p = phrasing();
    expect(runStatusPill('succeeded', p)).toEqual({ tone: 'success', label: 'Finished well' });
    expect(runStatusPill('stopped', p)).toEqual({ tone: 'info', label: 'Finished: a condition did not hold' });
    expect(runStatusPill('failed', p)).toEqual({ tone: 'danger', label: 'Stopped by an error' });
    expect(runStatusPill('waiting', p)).toEqual({ tone: 'warning', label: 'Waiting' });
    expect(runStatusPill('cancelled', p)).toEqual({ tone: 'neutral', label: 'Cancelled' });
  });

  it('an automation is active, paused, or on without what it needs', () => {
    const p = phrasing();
    expect(statePill({ enabled: true, missing_grants: [] }, p)).toEqual({ tone: 'success', label: 'Active' });
    expect(statePill({ enabled: false, missing_grants: [] }, p)).toEqual({ tone: 'neutral', label: 'Paused' });
    expect(statePill({ enabled: true, missing_grants: ['task.task.create'] }, p)).toEqual({ tone: 'warning', label: 'Unfinished' });
  });
});

describe('a line of the history', () => {
  const steps: Step[] = [
    { id: 's1', kind: 'query', operation: 'customer.customer.detail', params: {}, result: 'first' },
    { id: 's2', kind: 'condition', when: { 'input.total': { gte: 10000 } } },
    { id: 's3', kind: 'command', operation: 'task.task.create', params: {} },
    { id: 's4', kind: 'delay', seconds: 3600 },
  ];
  const entry = (more: Partial<LogEntry>): LogEntry => ({ step: 's3', kind: 'command', outcome: 'done', at: '2026-10-15T10:00:00+02:00', ...more });

  it('in words, step by step', () => {
    const p = phrasing();
    expect(describeLog(entry({ operation: 'task.task.create' }), steps, CATALOG, p)).toBe('Did: Create a task');
    expect(describeLog(entry({ step: 's1', kind: 'query', outcome: 'found', count: 3 }), steps, CATALOG, p)).toBe('Found 3');
    expect(describeLog(entry({ step: 's1', kind: 'query', outcome: 'not_found' }), steps, CATALOG, p)).toBe('Found nothing, and carried on');
    expect(describeLog(entry({ step: 's2', kind: 'condition', outcome: 'passed' }), steps, CATALOG, p)).toBe('The condition held');
    expect(
      describeLog(entry({ step: 's2', kind: 'condition', outcome: 'stopped', failed: [{ path: 'input.total', op: 'gte', value: 10000 }] }), steps, CATALOG, p),
    ).toBe('It stopped here because this was not met: Total greater than or equal to 10000. That is the automation working.');
    expect(describeLog(entry({ step: 's4', kind: 'delay', outcome: 'waited', seconds: 3600 }), steps, CATALOG, p)).toBe('Waited 1 hour');
    expect(
      describeLog(entry({ operation: 'task.task.create', outcome: 'failed', error: { code: 'invalid_field', message: 'No such project.' } }), steps, CATALOG, p),
    ).toBe('Create a task: No such project.');
  });
});
