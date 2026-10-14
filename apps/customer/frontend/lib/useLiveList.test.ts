// A live list bigger than what one query takes (`limit` ≤ 100): one live query per window of
// `useListState`, merged into one page for the DataTable. Every row on screen stays live and no
// query ever asks for more than 100 rows (a phone that pressed «Load more» three times).
import { describe, expect, it } from 'vitest';
import { defineComponent, h } from 'vue';

import { customerRow } from '../__tests__/fixtures';
import { BYE, errorFrame, flush, mountCustomer, subId } from '../__tests__/mount-customer';
import { useListState } from './useListState';
import { useLiveList } from './useLiveList';

const LIST = 'customer.customer.list';
const rows = (from: number, n: number) => Array.from({ length: n }, (_, i) => customerRow(`c${from + i}`, `C${from + i}`));

async function setup() {
  let api!: { list: ReturnType<typeof useListState>; live: ReturnType<typeof useLiveList<'customer.customer.list'>> };
  const Probe = defineComponent({
    setup() {
      const list = useListState({ sort: 'name' });
      const live = useLiveList(LIST, () => ({ ...list.base.value, lifecycle_stage: 'vip' as const }), list.windows);
      api = { list, live };
      return () => h('div');
    },
  });
  const m = await mountCustomer(Probe);
  const call = await m.live();
  const page = (params: unknown, data: unknown) => m.result(m.net.lastStream(), LIST, data, 1, params);
  return { ...m, call, api: () => api, page };
}

describe('useLiveList', () => {
  it('one window: one query with the base, its limit and offset; its result as is', async () => {
    const s = await setup();
    expect(s.params(LIST)).toEqual([{ sort: 'name', descending: false, lifecycle_stage: 'vip', limit: 50, offset: 0 }]);
    const data = { rows: rows(0, 2), total: 2, limit: 50, offset: 0 };
    await s.result(s.call, LIST, data);
    expect(s.api().live.data.value).toEqual(data);
    expect(s.api().live.status.value).toBe('live');
  });

  it('«Load more» beyond 100 rows: one query per window of ≤ 100, merged in order', async () => {
    const s = await setup();
    await s.result(s.call, LIST, { rows: rows(0, 50), total: 250, limit: 50, offset: 0 });
    s.api().list.loadMore();
    s.api().list.loadMore();
    s.api().list.loadMore();
    await flush();
    const params = s.params(LIST) as { limit: number; offset: number }[];
    expect(params.map((p) => [p.limit, p.offset]).sort((a, b) => a[1] - b[1])).toEqual([
      [100, 0],
      [100, 100],
    ]);
    for (const p of params) expect(p.limit).toBeLessThanOrEqual(100);
    await s.clock.advance(150);
    const base = { sort: 'name', descending: false, lifecycle_stage: 'vip' };
    await s.page({ ...base, limit: 100, offset: 0 }, { rows: rows(0, 100), total: 250, limit: 100, offset: 0 });
    expect(s.api().live.data.value?.rows).toHaveLength(100);
    await s.page({ ...base, limit: 100, offset: 100 }, { rows: rows(100, 100), total: 250, limit: 100, offset: 100 });
    expect(s.api().live.data.value).toMatchObject({ total: 250, offset: 0, limit: 200 });
    expect(s.api().live.data.value?.rows.map((r) => r.id).slice(98, 102)).toEqual(['c98', 'c99', 'c100', 'c101']);
  });

  it('back to one page drops the extra queries', async () => {
    const s = await setup();
    s.api().list.loadMore();
    s.api().list.loadMore();
    await flush();
    expect(s.params(LIST)).toHaveLength(2);
    s.api().list.goToPage(0);
    await flush();
    await s.clock.advance(2500);
    expect(s.params(LIST)).toEqual([{ sort: 'name', descending: false, lifecycle_stage: 'vip', limit: 50, offset: 0 }]);
  });

  it('an error of any window is the list\'s error; reconnecting too', async () => {
    const s = await setup();
    s.call.push(errorFrame(subId(s.client, LIST), 'boom'));
    await flush();
    expect([s.api().live.status.value, s.api().live.error.value?.code]).toEqual(['error', 'boom']);
    s.call.push(BYE);
    await flush();
    expect(s.api().live.status.value).toBe('reconnecting');
  });
});
