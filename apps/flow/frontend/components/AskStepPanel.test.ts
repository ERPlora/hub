// The form of «Ask someone first» (WORKBOOK FLOW-F28; the old module's flows-f18): the question and its
// details (with data inserted), who answers, how long to wait, and what a no and silence do. With «Carry
// on», it says how to act on the answer afterwards. The server's refusals show by field.
import { describe, expect, it } from 'vitest';

import type { Step } from '../operations';
import { ionValue, mountFlow } from '../__tests__/mount-flow';
import AskStepPanel from './AskStepPanel.vue';
import ValueBox from './ValueBox.vue';

const ASK: Step = { id: 's1', kind: 'ask', title: 'Refund?', details: '', role: '', hours: 72, on_no: 'stop', on_timeout: 'no' };

async function setup(step: Step = ASK, errors: Record<string, string> = {}) {
  const m = await mountFlow(AskStepPanel, { props: { step, index: 0, steps: [step], catalog: null, errors, pick: async () => 'input.amount' } });
  const emitted = () => (m.wrapper.emitted('update:step') ?? []).map(([value]) => value as Step);
  const box = (testid: string) => m.wrapper.findAllComponents(ValueBox).find((candidate) => candidate.props('testid') === testid)!;
  return { ...m, emitted, box };
}

describe('AskStepPanel', () => {
  it('writes the question and its details, a datum alone as text', async () => {
    const s = await setup();
    s.box('flow-ask-title-s1').vm.$emit('update:modelValue', 'Refund {{input.amount}}?');
    expect(s.emitted().at(-1)).toMatchObject({ title: 'Refund {{input.amount}}?' });
    s.box('flow-ask-details-s1').vm.$emit('update:modelValue', 'input.note');
    expect(s.emitted().at(-1)).toMatchObject({ details: '{{input.note}}' });
  });

  it('chooses who answers and says who else can', async () => {
    const s = await setup();
    expect(s.find('flow-ask-who-s1').text()).toBe('Whoever runs the business answers it in Automations, under «Waiting for your answer».');
    await ionValue(s.find('flow-ask-role-s1').element, 'manager');
    expect(s.emitted().at(-1)).toMatchObject({ role: 'manager' });
    const managers = await setup({ ...ASK, role: 'manager' });
    expect(managers.find('flow-ask-who-s1').text()).toBe('The managers answer it in Automations, under «Waiting for your answer»; whoever runs the business can too.');
  });

  it('waits from one hour to thirty days', async () => {
    const s = await setup();
    await ionValue(s.find('flow-ask-hours-s1').element, '24', 'ionInput');
    expect(s.emitted().at(-1)).toMatchObject({ hours: 24 });
    await ionValue(s.find('flow-ask-hours-s1').element, '9999', 'ionInput');
    expect(s.emitted().at(-1)).toMatchObject({ hours: 720 });
  });

  it('chooses what a no and silence do, and with «Carry on» says how to act on the answer', async () => {
    const s = await setup();
    expect(s.find('flow-ask-continuehint-s1').exists()).toBe(false);
    await ionValue(s.find('flow-ask-onno-s1').element, 'continue');
    expect(s.emitted().at(-1)).toMatchObject({ on_no: 'continue' });
    await ionValue(s.find('flow-ask-ontimeout-s1').element, 'stop');
    expect(s.emitted().at(-1)).toMatchObject({ on_timeout: 'stop' });
    const carrying = await setup({ ...ASK, on_timeout: 'continue' });
    expect(carrying.find('flow-ask-continuehint-s1').text()).toContain('add «Only continue if…» on «Approved»');
  });

  it('shows the server\'s refusals next to their field', async () => {
    const s = await setup(ASK, { 'steps.0.title': 'String should have at least 1 character', 'steps.0.hours': 'Input should be less than or equal to 720' });
    expect(s.box('flow-ask-title-s1').props('errorText')).toBe('String should have at least 1 character');
    expect((s.find('flow-ask-hours-s1').element as HTMLElement & { errorText?: string }).errorText).toBe('Input should be less than or equal to 720');
  });
});
