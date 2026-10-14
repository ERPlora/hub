// `useLiveList`: the Sales list followed live in WINDOWS of at most 100 rows (the server's cap on
// `limit`), each its own subscription, merged into one page for the DataTable: the rows in order, the
// query's total, «loading» until every window answered, the first error. Fewer windows release the
// subscriptions left over.
import { describe, expect, it } from 'vitest';
import { defineComponent, h, type PropType } from 'vue';

import { errorFrame, flush, mountSale } from '../../__tests__/mount-sale';
import type { SaleRow } from '../../operations';
import { useLiveList } from './useLiveList';
import type { ListWindow } from './useServerTable';

const OP = 'sale.sale.list';

const sale = (n: number): SaleRow => ({
  id: `s${n}`,
  number: `20261014-${String(n).padStart(4, '0')}`,
  business_day: '2026-10-14',
  created_at: '2026-10-14T10:00:00Z',
  status: 'completed',
  document_type: 'ticket',
  customer_id: null,
  customer_name: '',
  payment_method_name: 'Cash',
  staff_id: null,
  total: 1000,
  tax_total: 174,
  refunded_total: 0,
  refundable_total: 1000,
});
const rows = (from: number, count: number) => Array.from({ length: count }, (_, i) => sale(from + i));

let captured: ReturnType<typeof useLiveList<typeof OP>> | undefined;

const Host = defineComponent({
  props: { windows: { type: Array as PropType<ListWindow[]>, required: true } },
  setup(props) {
    captured = useLiveList(OP, () => ({ sort: 'created_at' as const, dir: 'desc' as const }), () => props.windows);
    return () => h('div');
  },
});

async function setup(windows: ListWindow[]) {
  const m = await mountSale(Host, { props: { windows } });
  await m.live();
  return { ...m, list: captured! };
}

describe('useLiveList', () => {
  it('one window is one subscription, and its page is the list', async () => {
    const s = await setup([{ limit: 50, offset: 0 }]);
    expect(s.params(OP)).toEqual([{ sort: 'created_at', dir: 'desc', limit: 50, offset: 0 }]);
    expect(s.list.status.value).toBe('loading');
    await s.result(OP, { rows: rows(0, 2), total: 2, limit: 50, offset: 0 });
    expect(s.list.status.value).toBe('live');
    expect(s.list.data.value).toEqual({ rows: rows(0, 2), total: 2, limit: 50, offset: 0 });
  });

  it('several windows: one subscription each, merged in order once all answered', async () => {
    const s = await setup([
      { limit: 100, offset: 0 },
      { limit: 50, offset: 100 },
    ]);
    expect(s.params(OP).map((p) => [p.limit, p.offset])).toEqual([
      [100, 0],
      [50, 100],
    ]);
    await s.result(OP, { rows: rows(0, 100), total: 180, limit: 100, offset: 0 }, { offset: 0 });
    expect(s.list.status.value).toBe('loading');
    await s.result(OP, { rows: rows(100, 50), total: 180, limit: 50, offset: 100 }, { offset: 100 });
    expect(s.list.status.value).toBe('live');
    expect(s.list.data.value?.rows.map((r) => r.id)).toEqual(rows(0, 150).map((r) => r.id));
    expect(s.list.data.value).toMatchObject({ total: 180, limit: 150, offset: 0 });
  });

  it('fewer windows release the subscriptions left over', async () => {
    const s = await setup([
      { limit: 100, offset: 0 },
      { limit: 50, offset: 100 },
    ]);
    await s.wrapper.setProps({ windows: [{ limit: 50, offset: 0 }] });
    await s.clock.advance(2000);
    await flush();
    expect(s.params(OP)).toEqual([{ sort: 'created_at', dir: 'desc', limit: 50, offset: 0 }]);
  });

  it('an error of any window is the list’s', async () => {
    const s = await setup([{ limit: 50, offset: 0 }]);
    s.net.lastStream().push(errorFrame(s.subId(OP), 'sale.boom'));
    await flush();
    expect(s.list.status.value).toBe('error');
    expect(s.list.error.value?.code).toBe('sale.boom');
  });
});
