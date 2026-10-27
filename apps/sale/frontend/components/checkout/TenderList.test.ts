// «Payments taken» of a split payment (SALE-F03): one row per leg — its method's icon, name and amount,
// and «Change x» when cash gave change; tapping the row brings the leg back to the keypad, ✕ removes it.
// Both named with the method and the amount for a screen reader.
import { HubIcon } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';

import { click, mountSale } from '../../__tests__/mount-sale';
import { plain } from '../../lib/format';
import type { Leg, TenderMethod } from '../../lib/checkout/tender';
import TenderList from './TenderList.vue';

const CASH: TenderMethod = { id: 'm-cash', display_name: 'Cash', type: 'cash', requires_change: true };
const CARD: TenderMethod = { id: 'm-card', display_name: 'Card', type: 'card', requires_change: false };
const LEGS: Leg[] = [
  { id: 'leg-1', method: CARD, amount: 2000, tendered: 2000 },
  { id: 'leg-2', method: CASH, amount: 2250, tendered: 3000 },
];

async function setup(locale: 'en' | 'es' = 'en') {
  const m = await mountSale(TenderList, { props: { legs: LEGS }, locale });
  await m.live();
  const rows = () => m.wrapper.findAll('[data-testid="sale-checkout-leg"]');
  return { ...m, rows };
}

describe('TenderList', () => {
  it('lists the legs under «Payments taken»: icon, name, amount and the change cash gave', async () => {
    const s = await setup();
    expect(s.find('sale-checkout-legs-label').text()).toBe('Payments taken');
    const parts = (i: number) => s.rows()[i].findAll('.tender-name, .tender-amount, .tender-change').map((p) => plain(p.text()));
    expect([parts(0), parts(1)]).toEqual([
      ['Card', '€20.00'],
      ['Cash', '€22.50', 'Change €7.50'],
    ]);
    expect(s.wrapper.findAllComponents(HubIcon).map((i) => i.props('name'))).toEqual([
      'ion:card-outline',
      'ion:close-outline',
      'ion:cash-outline',
      'ion:close-outline',
    ]);
  });

  it('names each action with the method and the amount', async () => {
    const s = await setup();
    const row = s.rows()[1];
    expect(plain(row.find('[data-testid="sale-checkout-leg-edit"]').attributes('aria-label') ?? '')).toBe('Edit Cash, €22.50');
    expect(plain(row.find('[data-testid="sale-checkout-leg-remove"]').attributes('aria-label') ?? '')).toBe('Remove Cash, €22.50');
  });

  it('brings a leg back to the keypad or removes it', async () => {
    const s = await setup();
    await click(s.rows()[0].find('[data-testid="sale-checkout-leg-edit"]').element);
    await click(s.rows()[1].find('[data-testid="sale-checkout-leg-remove"]').element);
    expect([s.wrapper.emitted('edit'), s.wrapper.emitted('remove')]).toEqual([[['leg-1']], [['leg-2']]]);
  });

  it('speaks Spanish', async () => {
    const s = await setup('es');
    expect(s.find('sale-checkout-legs-label').text()).toBe('Cobros tomados');
    expect(plain(s.rows()[1].find('.tender-change').text())).toBe('Cambio 7,50 €');
    expect(plain(s.rows()[0].find('[data-testid="sale-checkout-leg-remove"]').attributes('aria-label') ?? '')).toBe('Quitar Card, 20,00 €');
  });
});
