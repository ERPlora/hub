// «Split check» (TABLE-F17): the lines of the table's check in Sales, read live, each with a checkbox; the
// ones marked go to the new check («Split»), none marked = a blank one. While they load, «Loading…»; a
// check with no lines says so.
import { describe, expect, it } from 'vitest';

import { click, ionChecked, mountTable, settle } from '../__tests__/mount-table';
import SplitLines from './SplitLines.vue';

const OP = 'sale.order.get';
const ORDER = {
  id: 'o1',
  lines: [
    { id: 'l1', name: 'Coffee', quantity: '2', line_total: 300 },
    { id: 'l2', name: 'Steak', quantity: '1', line_total: 1800 },
  ],
};

async function setup(marked: string[] = []) {
  const m = await mountTable(SplitLines, { props: { orderId: 'o1', marked } });
  await m.live();
  const el = (name: string) => m.wrapper.find(`[data-testid="table-sheet-${name}"]`);
  return { ...m, el };
}

describe('SplitLines', () => {
  it('reads the check’s lines live and says so while they load', async () => {
    const s = await setup();
    expect(s.params(OP)).toEqual([{ order_id: 'o1' }]);
    expect(s.el('split-loading').text()).toContain('Loading…');
    await s.result(OP, ORDER);
    expect(s.el('split-line-l1').text()).toBe('2 × Coffee · €3.00');
    expect(s.el('split-line-l2').text()).toBe('1 × Steak · €18.00');
  });

  it('marks a line, splits, and goes back', async () => {
    const s = await setup(['l2']);
    await s.result(OP, ORDER);
    expect((s.el('split-line-l2').element as HTMLElement & { checked?: boolean }).checked).toBe(true);
    await ionChecked(s.el('split-line-l1').element, true);
    await click(s.el('split-confirm').element);
    await click(s.el('split-back').element);
    expect(s.wrapper.emitted('toggle')).toEqual([['l1']]);
    expect(s.wrapper.emitted('confirm')).toHaveLength(1);
    expect(s.wrapper.emitted('back')).toHaveLength(1);
  });

  it('a tap marks a line once: the checkbox’s change counts, not its clicks', async () => {
    // In the browser one tap on an ion-checkbox reaches its host as a click from the label and another from the
    // box; counting clicks marked and unmarked the line at once, and the new check was born empty (e2e F17).
    const s = await setup();
    await s.result(OP, ORDER);
    const box = s.el('split-line-l1').element;
    await click(box);
    await click(box);
    await ionChecked(box, true);
    expect(s.wrapper.emitted('toggle')).toEqual([['l1']]);
  });

  it('says each quantity as the till does: no trailing decimals, the reader’s separator, a weight with its unit', async () => {
    // Sales sends quantities with three decimals («1.000»): raw, a Spanish reader read «1.000 ×» as a thousand.
    const m = await mountTable(SplitLines, { props: { orderId: 'o1', marked: [] }, locale: 'es' });
    await m.live();
    await m.result(OP, {
      id: 'o1',
      lines: [
        { id: 'l1', name: 'Café', quantity: '1.000', unit: 'ud', line_total: 150 },
        { id: 'l2', name: 'Queso', quantity: '0.532', unit: 'kg', line_total: 1064 },
      ],
    });
    const text = (id: string) => m.wrapper.find(`[data-testid="table-sheet-split-line-${id}"]`).text().replace(/\s+/g, ' ');
    expect(text('l1')).toBe('1 × Café · 1,50 €');
    expect(text('l2')).toBe('0,532 kg × Queso · 10,64 €');
  });

  it('a check with no lines yet says so', async () => {
    const s = await setup();
    await s.result(OP, { id: 'o1', lines: [] });
    await settle();
    expect(s.el('split-empty').text()).toBe('This check has no lines yet.');
  });
});
