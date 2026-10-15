// `useSheetList`: the list of a voucher's sheet (Sold vouchers, Movements, Vouchers with no customer):
// the first 20 live, «Load more» 20 more each time, past 100 in windows of 100 (the server's cap), with
// «Showing {shown} of {total}» while there are more.
import { describe, expect, it } from 'vitest';
import { defineComponent, h } from 'vue';

import type { GrantOut } from '../operations';
import { flush, mountService, page } from '../__tests__/mount-service';
import { useSheetList } from './useSheetList';

const OP = 'service.grant.list';
const row = (id: string) => ({ id }) as GrantOut;

async function setup() {
  const exposed: { list?: ReturnType<typeof useSheetList<'service.grant.list'>> } = {};
  const Host = defineComponent({
    setup() {
      exposed.list = useSheetList(OP, () => ({ package_id: 'p1' }));
      return () => h('p', exposed.list!.rows.value.map((r) => r.id).join(','));
    },
  });
  const m = await mountService(Host);
  await m.live();
  return { ...m, list: exposed.list! };
}

describe('useSheetList', () => {
  it('follows the first 20 and says whether there are more', async () => {
    const s = await setup();
    expect(s.params(OP)).toEqual([{ package_id: 'p1', limit: 20, offset: 0 }]);
    await s.result(OP, page([row('a'), row('b')], 45, 20));
    expect([s.list.rows.value.map((r) => r.id), s.list.total.value, s.list.hasMore.value]).toEqual([['a', 'b'], 45, true]);
  });

  it('«Load more» grows by 20, and past 100 in windows of 100', async () => {
    const s = await setup();
    await s.result(OP, page([row('a')], 300, 20));
    for (let i = 0; i < 5; i++) s.list.loadMore();
    await flush();
    await s.reopen();
    expect(s.params(OP)).toEqual([
      { package_id: 'p1', limit: 100, offset: 0 },
      { package_id: 'p1', limit: 20, offset: 100 },
    ]);
  });

  it('has no more once everything is shown', async () => {
    const s = await setup();
    await s.result(OP, page([row('a')], 1, 20));
    expect(s.list.hasMore.value).toBe(false);
  });
});
