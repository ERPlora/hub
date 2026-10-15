// «Lines paid another way» in the charge sheet (SALE-F27): each line of a service of this charge with its
// voucher slot. A line a voucher pays says «<voucher>: session spent. <n> left.» with «Undo»
// (`sale.order.remove_voucher`); a line of several units is split first («Split into N lines»,
// `sale.order.split_line`, the new lines handed up); one that cannot be split says why; the others offer
// the customer's vouchers (VoucherChooser).
import { describe, expect, it } from 'vitest';

import { click, mountSale } from '../../__tests__/mount-sale';
import { previewLine } from './__tests__/vouchers';
import VoucherChooser from './VoucherChooser.vue';
import VoucherLines from './VoucherLines.vue';

async function setup(lines = [previewLine('l1')], customerId: string | null = 'c1', locale: 'en' | 'es' = 'es') {
  const m = await mountSale(VoucherLines, { props: { orderId: 'o1', lines, customerId }, locale });
  // Only a slot that offers vouchers reads anything live.
  if (m.client.stream.subscriptions('service.grant.tender_options').length) await m.live();
  const text = (testid: string) => (m.find(testid).exists() ? m.find(testid).text().replace(/\s+/g, ' ').trim() : '');
  return { ...m, text };
}

describe('VoucherLines', () => {
  it('heads the section and offers the customer’s vouchers on each line of one unit', async () => {
    const s = await setup([previewLine('l1'), previewLine('l2', { name: 'Color', service_id: 'sv2' })]);
    expect(s.text('voucher-lines-title')).toBe('Líneas pagadas de otra forma');
    const choosers = s.wrapper.findAllComponents(VoucherChooser);
    expect(choosers.map((c) => c.props())).toEqual([
      { orderId: 'o1', lineId: 'l1', serviceId: 'sv1', customerId: 'c1' },
      { orderId: 'o1', lineId: 'l2', serviceId: 'sv2', customerId: 'c1' },
    ]);
    expect(s.text('voucher-line-l2-name')).toBe('Color');
  });

  it('a line a voucher pays says the session is spent and how many are left, with «Undo»', async () => {
    const s = await setup([previewLine('l1', { paid_by_voucher: true, voucher_name: 'Bono 5 cortes', voucher_remaining: 4, line_total: 0 })]);
    expect(s.text('voucher-l1-held')).toBe('Bono 5 cortes: sesión gastada. Quedan 4.');
    expect(s.wrapper.findAllComponents(VoucherChooser)).toHaveLength(0);
    s.answer(200, {});
    await click(s.find('voucher-l1-undo').element);
    expect(s.sent().at(-1)).toMatchObject({ path: '/api/sale/orders/remove_voucher', body: { order_id: 'o1', line_id: 'l1' } });
  });

  it('an unlimited voucher only says the session is spent', async () => {
    const s = await setup([previewLine('l1', { paid_by_voucher: true, voucher_name: 'Ilimitado', voucher_remaining: null, line_total: 0 })]);
    expect(s.text('voucher-l1-held')).toBe('Ilimitado: sesión gastada.');
  });

  it('«Undo» refused says why and the session stays', async () => {
    const s = await setup([previewLine('l1', { paid_by_voucher: true, voucher_name: 'Bono', voucher_remaining: 1, line_total: 0 })]);
    s.answer(409, { error: { code: 'sale.order_changed', message: 'La cuenta ha cambiado.' } });
    await click(s.find('voucher-l1-undo').element);
    expect(s.text('voucher-l1-error')).toBe('La cuenta ha cambiado.');
  });

  it('a line of several units is split first, and the new lines go up', async () => {
    const s = await setup([previewLine('l1', { quantity: '3.000', line_total: 7500 })]);
    expect(s.text('voucher-l1-split-reason')).toBe('Un bono cubre una línea. Sepárala y canjea las que alcance.');
    expect(s.wrapper.findAllComponents(VoucherChooser)).toHaveLength(0);
    s.answer(200, { order: {}, new_line_ids: ['l8', 'l9'] });
    await click(s.find('voucher-l1-split').element);
    expect(s.text('voucher-l1-split')).toBe('Separar en 3 líneas');
    expect(s.sent().at(-1)).toMatchObject({ path: '/api/sale/orders/split_line', body: { order_id: 'o1', line_id: 'l1' } });
    expect(s.wrapper.emitted('split')).toEqual([[['l8', 'l9']]]);
  });

  it('a line that cannot be split (a fraction, more than 50) says no voucher can cover it', async () => {
    const s = await setup([previewLine('l1', { quantity: '1.500', line_total: 3750 }), previewLine('l2', { quantity: '60.000' })]);
    expect(s.text('voucher-l1-not-splittable')).toBe('Esta línea no se puede separar, así que ningún bono puede cubrirla.');
    expect(s.find('voucher-l1-split').exists()).toBe(false);
    expect(s.find('voucher-l2-not-splittable').exists()).toBe(true);
  });

  it('a failed split says so in the server’s words', async () => {
    const s = await setup([previewLine('l1', { quantity: '2.000', line_total: 5000 })]);
    s.answer(409, { error: { code: 'sale.line_not_splittable', message: 'Esta línea no se puede separar.' } });
    await click(s.find('voucher-l1-split').element);
    expect(s.text('voucher-l1-error')).toBe('Esta línea no se puede separar.');
  });

  it('without a customer only the lines a voucher already pays are listed', async () => {
    const s = await setup([previewLine('l1'), previewLine('l2', { paid_by_voucher: true, voucher_name: 'Bono', voucher_remaining: 2, line_total: 0 })], null);
    expect(s.find('voucher-line-l1').exists()).toBe(false);
    expect(s.find('voucher-line-l2').exists()).toBe(true);
  });
});
