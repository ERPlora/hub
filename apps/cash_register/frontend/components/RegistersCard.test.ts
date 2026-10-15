// «Drawers» (CASH_REGISTER-F02): the business's drawers by name with whether they are active; whoever may
// change the settings adds one, renames one and deactivates (or activates) one, which is said; nobody else
// sees those buttons.
import { DataTable } from '@erplora/ui/components';
import { toastSuccess } from '@erplora/ui/shell';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import { flush, mountCash } from '../__tests__/mount-cash-register';
import RegisterModal from './RegisterModal.vue';
import RegistersCard from './RegistersCard.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});
vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...((await importOriginal()) as object),
  toastSuccess: vi.fn(() => Promise.resolve()),
}));
beforeEach(() => vi.mocked(toastSuccess).mockClear());

const OP = 'cash_register.register.list';
const PAGE = {
  rows: [
    { id: 'r1', name: 'Bar', is_active: true },
    { id: 'r2', name: 'Terrace', is_active: false },
  ],
  total: 2,
  limit: 100,
  offset: 0,
};

async function setup(editable = true) {
  const m = await mountCash(RegistersCard, { props: { editable } });
  await m.live();
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = (name: string) => (table().props() as Record<string, unknown>)[name];
  return { ...m, table, prop };
}

describe('RegistersCard', () => {
  it('lists the drawers by name with whether they are active', async () => {
    const s = await setup();
    expect(s.params(OP)).toEqual([{ limit: 100 }]);
    await s.result(OP, PAGE);
    expect(s.find('cash-register-registers-heading').text()).toBe('Drawers');
    expect(s.prop('rows')).toEqual(PAGE.rows);
    expect(s.prop('addable')).toBe(true);
  });

  it('deactivates or activates a drawer and says so', async () => {
    const s = await setup();
    await s.result(OP, PAGE);
    s.answer(200, { id: 'r1', name: 'Bar', is_active: false });
    s.table().vm.$emit('action', { actionId: 'toggle', row: PAGE.rows[0] });
    await flush();
    expect(s.sent()).toEqual([
      { method: 'POST', path: '/api/cash_register/registers/update', query: {}, body: { register_id: 'r1', is_active: false } },
    ]);
    expect(toastSuccess).toHaveBeenCalledWith('Drawer deactivated');
  });

  it('adds and renames through the drawer window', async () => {
    const s = await setup();
    await s.result(OP, PAGE);
    s.table().vm.$emit('add');
    await flush();
    expect(s.wrapper.findComponent(RegisterModal).props()).toMatchObject({ open: true, register: null });
    s.table().vm.$emit('action', { actionId: 'rename', row: PAGE.rows[1] });
    await flush();
    expect(s.wrapper.findComponent(RegisterModal).props('register')).toEqual(PAGE.rows[1]);
  });

  it('without the permission there is nothing to change', async () => {
    const s = await setup(false);
    await s.result(OP, PAGE);
    expect(s.prop('addable')).toBe(false);
    expect(s.prop('actions')).toEqual([]);
  });
});
