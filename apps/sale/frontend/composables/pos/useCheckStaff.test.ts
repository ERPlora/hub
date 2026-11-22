// Who serves the check on the till (SALE-F16) is the check's, kept in the Hub: a check on screen says who the Hub
// says, choosing someone for it saves it there, and someone chosen before there is a check opens it with them.
import { toastError } from '@erplora/ui/shell';
import { describe, expect, it, vi } from 'vitest';
import { shallowRef } from 'vue';

import { mountComposable, settle } from '../../__tests__/mount-sale';
import { order } from '../../components/pos/__tests__/fixtures';
import type { OrderOut } from '../../operations';
import { useCheckStaff } from './useCheckStaff';

const LUCIA = { id: 's9', name: 'Lucia Garcia' };
const ME = { id: null, name: null };
const SERVED_BY_LUCIA = order({ id: 'o1', version: 2, staff_id: 's9', staff_name: 'Lucia Garcia' });

async function setup(check: OrderOut | null = null, answer: [number, unknown] = [200, SERVED_BY_LUCIA]) {
  const current = shallowRef<OrderOut | null>(check);
  const orderId = shallowRef<string | null>(check?.id ?? null);
  const follow = vi.fn((next: OrderOut) => (current.value = next));
  let served!: ReturnType<typeof useCheckStaff>;
  const m = await mountComposable(() => {
    served = useCheckStaff({ order: current, orderId, follow });
  });
  m.net.onApi(() => Response.json(answer[1], { status: answer[0] }));
  const saves = () => m.sent().filter((call) => call.path === '/api/sale/orders/set_staff').map((call) => call.body);
  return { served, current, orderId, follow, saves };
}

describe('useCheckStaff', () => {
  it('a check on screen says who serves it as the Hub keeps it; nobody kept is «me»', async () => {
    const s = await setup(SERVED_BY_LUCIA);
    expect(s.served.staff.value).toEqual(LUCIA);
    s.current.value = order({ id: 'o1', staff_id: null, staff_name: '' });
    expect(s.served.staff.value).toEqual(ME);
  });

  it('choosing someone for the check on screen saves it on the check and the till follows the answer', async () => {
    const s = await setup(order({ id: 'o1' }));
    const saved = s.served.choose(LUCIA);
    expect(s.served.staff.value).toEqual(LUCIA);
    await saved;
    await settle();
    expect(s.saves()).toEqual([{ order_id: 'o1', staff_id: 's9' }]);
    expect(s.follow).toHaveBeenCalledWith(SERVED_BY_LUCIA);
    expect(s.served.staff.value).toEqual(LUCIA);
  });

  it('«me» saves nobody on the check', async () => {
    const s = await setup(SERVED_BY_LUCIA, [200, order({ id: 'o1', version: 3 })]);
    await s.served.choose(ME);
    expect(s.saves()).toEqual([{ order_id: 'o1', staff_id: null }]);
    expect(s.served.staff.value).toEqual(ME);
  });

  it('a refusal is said and the check stays with whoever served it', async () => {
    const refused = { error: { code: 'sale.staff_unavailable', message: 'Staff is not active in this business.' } };
    const s = await setup(order({ id: 'o1' }), [409, refused]);
    await s.served.choose(LUCIA);
    await settle();
    expect(toastError).toHaveBeenCalledWith('Staff is not active in this business.');
    expect(s.follow).not.toHaveBeenCalled();
    expect(s.served.staff.value).toEqual(ME);
  });

  it('with no check yet, who is chosen waits for it and the check opens with them; nothing is saved before', async () => {
    const s = await setup();
    await s.served.choose(LUCIA);
    expect(s.served.staff.value).toEqual(LUCIA);
    expect(s.served.opening()).toEqual({ staff_id: 's9' });
    expect(s.saves()).toEqual([]);
  });

  it('once the check is on screen, what was waiting is spent: the next check starts with «me»', async () => {
    const s = await setup();
    await s.served.choose(LUCIA);
    s.orderId.value = 'o1';
    s.current.value = SERVED_BY_LUCIA;
    await settle();
    expect(s.saves()).toEqual([]);
    s.orderId.value = null;
    s.current.value = null;
    await settle();
    expect(s.served.staff.value).toEqual(ME);
    expect(s.served.opening()).toEqual({});
  });

  it('a check opened elsewhere for this screen (Tables, seating it) knows nobody: who was waiting is saved on it', async () => {
    const s = await setup();
    await s.served.choose(LUCIA);
    s.orderId.value = 'o1';
    await settle();
    expect(s.saves()).toEqual([{ order_id: 'o1', staff_id: 's9' }]);
    expect(s.follow).toHaveBeenCalledWith(SERVED_BY_LUCIA);
    expect(s.served.opening()).toEqual({});
  });

  it('the screen starting afresh forgets who was waiting', async () => {
    const s = await setup();
    await s.served.choose(LUCIA);
    s.served.clear();
    expect(s.served.staff.value).toEqual(ME);
    expect(s.served.opening()).toEqual({});
  });
});
