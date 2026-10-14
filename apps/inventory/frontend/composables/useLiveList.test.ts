// A server-side list followed live as one page, whatever its window: each window of at most 100 rows
// (useServerTable) is its own `useLive` subscription, and their rows are joined in order. A phone's
// «Load more» past 100 rows adds a subscription instead of asking for more than the API serves;
// going back to one page drops the extra ones. Status and error are the list's: loading while any
// window has no result, the first error otherwise.
import { describe, expect, it } from 'vitest';
import { defineComponent, h, ref } from 'vue';

import { errorFrame, flush, mountInventory, page } from '../__tests__/mount-inventory';
import { useLiveList } from './useLiveList';
import type { RowWindow } from './useServerTable';

const row = (n: number) => ({ id: `m${n}` });

async function setup(initial: RowWindow[]) {
  const windows = ref(initial);
  const filters = ref<{ search?: string }>({});
  let list: ReturnType<typeof useLiveList<'inventory.movement.list'>> | undefined;
  const Probe = defineComponent({
    setup() {
      list = useLiveList('inventory.movement.list', () => ({ ...filters.value, sort: '-created_at' as const }), windows);
      return () => h('div');
    },
  });
  const m = await mountInventory(Probe);
  const call = await m.live();
  /** Results for the i-th subscription of the list. */
  async function push(index: number, data: unknown, stream = call) {
    stream.push(`event: result\ndata: ${JSON.stringify({ id: m.client.stream.subscriptions('inventory.movement.list')[index].id, data, rev: 1 })}\n\n`);
    await flush();
  }
  return { ...m, call, windows, filters, list: () => list!, push };
}

describe('useLiveList', () => {
  it('one window is one subscription, its page as it comes', async () => {
    const s = await setup([{ limit: 50, offset: 0 }]);
    expect(s.params('inventory.movement.list')).toEqual([{ sort: '-created_at', limit: 50, offset: 0 }]);
    expect(s.list().status.value).toBe('loading');
    await s.push(0, page([row(1), row(2)], 2));
    expect(s.list().data.value).toEqual(page([row(1), row(2)], 2));
    expect(s.list().status.value).toBe('live');
  });

  it('a window past 100 rows adds a subscription and joins its rows after the first ones', async () => {
    const s = await setup([{ limit: 100, offset: 0 }]);
    await s.push(0, page(Array.from({ length: 100 }, (_, i) => row(i)), 130, 100, 0));
    s.windows.value = [
      { limit: 100, offset: 0 },
      { limit: 50, offset: 100 },
    ];
    await flush();
    await s.clock.advance(150);
    expect(s.params('inventory.movement.list')).toEqual([
      { sort: '-created_at', limit: 100, offset: 0 },
      { sort: '-created_at', limit: 50, offset: 100 },
    ]);
    expect(s.list().status.value).toBe('loading');
    const stream = s.net.lastStream();
    stream.push('event: hello\ndata: {}\n\n');
    await s.push(0, page(Array.from({ length: 100 }, (_, i) => row(i)), 130, 100, 0), stream);
    await s.push(1, page(Array.from({ length: 30 }, (_, i) => row(100 + i)), 130, 50, 100), stream);
    const data = s.list().data.value!;
    expect([data.rows.length, data.total, data.offset, data.rows[100]]).toEqual([130, 130, 0, row(100)]);
    expect(s.list().status.value).toBe('live');
  });

  it('back to one window drops the extra subscription', async () => {
    const s = await setup([
      { limit: 100, offset: 0 },
      { limit: 100, offset: 100 },
    ]);
    expect(s.client.stream.subscriptions('inventory.movement.list')).toHaveLength(2);
    s.windows.value = [{ limit: 50, offset: 0 }];
    await flush();
    await s.clock.advance(3000);
    expect(s.params('inventory.movement.list')).toEqual([{ sort: '-created_at', limit: 50, offset: 0 }]);
  });

  it('the filters reach every window', async () => {
    const s = await setup([
      { limit: 100, offset: 0 },
      { limit: 10, offset: 100 },
    ]);
    s.filters.value = { search: 'caf' };
    await flush();
    expect(s.params('inventory.movement.list')).toEqual([
      { search: 'caf', sort: '-created_at', limit: 100, offset: 0 },
      { search: 'caf', sort: '-created_at', limit: 10, offset: 100 },
    ]);
  });

  it('an error in a window is the list error', async () => {
    const s = await setup([{ limit: 50, offset: 0 }]);
    s.call.push(errorFrame(s.client.stream.subscriptions('inventory.movement.list')[0].id, 'app_inactive'));
    await flush();
    expect([s.list().status.value, s.list().error.value?.code]).toEqual(['error', 'app_inactive']);
  });
});
