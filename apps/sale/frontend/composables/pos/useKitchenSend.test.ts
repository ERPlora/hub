import { describe, expect, it } from 'vitest';

import { CHECK, freshEachTest, setup } from '../../__tests__/till';
import { line, order, product, refused } from '../../components/pos/__tests__/fixtures';

freshEachTest();

describe('useTill: sending the round to the kitchen (SALE-F20, KITCHEN-F18)', () => {
  const SENT = order({ id: 'o1', version: 3, lines: [line({ id: 'l1', product_id: 'p1', round_no: 1, fired_at: '2026-10-20T12:00:00Z' })] });
  const TICKET = { id: 't1', number: 'K-0001', short_number: '1', round_no: 1 };
  const answer = (s: Awaited<ReturnType<typeof setup>>) =>
    s.net.onApi((call) => Response.json(call.url.startsWith('/api/kitchen/tickets/send') ? TICKET : SENT));

  it('asks Kitchen to send what is pending, normal or rush, then reads the check back with its round', async () => {
    const s = await setup();
    s.reply(CHECK);
    await s.till().addProduct(product({ id: 'p1' }), null);
    answer(s);
    expect(await s.till().sendToKitchen(true)).toEqual({ ok: true, round: 1, printed: true });
    const sent = s.sent().filter((c) => c.path === '/api/kitchen/tickets/send');
    expect(sent.map((c) => c.body)).toEqual([{ order_id: 'o1', priority: 'rush' }]);
    expect(s.till().order.value?.lines[0].round_no).toBe(1);
    await s.till().sendToKitchen(false);
    expect(s.sent().filter((c) => c.path === '/api/kitchen/tickets/send').at(-1)?.body).toEqual({ order_id: 'o1', priority: 'normal' });
  });

  it('says when the round went but its sheet did not print', async () => {
    const s = await setup();
    s.reply(CHECK);
    await s.till().addProduct(product({ id: 'p1' }), null);
    s.net.onApi((call) =>
      Response.json(call.url.startsWith('/api/kitchen/tickets/send') ? { ...TICKET, print_error: 'no printer' } : SENT),
    );
    expect(await s.till().sendToKitchen(false)).toEqual({ ok: true, round: 1, printed: false });
  });

  it('hands the refusal back in the server’s words', async () => {
    const s = await setup();
    s.reply(CHECK);
    await s.till().addProduct(product({ id: 'p1' }), null);
    s.net.onApi(() => refused('sale.nothing_to_fire', 'There is nothing new to send to the kitchen.'));
    expect(await s.till().sendToKitchen(false)).toEqual({
      ok: false,
      message: 'There is nothing new to send to the kitchen.',
      code: 'sale.nothing_to_fire',
    });
  });
});
