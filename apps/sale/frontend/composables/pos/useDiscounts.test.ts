import { describe, expect, it } from 'vitest';

import { approvalDialog, CANCELLED } from '../../__tests__/approval-dialog';
import { EMPLOYEE } from '../../__tests__/mount-sale';
import { answers, asks, CHECK, freshEachTest, setup } from '../../__tests__/till';
import { line, product, refused } from '../../components/pos/__tests__/fixtures';

freshEachTest();

describe('useTill: discounts and the manager’s door', () => {
  async function withCheck(extra: Parameters<typeof setup>[0] = {}) {
    const s = await setup({ settings: { max_discount_percent: 15 }, ...extra });
    s.reply(CHECK);
    await s.till().addProduct(product({ id: 'p1' }), null);
    return s;
  }

  it('a line discount within the cap goes through the ordinary door', async () => {
    const s = await withCheck();
    expect(await s.till().setLineDiscount(line({ id: 'l1' }), '10')).toEqual({ ok: true });
    expect(s.calls().at(-1)).toEqual(['/set_line_discount', { order_id: 'o1', line_id: 'l1', discount_percent: '10' }]);
  });

  it('above the cap a manager goes through the manager’s door', async () => {
    const s = await withCheck();
    await s.till().setLineDiscount(line({ id: 'l1' }), '30');
    expect(s.calls().at(-1)).toEqual(['/set_line_discount_over_limit', { order_id: 'o1', line_id: 'l1', discount_percent: '30' }]);
  });

  it('above the cap an employee asks a manager, who approves it with their PIN on this device', async () => {
    const s = await withCheck({ session: EMPLOYEE });
    s.net.onApi(answers(refused('sale.discount_over_limit', 'Over the cap.'), asks('sale.order.set_line_discount_over_limit', 'Discount a line above the maximum')));
    expect(await s.till().setLineDiscount(line({ id: 'l1' }), '30')).toEqual({ ok: true });
    const body = { order_id: 'o1', line_id: 'l1', discount_percent: '30' };
    expect(s.calls().slice(1)).toEqual([
      ['/set_line_discount', body],
      ['/set_line_discount_over_limit', body],
      ['/set_line_discount_over_limit', body],
    ]);
    expect(approvalDialog.questions.map((question) => question.label)).toEqual(['Discount a line above the maximum']);
  });

  it('«Cancel» on the approval hands the sheet its refusal, and the check stays as it was', async () => {
    const s = await withCheck({ session: EMPLOYEE });
    approvalDialog.answer = CANCELLED;
    s.net.onApi(answers(refused('sale.discount_over_limit', 'Over the cap.'), asks('sale.order.set_discount_over_limit', 'Discount the check above the maximum')));
    expect(await s.till().setTicketDiscount({ percent: '50', amount: 0 })).toEqual({ ok: false, message: 'This needs a manager’s approval.' });
    expect(s.till().order.value).toEqual(CHECK);
  });

  it('a refusal of another kind asks no manager', async () => {
    const s = await withCheck({ session: EMPLOYEE });
    s.net.onApi(() => refused('sale.discounts_not_allowed', 'This business does not allow discounts.'));
    expect(await s.till().setLineDiscount(line({ id: 'l1' }), '30')).toEqual({ ok: false, message: 'This business does not allow discounts.' });
    expect(approvalDialog.questions).toEqual([]);
  });

  it('a fixed ticket amount over the cap (the server says so) is retried through the manager’s door', async () => {
    const s = await withCheck();
    let count = 0;
    s.net.onApi(() => (++count === 1 ? refused('sale.discount_over_limit', 'Over the cap.') : Response.json(CHECK)));
    expect(await s.till().setTicketDiscount({ percent: '0', amount: 900 })).toEqual({ ok: true });
    expect(s.calls().slice(1)).toEqual([
      ['/set_discount', { order_id: 'o1', discount_percent: '0', discount_amount: 900 }],
      ['/set_discount_over_limit', { order_id: 'o1', discount_percent: '0', discount_amount: 900 }],
    ]);
  });
});
