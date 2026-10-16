// `useLiveList`: a server-side list that may show more rows than the server gives at once (100): one
// live subscription per window of `useServerTable`, the rows of all of them in order, the count of the
// first. A desk shows one window (one subscription); a phone that pressed «Load more» past 100 rows
// follows two or more, and going back drops the extra ones.
import { describe, expect, it } from 'vitest';
import { defineComponent, h, ref } from 'vue';

import type { FlowOut } from '../operations';
import { flush, mountFlow, page } from '../__tests__/mount-flow';
import type { ListWindow } from './useServerTable';
import { useLiveList } from './useLiveList';

const OP = 'flow.flow.list';
const row = (id: string) => ({ id, name: id }) as FlowOut;

async function setup(initial: ListWindow[]) {
  const windows = ref(initial);
  const exposed: { list?: ReturnType<typeof useLiveList<'flow.flow.list'>> } = {};
  const Host = defineComponent({
    setup() {
      exposed.list = useLiveList(OP, () => ({ sort: 'name' as const }), () => windows.value);
      return () => h('p', (exposed.list!.data.value?.rows ?? []).map((r) => r.id).join(','));
    },
  });
  const m = await mountFlow(Host);
  await m.live();
  const list = exposed.list!;
  return { ...m, windows, list };
}

describe('useLiveList', () => {
  it('follows one subscription for one window, with the query and the window', async () => {
    const s = await setup([{ limit: 50, offset: 0 }]);
    expect(s.params(OP)).toEqual([{ sort: 'name', limit: 50, offset: 0 }]);
    expect(s.list.status.value).toBe('loading');
    await s.result(OP, page([row('a'), row('b')], 2));
    expect(s.list.data.value).toEqual({ rows: [row('a'), row('b')], total: 2, limit: 50, offset: 0 });
    expect(s.list.status.value).toBe('live');
  });

  it('past 100 rows follows one subscription per window and joins their rows in order', async () => {
    const s = await setup([{ limit: 100, offset: 0 }]);
    await s.result(OP, page([row('a')], 150, 100, 0));
    s.windows.value = [
      { limit: 100, offset: 0 },
      { limit: 50, offset: 100 },
    ];
    await flush();
    await s.reopen();
    expect(s.params(OP)).toEqual([
      { sort: 'name', limit: 100, offset: 0 },
      { sort: 'name', limit: 50, offset: 100 },
    ]);
    // The first window stays painted while the next one is on its way.
    expect(s.list.data.value?.rows.map((r) => r.id)).toEqual(['a']);
    await s.result(OP, page([row('a')], 150, 100, 0), { offset: 0 });
    await s.result(OP, page([row('z')], 150, 50, 100), { offset: 100 });
    expect(s.list.data.value).toEqual({ rows: [row('a'), row('z')], total: 150, limit: 150, offset: 0 });
    expect(s.wrapper.text()).toBe('a,z');
  });

  it('keeps what the first page says besides its rows (how many runs failed)', async () => {
    const s = await setup([{ limit: 20, offset: 0 }]);
    await s.result(OP, { ...page([row('a')], 1, 20, 0), failed: 2 });
    expect(s.list.data.value).toEqual({ rows: [row('a')], total: 1, limit: 20, offset: 0, failed: 2 });
  });

  it('going back to one window drops the extra subscriptions', async () => {
    const s = await setup([
      { limit: 100, offset: 0 },
      { limit: 100, offset: 100 },
    ]);
    expect(s.params(OP)).toHaveLength(2);
    s.windows.value = [{ limit: 50, offset: 0 }];
    await flush();
    await s.clock.advance(2500);
    expect(s.params(OP)).toEqual([{ sort: 'name', limit: 50, offset: 0 }]);
  });
});
