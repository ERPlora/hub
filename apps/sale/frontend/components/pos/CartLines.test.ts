// The lines of the check (WORKBOOK «Vender»): «Tap a product to add it.» while empty; a flat list;
// two boxes, «Unsent» and «Sent», once the kitchen has some (SALE-F20). Lines can be marked only when
// there are two or more (SALE-F22). Every action of a line goes up with its line.
import { describe, expect, it } from 'vitest';
import { h } from 'vue';

import { mountSale } from '../../__tests__/mount-sale';
import { line } from './__tests__/fixtures';
import CartLine from './CartLine.vue';
import CartLines from './CartLines.vue';

const A = line({ id: 'a', name: 'Coffee' });
const B = line({ id: 'b', name: 'Tea', staff_id: 's1' });
const SENT = line({ id: 'c', name: 'Soup', fired_at: '2026-10-14T10:00:00Z', round_no: 1 });

async function setup(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  return mountSale(CartLines, {
    props: { lines: [A, B], marks: [], staffNames: { s1: 'Marta' }, allowDiscounts: true, busy: false, ...props },
    locale,
  });
}

describe('CartLines', () => {
  it('an empty check says how to start', async () => {
    const m = await setup({ lines: [] }, 'es');
    expect(m.find('pos-cart-empty').text()).toBe('Toca un producto para añadirlo.');
  });

  it('paints one line per row, in order, each with its professional’s name and its mark', async () => {
    const m = await setup({ marks: ['b'] });
    const rows = m.wrapper.findAllComponents(CartLine);
    expect(rows.map((r) => r.props('line').id)).toEqual(['a', 'b']);
    expect(rows.map((r) => [r.props('markable'), r.props('marked'), r.props('staffName')])).toEqual([
      [true, false, null],
      [true, true, 'Marta'],
    ]);
    expect(m.find('pos-cart-sections').exists()).toBe(false);
  });

  it('a lone line cannot be marked', async () => {
    const m = await setup({ lines: [A] });
    expect(m.wrapper.findComponent(CartLine).props('markable')).toBe(false);
  });

  it('with lines in the kitchen, «Unsent» on top and «Sent» below, each with its count', async () => {
    const m = await setup({ lines: [A, SENT, B] }, 'es');
    const pending = m.find('pos-cart-pending');
    const sent = m.find('pos-cart-sent');
    expect(pending.find('.pos-sec__h').text()).toBe('Pendiente de enviar · 2');
    expect(sent.find('.pos-sec__h').text()).toBe('Enviado · 1');
    const ids = (section: typeof pending) => section.findAll('.pos-line').map((row) => row.attributes('data-testid'));
    expect(ids(pending)).toEqual(['pos-line-a', 'pos-line-b']);
    expect(ids(sent)).toEqual(['pos-line-c']);
  });

  it('the «Sent» head carries what the cart puts beside it (Kitchen’s «Tickets · N», KITCHEN-F19)', async () => {
    const m = await mountSale(
      { setup: () => () => h(CartLines, { lines: [A, SENT], marks: [], staffNames: {}, allowDiscounts: true, busy: false }, { sent: () => h('button', { 'data-testid': 'slot-sent' }, 'Tickets · 1') }) },
      {},
    );
    expect(m.find('pos-cart-sent').find('.pos-sec__head [data-testid=slot-sent]').exists()).toBe(true);
    expect(m.find('pos-cart-pending').find('[data-testid=slot-sent]').exists()).toBe(false);
  });

  it('hands every action up with its line', async () => {
    const m = await setup();
    const second = m.wrapper.findAllComponents(CartLine)[1];
    second.vm.$emit('mark');
    second.vm.$emit('quantity', '3');
    second.vm.$emit('discount');
    second.vm.$emit('note');
    second.vm.$emit('gift');
    second.vm.$emit('staff');
    second.vm.$emit('void');
    expect(m.wrapper.emitted('mark')).toEqual([[B]]);
    expect(m.wrapper.emitted('quantity')).toEqual([[B, '3']]);
    for (const action of ['discount', 'note', 'gift', 'staff', 'void']) expect(m.wrapper.emitted(action)).toEqual([[B]]);
  });
});
