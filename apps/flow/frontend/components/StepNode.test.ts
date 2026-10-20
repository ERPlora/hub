// One step of the column (WORKBOOK FLOW-F11): «Do something» and «Look something up» are cards that open
// to choose the action (a list of this business's, in words) and fill what it asks for; «Only continue
// if…» is a dashed chip; «Wait» is a label on the line. Each has its handle and its ×.
import { Combo } from '@erplora/ui/components';
import { describe, expect, it } from 'vitest';

import type { CatalogOut, Step } from '../operations';
import { click, ionValue, mountFlow } from '../__tests__/mount-flow';
import ConditionRows from './ConditionRows.vue';
import AskStepPanel from './AskStepPanel.vue';
import HttpStepPanel from './HttpStepPanel.vue';
import StepNode from './StepNode.vue';
import StepOptions from './StepOptions.vue';
import ValueBox from './ValueBox.vue';

const CATALOG = {
  events: [],
  actions: [
    {
      name: 'task.task.create',
      kind: 'command',
      app: 'task',
      app_name: 'Tasks',
      description: 'Create a task',
      fields: [
        { name: 'title', type: 'string', required: true, description: 'What has to be done.', choices: [] },
        { name: 'priority', type: 'choice', required: false, description: 'Priority.', choices: ['low', 'medium', 'high', 'urgent'] },
        { name: 'description', type: 'string', required: false, description: '', choices: [] },
      ],
      outputs: ['id'],
    },
    { name: 'customer.customer.detail', kind: 'query', app: 'customer', app_name: 'Customers', description: '', fields: [], outputs: ['name'] },
  ],
} as unknown as CatalogOut;

async function setup(step: Step, open = true, errors: Record<string, string> = {}) {
  const m = await mountFlow(StepNode, {
    props: { step, index: 0, steps: [step], catalog: CATALOG, open, errors, choices: [], pick: async () => 'input.name' },
  });
  const emitted = () => (m.wrapper.emitted('update:step') ?? []).map(([value]) => value);
  return { ...m, emitted };
}

describe('StepNode', () => {
  it('a wait is a label on the line; it opens to say how long', async () => {
    const s = await setup({ id: 's1', kind: 'delay', seconds: 7200 });
    expect(s.find('flow-step-open-s1').text()).toBe('Wait 2 hours');
    expect((s.find('flow-step-amount-s1').element as unknown as { value: number }).value).toBe(2);
    await ionValue(s.find('flow-step-unit-s1').element, 'days');
    await ionValue(s.find('flow-step-amount-s1').element, '3', 'ionInput');
    expect(s.emitted()).toEqual([
      { id: 's1', kind: 'delay', seconds: 172800 },
      { id: 's1', kind: 'delay', seconds: 10800 },
    ]);
  });

  it('«Only continue if…» is a chip with its comparisons', async () => {
    const s = await setup({ id: 's1', kind: 'condition', when: { 'input.total': { gt: 1 } } });
    expect(s.find('flow-step-open-s1').text()).toBe('Only continue if Total greater than 1');
    s.wrapper.findComponent(ConditionRows).vm.$emit('update:modelValue', { 'input.total': { gt: 2 } });
    expect(s.emitted()).toEqual([{ id: 's1', kind: 'condition', when: { 'input.total': { gt: 2 } } }]);
  });

  it('«Do something» chooses the action from this business’s, in words', async () => {
    const s = await setup({ id: 's1', kind: 'command', operation: '', params: {} });
    expect(s.find('flow-step-open-s1').text()).toBe('Choose what this step does');
    const combo = s.wrapper.findComponent(Combo);
    expect(combo.props('options')).toEqual([{ id: 'task.task.create', label: 'Create a task', hint: 'Tasks · task.task.create' }]);
    combo.vm.$emit('update:modelValue', { id: 'task.task.create', label: 'Create a task' });
    expect(s.emitted()).toEqual([{ id: 's1', kind: 'command', operation: 'task.task.create', params: { title: '' } }]);
  });

  it('fills what the action asks for: the required always, the rest when added', async () => {
    const s = await setup({ id: 's1', kind: 'command', operation: 'task.task.create', params: { title: 'Hi' } });
    const boxes = () => s.wrapper.findAllComponents(ValueBox).map((box) => [box.props('label'), box.props('required'), box.props('modelValue')]);
    expect(boxes()).toEqual([['Title', true, 'Hi']]);
    await ionValue(s.find('flow-step-addinfo-s1').element, 'priority');
    expect(s.emitted().at(-1)).toEqual({ id: 's1', kind: 'command', operation: 'task.task.create', params: { title: 'Hi', priority: '' } });
    s.wrapper.findAllComponents(ValueBox)[0].vm.$emit('update:modelValue', 'Call {{input.name}}');
    expect(s.emitted().at(-1)).toEqual({ id: 's1', kind: 'command', operation: 'task.task.create', params: { title: 'Call {{input.name}}' } });
  });

  it('an optional field shows its choices and can be taken out', async () => {
    const s = await setup({ id: 's1', kind: 'command', operation: 'task.task.create', params: { title: 'Hi', priority: 'high' } });
    const priority = s.wrapper.findAllComponents(ValueBox)[1];
    expect(priority.props('helper')).toBe('low, medium, high, urgent');
    await click(s.find('flow-step-unparam-s1-priority').element);
    expect(s.emitted().at(-1)).toEqual({ id: 's1', kind: 'command', operation: 'task.task.create', params: { title: 'Hi' } });
  });

  it('«Look something up» chooses a read and what to keep', async () => {
    const s = await setup({ id: 's1', kind: 'query', operation: 'customer.customer.detail', params: {}, result: 'first' });
    expect(s.find('flow-step-open-s1').text()).toBe('Look up: Read a customer');
    await ionValue(s.find('flow-step-result-s1').element, 'count');
    expect(s.emitted().at(-1)).toMatchObject({ result: 'count' });
    expect(s.find('flow-step-queryhint-s1').exists()).toBe(true);
  });

  it('shows the server’s refusal next to the action and removes the step', async () => {
    const s = await setup({ id: 's1', kind: 'command', operation: 'spa.sauna.heat', params: {} }, true, {
      'steps.0.operation': 'That action does not exist in this business: «spa.sauna.heat».',
    });
    expect(s.wrapper.findComponent(Combo).props('errorText')).toBe('That action does not exist in this business: «spa.sauna.heat».');
    await click(s.find('flow-step-remove-s1').element);
    expect(s.wrapper.emitted('remove')).toHaveLength(1);
  });

  it('closed, only its line shows; a tap opens it', async () => {
    const s = await setup({ id: 's1', kind: 'command', operation: 'task.task.create', params: { title: 'Hi' } }, false);
    expect(s.find('flow-step-panel-s1').exists()).toBe(false);
    await click(s.find('flow-step-open-s1').element);
    expect(s.wrapper.emitted('toggle')).toHaveLength(1);
  });

  // FLOW-F25: the options of a step, inside it, and what they say when it is closed.
  it('an action, a read and a wait carry «More options»; a condition does not', async () => {
    const command = await setup({ id: 's1', kind: 'command', operation: 'task.task.create', params: { title: 'x' } });
    expect(command.wrapper.findComponent(StepOptions).exists()).toBe(true);
    command.wrapper.findComponent(StepOptions).vm.$emit('update:step', { id: 's1', kind: 'command', operation: 'task.task.create', params: { title: 'x' }, on_error: 'continue' });
    expect(command.emitted().at(-1)).toEqual({ id: 's1', kind: 'command', operation: 'task.task.create', params: { title: 'x' }, on_error: 'continue' });
    const wait = await setup({ id: 's1', kind: 'delay', seconds: 60 });
    expect(wait.wrapper.findComponent(StepOptions).exists()).toBe(true);
    const condition = await setup({ id: 's1', kind: 'condition', when: {} });
    expect(condition.wrapper.findComponent(StepOptions).exists()).toBe(false);
  });

  it('a closed step says its «Only if…» and that it carries on if it fails', async () => {
    const s = await setup({ id: 's1', kind: 'command', operation: 'task.task.create', params: {}, run_if: { 'input.total': { gt: 10000 } }, on_error: 'continue' }, false);
    expect(s.find('flow-step-summary-s1').text()).toBe('Only if: Total greater than 10000 · If it fails, it carries on');
    const plain = await setup({ id: 's1', kind: 'command', operation: 'task.task.create', params: {} }, false);
    expect(plain.find('flow-step-summary-s1').exists()).toBe(false);
  });

  // FLOW-F27: «Call another system» is a card named by its host; open, its form and its options.
  it('a call is a card named by its host that opens to its form and its options', async () => {
    const call: Step = { id: 's1', kind: 'http', method: 'POST', url: 'https://api.example.com/v1/x', headers: {}, body: '', timeout: 10, on_error: 'continue' };
    const closed = await setup(call, false);
    expect(closed.find('flow-step-open-s1').text()).toContain('Call api.example.com');
    expect(closed.find('flow-step-summary-s1').text()).toBe('If it fails, it carries on');
    const s = await setup(call);
    expect(s.wrapper.findComponent(HttpStepPanel).exists()).toBe(true);
    expect(s.wrapper.findComponent(StepOptions).exists()).toBe(true);
    s.wrapper.findComponent(HttpStepPanel).vm.$emit('update:step', { ...call, method: 'PUT' });
    expect(s.emitted().at(-1)).toMatchObject({ method: 'PUT' });
  });

  // FLOW-F28: «Ask someone first» is a card named by its question; open, its form and «Only if…» (it never fails).
  it('a question is a card named by what it asks that opens to its form', async () => {
    const question: Step = { id: 's1', kind: 'ask', title: 'Refund?', details: '', role: '', hours: 72, on_no: 'stop', on_timeout: 'no' };
    const closed = await setup(question, false);
    expect(closed.find('flow-step-open-s1').text()).toContain('Ask: Refund?');
    const s = await setup(question);
    expect(s.wrapper.findComponent(AskStepPanel).exists()).toBe(true);
    s.wrapper.findComponent(AskStepPanel).vm.$emit('update:step', { ...question, hours: 5 });
    expect(s.emitted().at(-1)).toMatchObject({ hours: 5 });
    expect(s.find('flow-step-onerror-s1').exists()).toBe(false);
  });
});
