// Sales & POS → Sell: another check on the till, parked under a title or resumed; one opened by its address is
// `PosPage.linked.test.ts`'s.
import { toastSuccess } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';

import { click, flush, settle } from '../__tests__/mount-sale';
import { CHECK, freshEachTest, setup } from '../__tests__/pos-page';
import DirtyCheckDialog from '../components/pos/DirtyCheckDialog.vue';
import ParkSheet from '../components/pos/ParkSheet.vue';
import PosCart from '../components/pos/PosCart.vue';
import { CURRENT_CHECK_KEY } from '../composables/pos/useCurrentCheck';

freshEachTest();

describe('PosPage: parking and switching', () => {
  it('parks under a title: the screen empties and says so', async () => {
    const s = await setup();
    await s.addProduct();
    await click(s.find('pos-park').element);
    expect(s.wrapper.findComponent(ParkSheet).props('open')).toBe(true);
    s.reply(CHECK);
    s.wrapper.findComponent(ParkSheet).vm.$emit('park', 'Ana');
    await settle();
    expect(s.writes().at(-1)).toEqual(['/api/sale/orders/set_label', { order_id: 'o1', label: 'Ana' }]);
    expect(toastSuccess).toHaveBeenCalledWith('Parked as “Ana”');
    expect(localStorage.getItem(CURRENT_CHECK_KEY)).toBeNull();
    expect(s.wrapper.findComponent(ParkSheet).props('open')).toBe(false);
  });

  it('resuming another check with lines on screen asks first; «Park it and open» parks and switches', async () => {
    const s = await setup();
    await s.addProduct();
    s.wrapper.findComponent(PosCart).vm.$emit('resume', { id: 'o2', label: 'Table 2' });
    await settle();
    expect(s.wrapper.findComponent(DirtyCheckDialog).props('open')).toBe(true);
    s.reply(CHECK);
    s.wrapper.findComponent(DirtyCheckDialog).vm.$emit('choose', 'park');
    await settle();
    await flush();
    expect(s.writes().find((w) => w[0] === '/api/sale/orders/set_label')?.[1]).toMatchObject({ order_id: 'o1' });
    expect(localStorage.getItem(CURRENT_CHECK_KEY)).toBe('o2');
    expect(s.wrapper.findComponent(DirtyCheckDialog).props('open')).toBe(false);
  });

  it('with nothing on screen, a check is resumed straight away', async () => {
    const s = await setup();
    s.wrapper.findComponent(PosCart).vm.$emit('resume', { id: 'o2', label: '' });
    await settle();
    expect(localStorage.getItem(CURRENT_CHECK_KEY)).toBe('o2');
    expect(s.wrapper.findComponent(DirtyCheckDialog).props('open')).toBe(false);
  });
});
