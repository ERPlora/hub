// `useSheetList`: the lists of a group's sheet (its options, what it applies to):
// the first 20 live, «Load more» 20 more each time, past 100 in windows of 100 (the server's cap), with
// «Showing {shown} of {total}» while there are more.
import { describe, expect, it } from 'vitest';
import { defineComponent, h } from 'vue';

import type { OptionOut } from '../operations';
import { flush, mountModifier, page } from '../__tests__/mount-modifier';
import { useSheetList } from './useSheetList';

const OP = 'modifier.option.list';
const row = (id: string) => ({ id }) as OptionOut;

async function setup() {
  const exposed: { list?: ReturnType<typeof useSheetList<'modifier.option.list'>> } = {};
  const Host = defineComponent({
    setup() {
      exposed.list = useSheetList(OP, () => ({ group_id: 'g1' }));
      return () => h('p', exposed.list!.rows.value.map((r) => r.id).join(','));
    },
  });
  const m = await mountModifier(Host);
  await m.live();
  return { ...m, list: exposed.list! };
}

describe('useSheetList', () => {
  it('follows the first 20 and says whether there are more', async () => {
    const s = await setup();
    expect(s.params(OP)).toEqual([{ group_id: 'g1', limit: 20, offset: 0 }]);
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
      { group_id: 'g1', limit: 100, offset: 0 },
      { group_id: 'g1', limit: 20, offset: 100 },
    ]);
  });

  it('has no more once everything is shown', async () => {
    const s = await setup();
    await s.result(OP, page([row('a')], 1, 20));
    expect(s.list.hasMore.value).toBe(false);
  });
});
