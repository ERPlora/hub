// «Which data?» (WORKBOOK FLOW-F11): the data a step can insert, grouped by where they come from — what
// started the automation, with a real example of this business, and what each earlier step leaves —;
// one tap picks it. Without data it says what to do first.
import { describe, expect, it, vi } from 'vitest';

import type { CatalogOut, Step } from '../operations';
import { click, mountFlow, settle } from '../__tests__/mount-flow';
import FieldPicker from './FieldPicker.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const CATALOG = { events: [], actions: [{ name: 'task.task.create', kind: 'command', app: 'task', app_name: 'Tasks', description: '', fields: [], outputs: ['number'] }] } as unknown as CatalogOut;
const STEPS: Step[] = [{ id: 's1', kind: 'command', operation: 'task.task.create', params: {} }];

async function setup(choices: unknown[]) {
  const m = await mountFlow(FieldPicker, { props: { open: true, choices, steps: STEPS, catalog: CATALOG } });
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
});

