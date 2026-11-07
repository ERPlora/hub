// «Which data?» (WORKBOOK FLOW-F11): the data a step can insert, grouped by where they come from — what
// started the automation, with a real example of this business, and what each earlier step leaves —;
// one tap picks it. Without data it says what to do first; while the catalog is read, «Loading…»; if it could not
// be read, the error with «Retry» (hub#969).
import { ApiError } from '@erplora/ui/sdk';
import { describe, expect, it, vi } from 'vitest';

import { click, mountFlow, settle, TASK_CATALOG, TASK_STEPS } from '../__tests__/mount-flow';
import FieldPicker from './FieldPicker.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

async function setup(choices: unknown[], more: Record<string, unknown> = {}) {
  const m = await mountFlow(FieldPicker, { props: { open: true, choices, steps: TASK_STEPS, catalog: TASK_CATALOG, ...more } });
  await settle();
  return m;
}

describe('FieldPicker', () => {
  it('groups the data by where they come from, each with its words and its example', async () => {
    const m = await setup([
      { path: 'input.total', group: 'input', example: 12500 },
      { path: 'steps.s1.number', group: 's1', example: undefined },
    ]);
    expect(m.find('flow-picker-group-input').text()).toBe('What brought it');
    expect(m.find('flow-picker-group-s1').text()).toBe('What step 1 left');
    expect(m.find('flow-picker-input.total').text()).toContain('Total');
    expect(m.find('flow-picker-input.total').text()).toContain('e.g. 12500');
    expect(m.find('flow-picker-steps.s1.number').text()).toContain('1. Create a task › Number');
  });

  it('a tap picks the datum and closes', async () => {
    const m = await setup([{ path: 'input.total', group: 'input', example: 1 }]);
    await click(m.find('flow-picker-input.total').element);
    expect(m.wrapper.emitted('pick')).toEqual([['input.total']]);
    expect(m.wrapper.emitted('update:open')).toEqual([[false]]);
  });

  it('without data says what to do first', async () => {
    const m = await setup([]);
    expect(m.find('flow-picker-none').text()).toBe(
      'There is no data to insert here yet: choose what happens first, or add an action before.',
    );
  });

  // FLOW-F27: inside a call, the secrets and the call's no-repeat key are offered too, by name.
  it('offers the secrets and the no-repeat key of a call under their own headings', async () => {
    const m = await setup([
      { path: 'secret.STRIPE_KEY', group: 'secret', example: undefined },
      { path: 'run.idempotency_key', group: 'run', example: undefined },
    ]);
    expect(m.find('flow-picker-group-secret').text()).toBe('Secrets');
    expect(m.find('flow-picker-group-run').text()).toBe('This call');
    expect(m.find('flow-picker-secret.STRIPE_KEY').text()).toContain('Secret «STRIPE_KEY»');
    expect(m.find('flow-picker-run.idempotency_key').text()).toContain('No-repeat key');
  });

  // hub#969: opened before the catalog of actions is in, it says it is loading, never that there is nothing.
  it('while the catalog is read says «Loading…», not that there is nothing, and offers nothing yet', async () => {
    const m = await setup([{ path: 'input.total', group: 'input', example: 1 }], { catalog: null, loading: true });
    expect(m.find('flow-picker-loading').text()).toBe('Loading…');
    expect(m.find('flow-picker-loading').attributes('role')).toBe('status');
    expect(m.find('flow-picker-none').exists()).toBe(false);
    expect(m.find('flow-picker-input.total').exists()).toBe(false);
  });

  it('a catalog that could not be read is said in red with «Retry», never «nothing to insert»; what is known stays', async () => {
    const failure = new ApiError(500, 'internal_error', 'Internal error');
    const m = await setup([{ path: 'input.total', group: 'input', example: 1 }], { catalog: null, error: failure });
    expect(m.find('flow-picker-error').text()).toContain('What automations can use here could not be read.');
    expect(m.find('flow-picker-error').text()).not.toContain('Internal error');
    expect(m.find('flow-picker-loading').exists()).toBe(false);
    expect(m.find('flow-picker-input.total').exists()).toBe(true);
    await click(m.find('flow-picker-retry').element);
    expect(m.wrapper.emitted('retry')).toEqual([[]]);
    expect(m.wrapper.emitted('update:open')).toBeUndefined();

    const empty = await setup([], { catalog: null, error: failure });
    expect(empty.find('flow-picker-error').exists()).toBe(true);
    expect(empty.find('flow-picker-none').exists()).toBe(false);
  });
});
