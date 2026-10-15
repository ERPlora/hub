// A line of the check (WORKBOOK «Vender»): name, price per unit, discount mark or «Gift», note and
// professional underneath; the discount, note and gift buttons and the quantity selector. A line sent
// to the kitchen only shows its quantity, «Order N» and ⊗ «Void this item». Tapping the line (not its
// buttons) marks it for a partial charge (SALE-F22). The amount is the server's `line_total`.
import { describe, expect, it } from 'vitest';

import { click, mountSale } from '../../__tests__/mount-sale';
import { plain } from '../../lib/format';
import { line } from './__tests__/fixtures';
import CartLine from './CartLine.vue';
import QtyStepper from './QtyStepper.vue';

async function setup(over: Parameters<typeof line>[0] = {}, props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  return mountSale(CartLine, {
    props: { line: line(over), markable: true, marked: false, staffName: null, allowDiscounts: true, ...props },
    locale,
  });
}

describe('CartLine: what it shows', () => {
  it('the name, the price per unit and the server’s amount for the line', async () => {
    const m = await setup({ quantity: '2.000', line_total: 300 }, {}, 'es');
    const row = m.find('pos-line-l1');
    expect(row.attributes('data-product-id')).toBe('p1');
    expect(row.find('h3').text()).toBe('Café con leche');
    expect(plain(row.find('.pos-line__price').text())).toBe('1,50 €');
    expect(plain(row.find('.pos-line__amount').text())).toBe('3,00 €');
    expect(m.wrapper.findComponent(QtyStepper).props()).toMatchObject({ quantity: '2.000', unit: 'ud' });
  });

  it('a price by weight says its unit', async () => {
    const m = await setup({ unit: 'kg', pricing_unit: 'kg', unit_price: 1200 }, {}, 'es');
    expect(plain(m.find('pos-line-l1').find('.pos-line__price').text())).toBe('12,00 € / kg');
  });

  it('marks a discount, a gift (with its reason, struck amount), the note and the professional', async () => {
    const m = await setup(
      { discount_percent: '10.00', is_gift: true, gift_reason: 'Birthday', notes: 'No ice', staff_id: 's1' },
      { staffName: 'Marta' },
      'es',
    );
    const row = m.find('pos-line-l1');
    expect(row.find('.pos-line__gift').text()).toBe('Invitación');
    expect(row.find('.pos-line__meta').text()).toContain('Birthday');
    expect(plain(row.find('.pos-line__discount').text())).toBe('−10 %');
    expect(row.find('.pos-line__amount').classes()).toContain('pos-line__amount--gift');
    expect(row.find('.pos-line__note').text()).toBe('No ice');
    const staff = m.find('pos-line-l1-staff');
    expect(staff.text()).toBe('Marta');
    expect(staff.attributes('title')).toBe('De quién es esta línea');
  });

  it('a professional whose name is not known yet is «the assigned professional»', async () => {
    const m = await setup({ staff_id: 's9' });
    expect(m.find('pos-line-l1-staff').text()).toBe('the assigned professional');
  });

  it('no professional line when the line has none (it goes with the check’s)', async () => {
    const m = await setup();
    expect(m.find('pos-line-l1-staff').exists()).toBe(false);
  });
});

describe('CartLine: actions', () => {
  it('discount, note, gift, professional and quantity are asked up', async () => {
    const m = await setup({ staff_id: 's1' });
    await click(m.find('pos-line-l1-discount').element);
    await click(m.find('pos-line-l1-note').element);
    await click(m.find('pos-line-l1-gift').element);
    await click(m.find('pos-line-l1-staff').element);
    m.wrapper.findComponent(QtyStepper).vm.$emit('change', '3');
    expect(Object.keys(m.wrapper.emitted())).toEqual(expect.arrayContaining(['discount', 'note', 'gift', 'staff', 'quantity']));
    expect(m.wrapper.emitted('quantity')).toEqual([['3']]);
    expect(m.wrapper.emitted('mark')).toBeUndefined();
    expect(m.find('pos-line-l1-discount').attributes('title')).toBe('Line discount');
    expect(m.find('pos-line-l1-note').attributes('title')).toBe('Note');
    expect(m.find('pos-line-l1-gift').attributes('title')).toBe('Comp / un-comp line');
  });

  it('no discount button when the business does not allow discounts', async () => {
    const m = await setup({}, { allowDiscounts: false });
    expect(m.find('pos-line-l1-discount').exists()).toBe(false);
  });

  it('tapping the line marks it; its circle says so', async () => {
    const m = await setup();
    await click(m.find('pos-line-l1').element);
    expect(m.wrapper.emitted('mark')).toHaveLength(1);
    const marked = await setup({}, { marked: true });
    expect(marked.find('pos-line-l1').classes()).toContain('pos-line--marked');
    expect(marked.find('pos-line-l1-mark').attributes('aria-pressed')).toBe('true');
  });

  it('a lone line is not markable: no circle, the tap does nothing', async () => {
    const m = await setup({}, { markable: false });
    expect(m.find('pos-line-l1-mark').exists()).toBe(false);
    await click(m.find('pos-line-l1').element);
    expect(m.wrapper.emitted('mark')).toBeUndefined();
  });
});

describe('CartLine: sent to the kitchen', () => {
  it('only shows «Order N», ×quantity and ⊗ «Void this item»; nothing else can change', async () => {
    const m = await setup({ fired_at: '2026-10-14T10:00:00Z', round_no: 2, quantity: '3.000', staff_id: 's1' }, {}, 'es');
    const row = m.find('pos-line-l1');
    expect(row.find('.pos-line__round').text()).toBe('Comanda 2');
    expect(row.find('.pos-line__qty').text()).toBe('×3');
    expect(m.wrapper.findComponent(QtyStepper).exists()).toBe(false);
    for (const id of ['discount', 'note', 'gift']) expect(m.find(`pos-line-l1-${id}`).exists()).toBe(false);
    expect(m.find('pos-line-l1-staff').attributes('disabled')).toBeDefined();
    const voiding = m.find('pos-line-l1-void');
    expect(voiding.attributes('aria-label')).toBe('Anular este artículo');
    await click(voiding.element);
    expect(m.wrapper.emitted('void')).toHaveLength(1);
  });
});

describe('CartLine: a line a voucher pays (SALE-F27)', () => {
  const covered = { service_id: 's1', is_service: true, paid_by_voucher: true, voucher_session_id: 'r1', voucher_name: 'Bono 5 cortes', line_total: 0 };

  it('says it is already paid with the voucher, at 0, and only lets the note change or the line go', async () => {
    const m = await setup(covered, {}, 'es');
    const row = m.find('pos-line-l1');
    expect(m.find('pos-line-l1-voucher').text()).toBe('Ya pagado · Bono 5 cortes');
    expect(plain(row.find('.pos-line__amount').text())).toBe('0,00 €');
    expect(m.find('pos-line-l1-discount').exists()).toBe(false);
    expect(m.find('pos-line-l1-gift').exists()).toBe(false);
    expect(m.wrapper.findComponent(QtyStepper).exists()).toBe(false);
    expect(m.find('pos-line-l1-note').exists()).toBe(true);
    await click(m.find('pos-line-l1-remove').element);
    expect(m.wrapper.emitted('quantity')).toEqual([['0']]);
  });

  it('a line no voucher pays keeps its buttons', async () => {
    const m = await setup({ service_id: 's1', is_service: true });
    expect(m.find('pos-line-l1-voucher').exists()).toBe(false);
    expect(m.find('pos-line-l1-remove').exists()).toBe(false);
    expect(m.wrapper.findComponent(QtyStepper).exists()).toBe(true);
  });
});
