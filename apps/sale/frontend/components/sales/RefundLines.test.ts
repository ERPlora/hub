// «What goes back» in the Refund window (SALE-F31 step 3): the sale's lines, each with a checkbox and its
// amount. Marking one says it goes back with the money (all that is left of it, to begin with); with two
// or more whole units left, «Units that go back» narrows it (1…left). A line partly returned says «<n>
// of <m> already returned»; one returned whole says «Already returned» and cannot be marked.
import { describe, expect, it } from 'vitest';

import { ionValue, mountSale } from '../../__tests__/mount-sale';
import { plain } from '../../lib/format';
import type { LineOption } from '../../operations';
import RefundLines from './RefundLines.vue';

const prop = (el: Element, name: string): unknown => (el as unknown as Record<string, unknown>)[name];

const line = (id: string, over: Partial<LineOption> = {}): LineOption => ({
  line_id: id,
  name: 'Coffee',
  unit: 'ud',
  quantity: '1.000',
  returned: '0.000',
  left: '1.000',
  line_total: 150,
  is_gift: false,
  ...over,
});

const LINES = [
  line('a', { name: 'Café' }),
  line('b', { name: 'Croissant', quantity: '3.000', returned: '1.000', left: '2.000', line_total: 600 }),
  line('c', { name: 'Zumo', returned: '1.000', left: '0.000', line_total: 300 }),
  line('d', { name: 'Queso', unit: 'kg', quantity: '0.532', left: '0.532', line_total: 950 }),
];

async function setup(picked: Record<string, number> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountSale(RefundLines, { props: { lines: LINES, picked }, locale });
  const emitted = () => (m.wrapper.emitted('update:picked') ?? []).map(([value]) => value);
  const check = (id: string) => m.find(`refund-line-check-${id}`);
  /** Ticks or unticks a box, as `ion-checkbox` does (`ionChange` with `checked`). */
  async function tick(id: string, checked: boolean) {
    check(id).element.dispatchEvent(new CustomEvent('ionChange', { detail: { checked } }));
    await m.wrapper.vm.$nextTick();
  }
  return { ...m, emitted, check, tick };
}

describe('RefundLines', () => {
  it('lists every line with its box and amount; one returned whole says so and cannot be marked', async () => {
    const s = await setup();
    expect(plain(s.find('refund-lines-title').text())).toBe('What goes back');
    expect(s.find('refund-lines-hint').text()).toBe('Mark what the customer returns and the amount is proposed for you. With nothing marked, only money goes back.');
    expect(LINES.map((l) => s.check(l.line_id).text())).toEqual(['Café', 'Croissant', 'Zumo', 'Queso']);
    expect(['a', 'b', 'd'].map((id) => plain(s.find(`refund-line-amount-${id}`).text()))).toEqual(['€1.50', '€6.00', '€9.50']);
    expect(s.find('refund-line-amount-c').text()).toBe('Already returned');
    expect(prop(s.check('c').element, 'disabled')).toBe(true);
    expect(prop(s.check('a').element, 'disabled')).toBe(false);
  });

  it('a line partly returned says how much already went back', async () => {
    const s = await setup();
    expect(s.find('refund-line-partly-b').text()).toBe('1 of 3 already returned');
    expect(s.find('refund-line-partly-a').exists()).toBe(false);
  });

  it('marking a line takes all that is left of it; unmarking drops it', async () => {
    const s = await setup({ a: 1000 });
    expect(prop(s.check('a').element, 'checked')).toBe(true);
    await s.tick('b', true);
    expect(s.emitted().at(-1)).toEqual({ a: 1000, b: 2000 });
    await s.tick('a', false);
    expect(s.emitted().at(-1)).toEqual({ b: 2000 });
  });

  it('with two or more whole units left, «Units that go back» narrows a marked line (1…left)', async () => {
    const s = await setup({ b: 2000, d: 532 });
    const units = s.find('refund-line-units-b');
    expect([prop(units.element, 'label'), prop(units.element, 'value'), prop(units.element, 'min'), prop(units.element, 'max')]).toEqual([
      'Units that go back',
      '2',
      1,
      2,
    ]);
    await ionValue(units.element, '1', 'ionInput');
    expect(s.emitted().at(-1)).toEqual({ b: 1000, d: 532 });
    await ionValue(units.element, '9', 'ionInput');
    expect(s.emitted().at(-1)).toEqual({ b: 2000, d: 532 });
    // A weighed line, or one with a single unit left, goes back whole.
    expect(s.find('refund-line-units-d').exists()).toBe(false);
    expect(s.find('refund-line-units-a').exists()).toBe(false);
  });

  it('speaks Spanish', async () => {
    const s = await setup({}, 'es');
    expect(s.find('refund-lines-title').text()).toBe('Qué se devuelve');
    expect(s.find('refund-line-partly-b').text()).toBe('1 de 3 ya devueltas');
    expect(s.find('refund-line-amount-c').text()).toBe('Ya devuelta');
    const s2 = await setup({ b: 2000 }, 'es');
    expect(prop(s2.find('refund-line-units-b').element, 'label')).toBe('Unidades que vuelven');
  });
});
