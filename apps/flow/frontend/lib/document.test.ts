// The editing model of an automation (WORKBOOK FLOW-F09 to F12): the document the editor holds, how a
// step is added, ordered and removed, how a value composed of text and picked data becomes what the
// server reads, the permissions the steps ask for and the server's 422 put next to its step. Pure.
import { describe, expect, it } from 'vitest';

import type { CatalogOut, FlowOut, Step } from '../operations';
import {
  addStep,
  conditionRows,
  dataChoices,
  delayParts,
  emptyDocument,
  fieldErrors,
  fromFlow,
  isPath,
  missingGrants,
  moveStep,
  newStepId,
  partsToValue,
  patchStep,
  removeStep,
  requiredGrants,
  rowsToCondition,
  secondsOf,
  toPayload,
  valueToParts,
} from './document';

const CMD: Step = { id: 's1', kind: 'command', operation: 'task.task.create', params: { title: 'Hi' } };

describe('the document', () => {
  it('a new automation starts by hand, with no steps', () => {
    expect(emptyDocument()).toEqual({ name: '', enabled: false, trigger: { kind: 'manual' }, steps: [] });
  });

  it('reads a saved automation, dropping what its schedule does not use', () => {
    const flow = {
      name: 'Weekly',
      enabled: true,
      trigger: { kind: 'schedule', every: 'week', weekday: 4, day: null, time: '18:00' },
      steps: [CMD],
    } as unknown as FlowOut;
    expect(fromFlow(flow)).toEqual({
      name: 'Weekly',
      enabled: true,
      trigger: { kind: 'schedule', every: 'week', weekday: 4, time: '18:00' },
      steps: [CMD],
    });
  });

  it('adds, removes, moves and patches steps without touching the original', () => {
    const doc = emptyDocument();
    const one = addStep(doc, 'command');
    expect(doc.steps).toEqual([]);
    expect(one.steps).toEqual([{ id: 's1', kind: 'command', operation: '', params: {} }]);
    const two = addStep(addStep(addStep(one, 'query'), 'condition'), 'delay');
    expect(two.steps.map((s) => [s.id, s.kind])).toEqual([
      ['s1', 'command'],
      ['s2', 'query'],
      ['s3', 'condition'],
      ['s4', 'delay'],
    ]);
    expect(two.steps[1]).toMatchObject({ result: 'first', params: {} });
    expect(two.steps[2]).toMatchObject({ when: {} });
    expect(two.steps[3]).toMatchObject({ seconds: 3600 });
    expect(moveStep(two, 3, 0).steps.map((s) => s.id)).toEqual(['s4', 's1', 's2', 's3']);
    expect(removeStep(two, 1).steps.map((s) => s.id)).toEqual(['s1', 's3', 's4']);
    expect(patchStep(two, 0, { operation: 'task.task.create' }).steps[0]).toMatchObject({ operation: 'task.task.create' });
  });

  it('a new step takes the first free id', () => {
    expect(newStepId([CMD, { ...CMD, id: 's3' }])).toBe('s2');
    expect(newStepId([])).toBe('s1');
  });

  it('what is sent to the server', () => {
    const doc = { ...emptyDocument(), name: ' Weekly ', trigger: { kind: 'schedule' as const, every: 'day' as const, time: '09:00' }, steps: [CMD] };
    // The switch is `flow.flow.set_enabled`'s alone (review 2026-10-15, item 3).
    expect(toPayload(doc)).toEqual({ name: 'Weekly', trigger: { kind: 'schedule', every: 'day', time: '09:00' }, steps: [CMD] });
  });
});

describe('values: text and picked data', () => {
  it('a path is a root and its fields', () => {
    expect(isPath('input.total')).toBe(true);
    expect(isPath('steps.s1.id')).toBe(true);
    expect(isPath('input')).toBe(false);
    expect(isPath('input.lines.0')).toBe(false);
    expect(isPath('Call them')).toBe(false);
  });

  it('a lone picked field keeps its type; text around it makes a template', () => {
    expect(partsToValue([{ kind: 'field', path: 'input.total' }])).toBe('input.total');
    expect(
      partsToValue([
        { kind: 'text', text: 'Call ' },
        { kind: 'field', path: 'input.customer_name' },
      ]),
    ).toBe('Call {{input.customer_name}}');
    expect(partsToValue([])).toBe('');
  });

  it('typed text that is a number or a yes/no is sent as one; anything else as text', () => {
    expect(partsToValue([{ kind: 'text', text: '10000' }])).toBe(10000);
    expect(partsToValue([{ kind: 'text', text: 'true' }])).toBe(true);
    expect(partsToValue([{ kind: 'text', text: '007' }])).toBe('007');
    expect(partsToValue([{ kind: 'text', text: 'high' }])).toBe('high');
  });

  it('reads a value back into its parts', () => {
    expect(valueToParts('input.total')).toEqual([{ kind: 'field', path: 'input.total' }]);
    expect(valueToParts('Call {{input.name}}!')).toEqual([
      { kind: 'text', text: 'Call ' },
      { kind: 'field', path: 'input.name' },
      { kind: 'text', text: '!' },
    ]);
    expect(valueToParts(10000)).toEqual([{ kind: 'text', text: '10000' }]);
    expect(valueToParts(undefined)).toEqual([]);
  });
});

describe('permissions', () => {
  const steps: Step[] = [
    { id: 's1', kind: 'query', operation: 'customer.customer.detail', params: {}, result: 'first' },
    { id: 's2', kind: 'condition', when: {} },
    CMD,
    { ...CMD, id: 's4' },
    { ...CMD, id: 's5', operation: '' },
  ];

  it('are the actions and reads of the steps, once each, in order', () => {
    expect(requiredGrants(steps)).toEqual(['customer.customer.detail', 'task.task.create']);
  });

  it('the missing ones are those not granted', () => {
    expect(missingGrants(steps, ['task.task.create'])).toEqual(['customer.customer.detail']);
  });
});

describe('waits', () => {
  it('in the largest unit that divides them', () => {
    expect(delayParts(86400)).toEqual({ amount: 1, unit: 'days' });
    expect(delayParts(7200)).toEqual({ amount: 2, unit: 'hours' });
    expect(delayParts(90 * 60)).toEqual({ amount: 90, unit: 'minutes' });
    expect(secondsOf(3, 'days')).toBe(259200);
    expect(secondsOf(1, 'minutes')).toBe(60);
  });
});

describe('conditions as rows', () => {
  it('one row per comparison, and back', () => {
    const condition = { 'input.total': { gte: 10000 }, 'input.customer_id': { exists: true } };
    const rows = conditionRows(condition);
    expect(rows).toEqual([
      { path: 'input.total', op: 'gte', value: 10000 },
      { path: 'input.customer_id', op: 'exists', value: true },
    ]);
    expect(rowsToCondition(rows)).toEqual(condition);
  });

  it('a row without its data is left out; two on the same data are merged', () => {
    expect(
      rowsToCondition([
        { path: '', op: 'eq', value: 1 },
        { path: 'input.total', op: 'gt', value: 1 },
        { path: 'input.total', op: 'lt', value: 9 },
      ]),
    ).toEqual({ 'input.total': { gt: 1, lt: 9 } });
  });
});

describe('the server says where it is wrong', () => {
  it('the step and the field, whatever the kind in between', () => {
    expect(
      fieldErrors({
        'steps.0.command.operation': 'Choose what this step does.',
        'steps.2.operation': 'That action does not exist',
        'trigger.event.event': 'Choose what has to happen',
        'trigger.schedule': 'Choose the day of the week.',
        'trigger.at': 'That date has passed',
        steps: 'Step 1 reads «steps.s9.id»',
      }),
    ).toEqual({
      'steps.0.operation': 'Choose what this step does.',
      'steps.2.operation': 'That action does not exist',
      'trigger.event': 'Choose what has to happen',
      trigger: 'Choose the day of the week.',
      'trigger.at': 'That date has passed',
      steps: 'Step 1 reads «steps.s9.id»',
    });
  });
});

describe('the data a step can insert', () => {
  const catalog = {
    events: [],
    actions: [
      { name: 'task.task.create', kind: 'command', app: 'task', app_name: 'Tasks', description: '', fields: [], outputs: ['id', 'number'] },
      { name: 'customer.customer.detail', kind: 'query', app: 'customer', app_name: 'Customers', description: '', fields: [], outputs: ['name', 'found', 'count'] },
    ],
  } as CatalogOut;

  it('what the event brought (with its example) and what earlier actions and reads leave', () => {
    const steps: Step[] = [
      { id: 's1', kind: 'query', operation: 'customer.customer.detail', params: {}, result: 'first' },
      { id: 's2', kind: 'condition', when: {} },
      { ...CMD, id: 's3' },
      { ...CMD, id: 's4' },
    ];
    const choices = dataChoices(steps, 3, { total: 12500, customer: { name: 'Ana', tags: ['x'] }, lines: [{ a: 1 }] }, catalog);
    // A list is never offered: a path cannot index one.
    expect(choices).toEqual([
      { path: 'input.total', group: 'input', example: 12500 },
      { path: 'input.customer.name', group: 'input', example: 'Ana' },
      { path: 'steps.s1.name', group: 's1', example: undefined },
      { path: 'steps.s1.found', group: 's1', example: undefined },
      { path: 'steps.s1.count', group: 's1', example: undefined },
      { path: 'steps.s3.id', group: 's3', example: undefined },
      { path: 'steps.s3.number', group: 's3', example: undefined },
    ]);
  });
});
