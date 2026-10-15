// «Split check» (TABLE-F17): the lines of the table's check in Sales, read live, each with a checkbox; the
// ones marked go to the new check («Split»), none marked = a blank one. While they load, «Loading…»; a
// check with no lines says so.
import { describe, expect, it } from 'vitest';

import { click, mountTable, settle } from '../__tests__/mount-table';
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
    await click(s.el('split-line-l1').element);
    await click(s.el('split-confirm').element);
    await click(s.el('split-back').element);
    expect(s.wrapper.emitted('toggle')).toEqual([['l1']]);
    expect(s.wrapper.emitted('confirm')).toHaveLength(1);
    expect(s.wrapper.emitted('back')).toHaveLength(1);
  });

  it('a check with no lines yet says so', async () => {
    const s = await setup();
    await s.result(OP, { id: 'o1', lines: [] });
    await settle();
    expect(s.el('split-empty').text()).toBe('This check has no lines yet.');
  });
});
