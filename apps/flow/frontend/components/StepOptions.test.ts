// The options of a step (WORKBOOK FLOW-F25): «Only if…» — when it does not hold the step is skipped and
// the automation goes on — on every step but «Only continue if…», and «If it fails, carry on with the
// next steps» on an action or a read. Off, the step keeps no option at all.
import { describe, expect, it } from 'vitest';

import type { Step } from '../operations';
import { click, ionChecked, mountFlow } from '../__tests__/mount-flow';
import ConditionRows from './ConditionRows.vue';
import StepOptions from './StepOptions.vue';

const CMD: Step = { id: 's2', kind: 'command', operation: 'task.task.create', params: {} };
const CHOICES = [{ path: 'input.total', group: 'input', example: 12500 }];

async function setup(step: Step) {
  const m = await mountFlow(StepOptions, { props: { step, choices: CHOICES, steps: [step], catalog: null, pick: async () => null } });
  const emitted = () => (m.wrapper.emitted('update:step') ?? []).map(([value]) => value as Step);
  return { ...m, emitted };
}

describe('StepOptions', () => {
  it('«Only if…» opens its conditions and saves them in the step', async () => {
    const s = await setup(CMD);
    await click(s.find('flow-step-options-toggle-s2').element);
    expect(s.wrapper.findComponent(ConditionRows).exists()).toBe(false);
    await ionChecked(s.find('flow-step-runif-s2').element, true);
    expect(s.emitted().at(-1)).toEqual({ ...CMD, run_if: {} });
  });

  it('a step with «Only if…» shows its conditions and says what happens when they do not hold', async () => {
    const s = await setup({ ...CMD, run_if: { 'input.total': { gt: 10000 } } });
    expect(s.wrapper.findComponent(ConditionRows).props('modelValue')).toEqual({ 'input.total': { gt: 10000 } });
    expect(s.find('flow-step-runif-hint-s2').text()).toBe('When it does not hold, this step is skipped and the automation goes on.');
    s.wrapper.findComponent(ConditionRows).vm.$emit('update:modelValue', { 'input.total': { gt: 5 } });
    expect(s.emitted().at(-1)).toEqual({ ...CMD, run_if: { 'input.total': { gt: 5 } } });
    await ionChecked(s.find('flow-step-runif-s2').element, false);
    expect(s.emitted().at(-1)).toEqual(CMD);
  });

  it('«If it fails, carry on» is kept as `on_error: continue`, and off it leaves nothing', async () => {
    const s = await setup(CMD);
    await click(s.find('flow-step-options-toggle-s2').element);
    await ionChecked(s.find('flow-step-onerror-s2').element, true);
    expect(s.emitted().at(-1)).toEqual({ ...CMD, on_error: 'continue' });
    const on = await setup({ ...CMD, on_error: 'continue' });
    expect(on.find('flow-step-onerror-hint-s2').text()).toBe('Its failure is written in this step and the next steps can check whether it failed.');
    await ionChecked(on.find('flow-step-onerror-s2').element, false);
    expect(on.emitted().at(-1)).toEqual(CMD);
  });

  it('a wait can be skipped but cannot fail', async () => {
    const s = await setup({ id: 's3', kind: 'delay', seconds: 60 });
    await click(s.find('flow-step-options-toggle-s3').element);
    expect(s.find('flow-step-runif-s3').exists()).toBe(true);
    expect(s.find('flow-step-onerror-s3').exists()).toBe(false);
  });

  it('«More options» is closed on a step without any and open on one that has them', async () => {
    const s = await setup(CMD);
    expect(s.find('flow-step-options-s2').exists()).toBe(false);
    await click(s.find('flow-step-options-toggle-s2').element);
    expect(s.find('flow-step-options-s2').exists()).toBe(true);
    const set = await setup({ ...CMD, on_error: 'continue' });
    expect(set.find('flow-step-options-s2').exists()).toBe(true);
    expect(set.find('flow-step-options-toggle-s2').attributes('aria-expanded')).toBe('true');
  });
});
