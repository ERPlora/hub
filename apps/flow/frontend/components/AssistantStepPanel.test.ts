// The form of «Ask the assistant» (WORKBOOK FLOW-F37; old hub HUB-F95): what it is asked (with data inserted), the
// reads and actions it may use — only the ones the assistant can use, each a permission of the automation —, whether
// a change waits for a yes («Ask me first») or it makes it on its own, and its most turns. Refusals show by field.
import { describe, expect, it } from 'vitest';

import type { CatalogOut, Step } from '../operations';
import { ionValue, mountFlow } from '../__tests__/mount-flow';
import AssistantStepPanel from './AssistantStepPanel.vue';
import ValueBox from './ValueBox.vue';

const STEP: Step = { id: 's1', kind: 'assistant', prompt: 'Book {{input.name}}', tools: ['task.task.list'], mode: 'ask', max_rounds: 6 };

const action = (name: string, kind: 'command' | 'query', assistant: boolean, ask_first = false) => ({
  name, kind, app: 'task', app_name: 'Tasks', description: '', fields: [], outputs: [], assistant, ask_first,
});
const CATALOG: CatalogOut = {
  events: [],
  actions: [
    action('task.task.list', 'query', true),
    action('task.task.create', 'command', true),
    action('customer.health.detail', 'query', false),
    action('reservation.reservation.cancel', 'command', true, true),
  ],
};
const options = (s: Awaited<ReturnType<typeof setup>>) =>
  (s.wrapper.findComponent({ name: 'Combo' }).props('options') as { id: string }[]).map((option) => option.id);

async function setup(step: Step = STEP, errors: Record<string, string> = {}) {
  const m = await mountFlow(AssistantStepPanel, { props: { step, index: 0, steps: [step], catalog: CATALOG, errors, pick: async () => 'input.name' } });
  const emitted = () => (m.wrapper.emitted('update:step') ?? []).map(([value]) => value as Step);
  const box = m.wrapper.findAllComponents(ValueBox).find((candidate) => candidate.props('testid') === 'flow-assistant-prompt-s1')!;
  return { ...m, emitted, box };
}

describe('AssistantStepPanel', () => {
  it('writes what it is asked, a datum alone as text', async () => {
    const s = await setup();
    s.box.vm.$emit('update:modelValue', 'input.name');
    expect(s.emitted().at(-1)).toMatchObject({ prompt: '{{input.name}}' });
  });

  it('offers only what the assistant can use, and adds and removes it', async () => {
    const s = await setup();
    expect(s.find('flow-assistant-tool-s1-task.task.list').text()).toBe('Look for tasks');
    const combo = s.wrapper.findComponent({ name: 'Combo' });
    expect(options(s)).toEqual(['reservation.reservation.cancel', 'task.task.create']);
    combo.vm.$emit('update:modelValue', { id: 'task.task.create', label: 'Create' });
    expect(s.emitted().at(-1)).toMatchObject({ tools: ['task.task.list', 'task.task.create'] });
    // Once added, the search holds the choice and then nothing again (the Combo empties its field), the same Combo:
    // never a new one over the old one's open list.
    await s.wrapper.vm.$nextTick();
    expect(combo.props('modelValue')).toMatchObject({ id: 'task.task.create' });
    await new Promise((resolve) => setTimeout(resolve));
    const after = s.wrapper.findComponent({ name: 'Combo' });
    expect([after.vm.$.uid, after.props('modelValue')]).toEqual([combo.vm.$.uid, null]);
    await s.find('flow-assistant-tool-remove-s1-task.task.list').trigger('click');
    expect(s.emitted().at(-1)).toMatchObject({ tools: [] });
  });

  it('a change waits for a yes by default, or it makes it on its own', async () => {
    const s = await setup();
    expect(s.find('flow-assistant-modehint-s1').text()).toBe(
      'A change it wants waits for a yes in Automations, under «Waiting for your answer». What it only looks up never waits.',
    );
    await ionValue(s.find('flow-assistant-mode-s1').element, 'auto');
    expect(s.emitted().at(-1)).toMatchObject({ mode: 'auto' });
    const own = await setup({ ...STEP, mode: 'auto' });
    expect(own.find('flow-assistant-modehint-s1').text()).toBe('It makes the changes on its own, as this automation, with the permissions you gave it.');
  });

  it('offers cancelling a booking only when it asks first, and says who can say yes to it', async () => {
    const asking = await setup({ ...STEP, tools: ['reservation.reservation.cancel'] });
    expect(asking.find('flow-assistant-askfirst-s1').text()).toBe(
      'Only after a yes from someone who may do it themselves: «Cancel a reservation».',
    );
    const own = await setup({ ...STEP, mode: 'auto' });
    expect(options(own)).toEqual(['task.task.create']);
    expect(own.wrapper.find('[data-testid="flow-assistant-askfirst-s1"]').exists()).toBe(false);
    // Named but on its own (a row the server would refuse): the hint belongs to «Ask me first» alone.
    const slipped = await setup({ ...STEP, mode: 'auto', tools: ['reservation.reservation.cancel'] });
    expect(slipped.wrapper.find('[data-testid="flow-assistant-askfirst-s1"]').exists()).toBe(false);
    const plain = await setup();
    expect(plain.wrapper.find('[data-testid="flow-assistant-askfirst-s1"]').exists()).toBe(false);
  });

  it('takes from one to ten turns', async () => {
    const s = await setup();
    await ionValue(s.find('flow-assistant-rounds-s1').element, '3', 'ionInput');
    expect(s.emitted().at(-1)).toMatchObject({ max_rounds: 3 });
    await ionValue(s.find('flow-assistant-rounds-s1').element, '40', 'ionInput');
    expect(s.emitted().at(-1)).toMatchObject({ max_rounds: 10 });
  });

  it('shows the server refusals next to their field', async () => {
    const s = await setup(STEP, { 'steps.0.tools': 'The assistant cannot use «customer.health.detail».' });
    expect(s.find('flow-assistant-tools-error-s1').text()).toBe('The assistant cannot use «customer.health.detail».');
  });
});
