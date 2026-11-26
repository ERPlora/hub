// BasketSheet (ONLINE_ORDER-F04): the order a customer is about to send from their table. Each line with what goes
// with it, its note, its quantity with one less and one more, and its amount; the total below; «Send order», which
// waits while it is sent and says why it was refused. With nothing in it, it says the order is empty.
import type { SessionMe } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';

import { click, mountInShell } from '../__tests__/mount-online-order';
import type { BasketLine } from '../lib/basket';
import en from '../locale/en.json';
import es from '../locale/es.json';
import BasketSheet from './BasketSheet.vue';

const VISITOR: SessionMe = { user: null, permissions: [], menu: [], apps: [], language: 'en' };
const CROQUETTES: BasketLine = {
  key: 1,
  kind: 'dish',
  ref: 'p1',
  name: 'Croquettes',
  price: 750,
  picks: [{ id: 'o1', name: 'Aioli', price_delta: 50 }],
  quantity: 2,
  notes: 'No salt',
};

async function setup(lines: BasketLine[], more: Record<string, unknown> = {}) {
  return mountInShell(
    BasketSheet,
    { props: { open: true, lines, money: { currency: 'EUR', decimals: 2 }, ...more }, session: VISITOR },
    { path: '/p/casa-pepe/order/code', session: VISITOR, messages: { en, es } },
  );
}

describe('BasketSheet', () => {
  it('lists each line with what goes with it, its note and its amount, and the total', async () => {
    const s = await setup([CROQUETTES]);
    const line = s.inDoc('oo-order-line-1')!.innerHTML;
    for (const told of ['Croquettes', 'Aioli', 'No salt', '€16.00']) expect(line).toContain(told);
    expect(s.inDoc('oo-order-total')!.textContent).toContain('€16.00');
  });

  it('asks one more or one less of a line', async () => {
    const s = await setup([CROQUETTES]);
    await click(s.inDoc('oo-order-more-1'));
    await click(s.inDoc('oo-order-less-1'));
    expect(s.wrapper.emitted('quantity')).toEqual([
      [1, 3],
      [1, 1],
    ]);
  });

  it('says the order is empty and sends nothing', async () => {
    const s = await setup([]);
    expect(s.inDoc('oo-order-empty')!.innerHTML).toContain('Your order is empty');
    expect((s.inDoc('oo-order-sheet-submit') as HTMLButtonElement).disabled).toBe(true);
  });

  it('sends the order', async () => {
    const s = await setup([CROQUETTES]);
    await click(s.inDoc('oo-order-sheet-submit'));
    expect(s.wrapper.emitted('send')).toHaveLength(1);
  });
});
