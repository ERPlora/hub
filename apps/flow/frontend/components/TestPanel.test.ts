// «Try it» (WORKBOOK FLOW-F13): what the automation would do with the last thing that really happened
// in this business, step by step, executing nothing — what would come out empty, what the action
// would refuse, where a condition would stop it, what it is not allowed yet —, with the editor's
// document as it is, saved or not.
import { describe, expect, it } from 'vitest';

import type { CatalogOut, TestOut } from '../operations';
import { click, mountFlow, settle } from '../__tests__/mount-flow';
import TestPanel from './TestPanel.vue';

const CATALOG = {
  events: [{ name: 'sale.sale.completed', app: 'sale', app_name: 'Sales' }],
  actions: [{ name: 'task.task.create', kind: 'command', app: 'task', app_name: 'Tasks', description: '', fields: [], outputs: [] }],
} as unknown as CatalogOut;

const DOC = {
  name: 'Big sale',
  enabled: false,
  trigger: { kind: 'event' as const, event: 'sale.sale.completed' },
  steps: [
    { id: 's1', kind: 'condition' as const, when: { 'input.total': { gte: 10000 } } },
    { id: 's2', kind: 'delay' as const, seconds: 3600 },
    { id: 's3', kind: 'command' as const, operation: 'task.task.create', params: { title: 'Hi {{input.customer_name}}' } },
  ],
};

const ANSWER: TestOut = {
  sample: { found: true, event: 'sale.sale.completed', at: '2026-10-15T10:00:00+02:00', payload: { total: 12500 } },
  starts: true,
  trigger_failed: [],
  steps: [
    { id: 's1', kind: 'condition', outcome: 'would_run', operation: '', params: {}, empty: [], unknown: [], errors: {}, failed: [], seconds: null },
    { id: 's2', kind: 'delay', outcome: 'waits', operation: '', params: {}, empty: [], unknown: [], errors: {}, failed: [], seconds: 3600 },
    {
      id: 's3',
      kind: 'command',
      outcome: 'refused',
      operation: 'task.task.create',
      params: { title: 'Hi ' },
      empty: ['title'],
      unknown: [],
      errors: { priority: 'Input should be low, medium, high or urgent' },
      failed: [],
      seconds: null,
    },
  ],
};

async function setup(answer: [number, unknown] = [200, ANSWER], flowId: string | null = 'f1') {
  const m = await mountFlow(TestPanel, { props: { document: DOC, flowId, catalog: CATALOG }, answers: { '/api/flow/flows/test': answer } });
  await settle();
  return m;
}

describe('TestPanel', () => {
  it('asks the server with the editor’s document and the saved automation’s permissions', async () => {
    const m = await setup();
    const [call] = m.sent();
    expect([call.method, call.path, call.query.id]).toEqual(['GET', '/api/flow/flows/test', 'f1']);
    expect(JSON.parse(call.query.document as string)).toEqual({ trigger: DOC.trigger, steps: DOC.steps });
  });

  it('says nothing is real and what it tries with', async () => {
    const m = await setup();
    expect(m.find('flow-test-banner').text()).toContain('None of this is real.');
    expect(m.find('flow-test-sample').text()).toMatch(/^With what really happened the last time: a sale is charged \(/);
  });

  it('walks the steps: what each would do, what comes out empty and what would be refused', async () => {
    const m = await setup();
    expect(m.find('flow-test-step-s1').attributes('data-outcome')).toBe('would_run');
    expect(m.find('flow-test-step-s2').text()).toContain('Would wait 1 hour');
    const task = m.find('flow-test-step-s3');
    expect(task.attributes('data-outcome')).toBe('refused');
    expect(task.text()).toContain('They would refuse it');
    expect(task.text()).toContain('Would arrive empty: Title');
    expect(task.text()).toContain('Priority: Input should be low, medium, high or urgent');
  });

  it('says when it would not even start, and when nothing like it happened lately', async () => {
    const m = await setup([200, { ...ANSWER, starts: false, trigger_failed: [{ path: 'input.total', op: 'gte', value: 10000 }], sample: { ...ANSWER.sample } }]);
    expect(m.find('flow-test-notstart').text()).toContain('It would not even start');
    expect(m.find('flow-test-notstart').text()).toContain('Total greater than or equal to 10000');
    const none = await setup([200, { ...ANSWER, sample: { found: false, event: 'sale.sale.completed', at: null, payload: {} } }]);
    expect(none.find('flow-test-sample').text()).toBe('This has not happened in your business lately, so it walks the steps with nothing in.');
  });

  it('a failure says why and tries again', async () => {
    const m = await setup([422, { error: { code: 'invalid_payload', message: 'Bad document' } }]);
    expect(m.find('flow-test-error').text()).toContain('Bad document');
    m.answerBy({ '/api/flow/flows/test': [200, ANSWER] });
    await click(m.find('flow-test-again').element);
    await settle();
    expect(m.find('flow-test-step-s3').exists()).toBe(true);
  });
});

describe('TestPanel: review 2026-10-15, item 1', () => {
  it('an action that needs a person is said to be no automation’s', async () => {
    const step = { ...ANSWER.steps[2], outcome: 'high_risk' as const, operation: 'sale.order.void' };
    const m = await setup([200, { ...ANSWER, steps: [step] }]);
    expect(m.find('flow-test-step-s3').text()).toContain('needs a person in front: an automation cannot do it');
  });

  // FLOW-F27: a call says where it would go and with what (secrets as ••••), never calling.
  it('a call says where it would go and with what, and names the call when it is not allowed yet', async () => {
    const call = { id: 's4', kind: 'http' as const, method: 'POST' as const, url: 'https://api.example.com/v1/x', headers: { Authorization: 'Bearer {{secret.KEY}}' }, body: '', timeout: 10 };
    const step = {
      ...ANSWER.steps[2],
      id: 's4',
      kind: 'http',
      outcome: 'would_call' as const,
      operation: '',
      empty: [],
      errors: {},
      params: { method: 'POST', url: 'https://api.example.com/v1/x', headers: { Authorization: 'Bearer ••••' }, body: '', host: 'api.example.com' },
    };
    const m = await mountFlow(TestPanel, {
      props: { document: { ...DOC, steps: [call] }, flowId: 'f1', catalog: CATALOG },
      answers: { '/api/flow/flows/test': [200, { ...ANSWER, steps: [step] }] },
    });
    await settle();
    const text = m.find('flow-test-step-s4').text();
    expect(text).toContain('Call api.example.com');
    expect(text).toContain('Would call api.example.com');
    expect(text).toContain('Bearer ••••');
    expect(text).not.toContain('Host');
    const refused = await mountFlow(TestPanel, {
      props: { document: { ...DOC, steps: [call] }, flowId: 'f1', catalog: CATALOG },
      answers: { '/api/flow/flows/test': [200, { ...ANSWER, steps: [{ ...step, outcome: 'not_allowed' }] }] },
    });
    await settle();
    expect(refused.find('flow-test-step-s4').text()).toContain('you have not allowed it «Call api.example.com» yet');
  });
});

