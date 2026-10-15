// «Permissions» (WORKBOOK FLOW-F12): what the steps ask for, in words — waiting for your permission or
// allowed —, «Allow everything it needs» and «Withdraw»; the whole list goes to the server each time.
// Before the first save there is nothing to allow yet, and it says so.
import { describe, expect, it, vi } from 'vitest';

import type { CatalogOut, FlowOut, Step } from '../operations';
import { click, mountFlow, settle } from '../__tests__/mount-flow';
import PermissionsPanel from './PermissionsPanel.vue';

const toastSuccess = vi.hoisted(() => vi.fn<(message: string) => Promise<void>>(async () => undefined));
vi.mock('@erplora/ui/shell', async (importOriginal) => ({ ...(await importOriginal<typeof import('@erplora/ui/shell')>()), toastSuccess }));

const CATALOG = {
  events: [],
  actions: [
    { name: 'task.task.create', kind: 'command', app: 'task', app_name: 'Tasks', description: '', fields: [], outputs: [] },
    { name: 'customer.customer.detail', kind: 'query', app: 'customer', app_name: 'Customers', description: '', fields: [], outputs: [] },
  ],
} as unknown as CatalogOut;
const STEPS: Step[] = [
  { id: 's1', kind: 'query', operation: 'customer.customer.detail', params: {}, result: 'first' },
  { id: 's2', kind: 'command', operation: 'task.task.create', params: {} },
];
const FLOW = { id: 'f1', grants: ['task.task.create'] } as FlowOut;

async function setup(flow: FlowOut | null, steps: Step[] = STEPS, answer: [number, unknown] = [200, { ...FLOW, grants: ['task.task.create', 'customer.customer.detail'] }]) {
  toastSuccess.mockClear();
  return mountFlow(PermissionsPanel, { props: { flow: flow ? ({ ...flow, steps } as FlowOut) : null, dirty: false, catalog: CATALOG }, answers: { '/api/flow/flows/grant': answer } });
}

describe('PermissionsPanel', () => {
  it('lists what the steps ask for: waiting or allowed, in words', async () => {
    const m = await setup(FLOW);
    expect(m.find('flow-perm-intro').text()).toBe(
      'An automation runs with its own permissions, never with yours. Nothing below happens until you allow it.',
    );
    expect(m.find('flow-perm-missing-customer.customer.detail').text()).toContain('Waiting for your permission');
    expect(m.find('flow-perm-missing-customer.customer.detail').text()).toContain('Read a customer');
    expect(m.find('flow-perm-granted-task.task.create').text()).toContain('Allowed');
    expect(m.find('flow-perm-granted-task.task.create').text()).toContain('Create a task');
  });

  it('«Allow everything it needs» sends the whole list and says so', async () => {
    const m = await setup(FLOW);
    await click(m.find('flow-perm-grantall').element);
    await settle();
    expect(m.sent().map((call) => [call.path, call.body])).toEqual([
      ['/api/flow/flows/grant', { id: 'f1', operations: ['task.task.create', 'customer.customer.detail'] }],
    ]);
    expect(toastSuccess).toHaveBeenCalledWith('Permissions updated.');
  });

  it('«Withdraw» sends the list without it', async () => {
    const m = await setup(FLOW, STEPS, [200, { ...FLOW, grants: [] }]);
    await click(m.find('flow-perm-withdraw-task.task.create').element);
    await settle();
    expect(m.sent()[0].body).toEqual({ id: 'f1', operations: [] });
  });

  it('a refusal is said in red, nothing changes', async () => {
    const m = await setup(FLOW, STEPS, [422, { error: { code: 'invalid_payload', message: 'That action does not exist in this business: «x».' } }]);
    await click(m.find('flow-perm-grantall').element);
    await settle();
    expect(m.find('flow-perm-error').text()).toContain('That action does not exist in this business');
    expect(toastSuccess).not.toHaveBeenCalled();
  });

  it('before the first save there is nothing to allow; steps that ask nothing say so', async () => {
    expect((await setup(null)).find('flow-perm-savefirst').text()).toBe('Save it first: then you can allow what it needs.');
    const none = await setup({ ...FLOW, grants: [] }, [{ id: 's1', kind: 'delay', seconds: 60 }]);
    expect(none.find('flow-perm-none').text()).toBe('Its steps ask for nothing.');
    expect(none.find('flow-perm-grantall').exists()).toBe(false);
  });
});

describe('PermissionsPanel: review 2026-10-15, item 12', () => {
  it('reads what is missing from the saved steps, and asks to save the changes first', async () => {
    const saved = { ...FLOW, steps: [STEPS[1]], grants: [] } as unknown as FlowOut;
    const m = await mountFlow(PermissionsPanel, { props: { flow: saved, dirty: true, catalog: CATALOG } });
    expect(m.find('flow-perm-missing-task.task.create').exists()).toBe(true);
    expect(m.find('flow-perm-missing-customer.customer.detail').exists()).toBe(false);
    expect(m.find('flow-perm-dirty').text()).toBe('Save it first: what you allow is what is saved.');
  });
});
