// Sales & POS → Sell: who serves the check (SALE-F16) is the check's, kept in the Hub. Left and opened again (a
// reload, the floor plan, «Open checks»), the chip still names who serves it; choosing someone saves it on the check;
// someone chosen before there is a check opens it with them; and a round sent leaves the name to the check.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { click, MANAGER, mountSale, settle } from '../__tests__/mount-sale';
import { posWithCheck } from '../__tests__/pos-with-check';
import CartHeading from '../components/pos/CartHeading.vue';
import PosCart from '../components/pos/PosCart.vue';
import PosCatalog from '../components/pos/PosCatalog.vue';
import StaffPicker from '../components/pos/StaffPicker.vue';
import { line, memoryStorage, order, product, settings } from '../components/pos/__tests__/fixtures';
import { CURRENT_CHECK_KEY } from '../composables/pos/useCurrentCheck';
import PosPage from './PosPage.vue';

beforeEach(() => vi.stubGlobal('localStorage', memoryStorage()));
afterEach(() => vi.unstubAllGlobals());

const LUCIA = { id: 's9', name: 'Lucia Garcia' };
const COFFEE = line({ id: 'l1', product_id: 'p1', name: 'White coffee', staff_id: 's9' });
const SERVED_BY_LUCIA = order({ id: 'o6', version: 3, label: 'Table 6', staff_id: 's9', staff_name: 'Lucia Garcia', lines: [COFFEE] });
const WITH_KITCHEN = { ...MANAGER, permissions: [...MANAGER.permissions, 'kitchen.add_ticket'], apps: [{ label: 'kitchen', state: 'on' as const }] };

/** The chip «Served by …» of the check's heading. */
const chip = (s: Awaited<ReturnType<typeof mountSale>>) => s.wrapper.findComponent(CartHeading).props();

async function pick(s: Awaited<ReturnType<typeof mountSale>>, who: { id: string | null; name: string | null }) {
  await click(s.find('pos-staff-chip').element);
  await settle();
  s.wrapper.findComponent(StaffPicker).vm.$emit('choose', who);
  await settle();
}

describe('PosPage: who serves the check is the check’s', () => {
  it('a check opened again still names who serves it, as the Hub keeps it', async () => {
    localStorage.setItem(CURRENT_CHECK_KEY, 'o6');
    const s = await mountSale(PosPage);
    await s.live();
    await s.result('sale.pos_settings.get', settings());
    await s.reopen();
    await s.result('sale.order.get', SERVED_BY_LUCIA, { order_id: 'o6' });
    await settle();
    expect(chip(s)).toMatchObject({ staffId: 's9', staffName: 'Lucia Garcia' });
    expect(s.find('pos-staff-chip').text()).toContain('Served by Lucia Garcia');
  });

  it('choosing who serves an open check saves it on the check, and the next lines are theirs', async () => {
    const s = await posWithCheck(order({ id: 'o1', lines: [line({ id: 'l1', product_id: 'p1' })] }));
    s.net.onApi(() => Response.json(order({ id: 'o1', version: 2, staff_id: 's9', staff_name: 'Lucia Garcia' })));
    await pick(s, LUCIA);
    const writes = s.sent().filter((call) => call.method === 'POST');
    expect(writes.at(-1)).toMatchObject({ path: '/api/sale/orders/set_staff', body: { order_id: 'o1', staff_id: 's9' } });
    expect(chip(s)).toMatchObject({ staffId: 's9', staffName: 'Lucia Garcia' });
    s.wrapper.findComponent(PosCatalog).vm.$emit('add', product({ id: 'p2' }));
    await settle();
    expect(s.sent().at(-1)).toMatchObject({ path: '/api/sale/orders/add_line', body: { order_id: 'o1', product_id: 'p2', staff_id: 's9' } });
  });

  it('someone chosen before there is a check opens it with them', async () => {
    const s = await mountSale(PosPage);
    await s.live();
    await s.result('sale.pos_settings.get', settings());
    await pick(s, LUCIA);
    s.net.onApi(() => Response.json(SERVED_BY_LUCIA));
    s.wrapper.findComponent(PosCatalog).vm.$emit('add', product({ id: 'p1' }));
    await settle();
    expect(s.sent().at(-1)).toMatchObject({
      path: '/api/sale/orders',
      body: { staff_id: 's9', lines: [{ product_id: 'p1', staff_id: 's9' }] },
    });
  });

  it('a round sent names nobody: the kitchen ticket names who serves the check, as the Hub keeps it', async () => {
    const s = await posWithCheck(order({ id: 'o6', lines: [COFFEE] }), { session: WITH_KITCHEN });
    s.net.onApi(({ url }) => Response.json(url.includes('/kitchen/') ? { id: 't1', round_no: 1 } : SERVED_BY_LUCIA));
    await pick(s, LUCIA);
    s.wrapper.findComponent(PosCart).vm.$emit('send', false);
    await settle();
    const sends = s.sent().filter((call) => call.path.startsWith('/api/kitchen/'));
    expect(sends.map((call) => call.body)).toEqual([{ order_id: 'o6', priority: 'normal' }]);
  });
});
