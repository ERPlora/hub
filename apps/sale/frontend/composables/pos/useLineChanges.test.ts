import { toastError } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';

import { approvalDialog } from '../../__tests__/approval-dialog';
import { EMPLOYEE } from '../../__tests__/mount-sale';
import { answers, asks, CHECK, freshEachTest, setup } from '../../__tests__/till';
import { line, product, refused } from '../../components/pos/__tests__/fixtures';

freshEachTest();

describe('useTill: the lines', () => {
  async function withCheck(extra: Parameters<typeof setup>[0] = {}) {
    const s = await setup(extra);
    s.reply(CHECK);
    await s.till().addProduct(product({ id: 'p1' }), null);
    return s;
  }

  it('a quantity goes to the line; zero takes the line off', async () => {
    const s = await withCheck();
    await s.till().setQuantity(line({ id: 'l1' }), '0.532');
    await s.till().setQuantity(line({ id: 'l1' }), '0');
    expect(s.calls().slice(1)).toEqual([
      ['/update_line', { order_id: 'o1', line_id: 'l1', quantity: '0.532' }],
      ['/remove_line', { order_id: 'o1', line_id: 'l1' }],
    ]);
  });

  it('a refused quantity says why and the line stays as the server keeps it', async () => {
    const s = await withCheck();
    s.net.onApi(() => refused('sale.quantity_off_grid', 'Quantity doesn’t fit the product’s step'));
    await s.till().setQuantity(line({ id: 'l1' }), '0.5');
    expect(toastError).toHaveBeenCalledExactlyOnceWith('Quantity doesn’t fit the product’s step');
    expect(s.till().order.value).toEqual(CHECK);
  });

  it('comps a line with its reason, and takes the comp off', async () => {
    const s = await withCheck({ locale: 'es' });
    await s.till().toggleGift(line({ id: 'l1', is_gift: false }));
    await s.till().toggleGift(line({ id: 'l1', is_gift: true }));
    expect(s.calls().slice(1)).toEqual([
      ['/update_line', { order_id: 'o1', line_id: 'l1', is_gift: true, gift_reason: 'Invitación' }],
      ['/update_line', { order_id: 'o1', line_id: 'l1', is_gift: false, gift_reason: '' }],
    ]);
  });

  it('a note and the customer allergy go to their existing operations', async () => {
    const s = await withCheck();
    expect(await s.till().setNote(line({ id: 'l1' }), 'No ice', ['gluten', 'milk'])).toEqual({ ok: true });
    expect(s.calls().slice(-2)).toEqual([['/update_line', { order_id: 'o1', line_id: 'l1', notes: 'No ice' }], ['/set_line_allergy', { order_id: 'o1', line_id: 'l1', allergy: ['gluten', 'milk'] }]]);
  });

  it('moves a line to another professional; a refusal says it stays with the one it had', async () => {
    const s = await withCheck();
    await s.till().setLineStaff(line({ id: 'l1' }), 's3');
    expect(s.calls().at(-1)).toEqual(['/set_line_staff', { order_id: 'o1', line_id: 'l1', staff_id: 's3' }]);
    s.net.onApi(() => new Response('Bad gateway', { status: 502 }));
    await s.till().setLineStaff(line({ id: 'l1' }), null);
    expect(toastError).toHaveBeenCalledWith('The line could not be moved to another professional. It stays with the one it had.');
  });

  it('voids a line sent to the kitchen with its reason', async () => {
    const s = await withCheck();
    expect(await s.till().voidLine(line({ id: 'l1' }), 'Sold out')).toEqual({ ok: true });
    expect(s.calls().at(-1)).toEqual(['/void_line', { order_id: 'o1', line_id: 'l1', reason: 'Sold out' }]);
  });

  it('an employee voids a line sent to the kitchen once a manager approves it with their PIN', async () => {
    const s = await withCheck({ session: EMPLOYEE });
    s.net.onApi(answers(asks('sale.order.void_line', 'Void an item already sent to the kitchen')));
    expect(await s.till().voidLine(line({ id: 'l1' }), 'Sold out')).toEqual({ ok: true });
    const body = { order_id: 'o1', line_id: 'l1', reason: 'Sold out' };
    expect(s.calls().slice(-2)).toEqual([
      ['/void_line', body],
      ['/void_line', body],
    ]);
    expect(approvalDialog.questions.map((question) => question.label)).toEqual(['Void an item already sent to the kitchen']);
  });
});
