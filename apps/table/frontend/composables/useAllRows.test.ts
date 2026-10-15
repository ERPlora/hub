// `useAllRows`: every row of a live list that the screen must show whole (the floor plan: every table
// of a zone), read in windows of 100 (the server's cap) — one window first, as many as the total asks
// once it is known — joined in order, live.
import { describe, expect, it } from 'vitest';
import { defineComponent, h, ref } from 'vue';

import type { TableOut } from '../operations';
import { flush, mountTable, page } from '../__tests__/mount-table';
import { useAllRows } from './useAllRows';

const OP = 'table.table.list';
const row = (id: string) => ({ id, number: id }) as unknown as TableOut;

async function setup() {
  const zone = ref('z1');
  const exposed: { all?: ReturnType<typeof useAllRows<'table.table.list'>> } = {};
  const Host = defineComponent({
    setup() {
      exposed.all = useAllRows(OP, () => ({ zone_id: zone.value, sort: 'number' }));
      return () => h('p', exposed.all!.rows.value.map((r) => r.id).join(','));
    },
  });
  const m = await mountTable(Host);
  await m.live();
  return { ...m, zone, all: exposed.all! };
}

describe('useAllRows', () => {
  it('asks the first hundred rows, and stays on one window when they are all', async () => {
    const s = await setup();
    expect(s.params(OP)).toEqual([{ zone_id: 'z1', sort: 'number', limit: 100, offset: 0 }]);
    expect(s.all.status.value).toBe('loading');
    await s.result(OP, page([row('1'), row('2')], 2, 100, 0));
    expect(s.wrapper.text()).toBe('1,2');
    expect(s.all.status.value).toBe('live');
  });

  it('opens as many windows as the total asks and joins them in order', async () => {
    const s = await setup();
    await s.result(OP, page([row('1')], 150, 100, 0));
    await flush();
    await s.reopen();
    expect(s.params(OP)).toEqual([
      { zone_id: 'z1', sort: 'number', limit: 100, offset: 0 },
      { zone_id: 'z1', sort: 'number', limit: 100, offset: 100 },
    ]);
    await s.result(OP, page([row('1')], 150, 100, 0), { offset: 0 });
    await s.result(OP, page([row('101')], 150, 100, 100), { offset: 100 });
    expect(s.wrapper.text()).toBe('1,101');
  });

  it('starts again from one window when the query changes', async () => {
    const s = await setup();
    await s.result(OP, page([row('1')], 150, 100, 0));
    await flush();
    s.zone.value = 'z2';
    await flush();
    await s.reopen();
    await s.clock.advance(2500);
    expect(s.params(OP)).toEqual([{ zone_id: 'z2', sort: 'number', limit: 100, offset: 0 }]);
  });
});
