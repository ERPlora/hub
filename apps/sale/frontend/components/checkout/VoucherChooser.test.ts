// «Pay this line with a voucher» (SALE-F27, SERVICE-F22): the customer's vouchers that cover the line's
// service (`service.grant.tender_options`, live), the one spent first already chosen with why, how many
// sessions are left before and after, its expiry; «Spend one session» pays the line with the chosen one
// (`sale.order.apply_voucher`). Never «no vouchers» when the read failed; a refusal is read here.
import { describe, expect, it } from 'vitest';

import { click, errorFrame, flush, mountSale } from '../../__tests__/mount-sale';
import { option } from './__tests__/vouchers';
import VoucherChooser from './VoucherChooser.vue';

const OP = 'service.grant.tender_options';
const PROPS = { orderId: 'o1', lineId: 'l1', serviceId: 'sv1', customerId: 'c1' };
const page = (rows: unknown[]) => ({ rows, total: rows.length, limit: 20, offset: 0 });

async function setup(locale: 'en' | 'es' = 'es') {
  const m = await mountSale(VoucherChooser, { props: PROPS, locale });
  await m.live();
  const text = (testid: string) => (m.find(testid).exists() ? m.find(testid).text().replace(/\s+/g, ' ').trim() : '');
  return { ...m, text };
}

const TWO = [
  option('g1', { package_name: 'Bono 5 cortes', remaining_before: 3, remaining_after: 2, expires_at: '2026-11-14T10:00:00Z', is_default: true, default_reason: 'expires_first', candidate_count: 2 }),
  option('g2', { package_name: 'Bono ilimitado', max_uses: null, remaining_before: null, remaining_after: null, is_unlimited: true, candidate_count: 2 }),
];

describe('VoucherChooser', () => {
  it('asks Services for the customer’s vouchers that cover the line’s service, and waits with a skeleton', async () => {
    const s = await setup();
    expect(s.params(OP)).toEqual([{ customer_id: 'c1', service_id: 'sv1', limit: 20, offset: 0 }]);
    expect(s.find('voucher-l1-loading').exists()).toBe(true);
  });

  it('paints each voucher with what is left, its expiry and why the chosen one goes first', async () => {
    const s = await setup();
    await s.result(OP, page(TWO));
    expect(s.text('voucher-l1-title')).toBe('Pagar esta línea con un bono');
    expect(s.text('voucher-l1-candidates')).toBe('2 bonos válidos');
    expect(s.text('voucher-l1-option-g1')).toContain('Bono 5 cortes');
    expect(s.text('voucher-l1-option-g1')).toContain('Quedan 3 sesiones · 2 después de esta');
    expect(s.text('voucher-l1-option-g1')).toContain('Caduca el 14/11/2026');
    expect(s.text('voucher-l1-option-g1')).toContain('Se gasta primero porque es el que antes caduca.');
    expect(s.find('voucher-l1-option-g1').attributes('aria-checked')).toBe('true');
    expect(s.text('voucher-l1-option-g2')).toContain('Sesiones ilimitadas');
    expect(s.find('voucher-l1-option-g2').attributes('aria-checked')).toBe('false');
  });

  it('«Spend one session» pays the line with the chosen voucher; another one can be chosen first', async () => {
    const s = await setup();
    await s.result(OP, page(TWO));
    await click(s.find('voucher-l1-option-g2').element);
    expect(s.find('voucher-l1-option-g2').attributes('aria-checked')).toBe('true');
    s.answer(200, {});
    await click(s.find('voucher-l1-confirm').element);
    expect(s.sent().at(-1)).toMatchObject({
      method: 'POST',
      path: '/api/sale/orders/apply_voucher',
      body: { order_id: 'o1', line_id: 'l1', grant_id: 'g2' },
    });
  });

  it('a single voucher is the only option', async () => {
    const s = await setup('en');
    await s.result(OP, page([option('g1', { is_default: true, default_reason: 'only_option' })]));
    expect(s.find('voucher-l1-candidates').exists()).toBe(false);
    expect(s.text('voucher-l1-option-g1')).toContain('It is the only voucher that covers this service.');
    expect(s.text('voucher-l1-confirm')).toBe('Spend one session');
  });

  it('no voucher that covers it says so', async () => {
    const s = await setup();
    await s.result(OP, page([]));
    expect(s.text('voucher-l1-none')).toBe('Este cliente no tiene ningún bono que cubra este servicio.');
    expect(s.find('voucher-l1-confirm').exists()).toBe(false);
  });

  it('a read that fails never says «no vouchers»: it says so with «Retry»', async () => {
    const s = await setup();
    s.net.lastStream().push(errorFrame(s.subId(OP), 'internal_error'));
    await flush();
    expect(s.text('voucher-l1-load-error')).toContain('No se han podido cargar los bonos del cliente.');
    expect(s.find('voucher-l1-none').exists()).toBe(false);
    const streams = s.net.streams.length;
    await click(s.find('voucher-l1-retry').element);
    await s.reopen();
    expect(s.net.streams.length).toBeGreaterThan(streams);
  });

  it('a refusal (the last session went at another till) is read in the slot, in the server’s words', async () => {
    const s = await setup();
    await s.result(OP, page(TWO));
    s.answer(409, { error: { code: 'service.grant_no_uses_left', message: 'Este bono ya no tiene sesiones disponibles.' } });
    await click(s.find('voucher-l1-confirm').element);
    expect(s.text('voucher-l1-error')).toBe('Este bono ya no tiene sesiones disponibles.');
  });
});
