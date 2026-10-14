// `useLiveWindows(op, query, size)`: a list followed live in windows of at most 100 rows (the server's
// cap: a bigger `limit` is a 422), each window its own subscription. «Load more» opens the next
// window; a new query (another category, another search) starts again from one window.
import { describe, expect, it } from 'vitest';
import { defineComponent, h, shallowRef } from 'vue';

import { errorFrame, mountSale } from '../../__tests__/mount-sale';
import { useLiveWindows, type LiveWindows } from './useLiveWindows';

const OP = 'sale.order.list';

const row = (id: string) => ({ id });

async function setup(size = 2) {
  const query = shallowRef<Record<string, unknown>>({ status: 'open' });
  let list!: LiveWindows<{ id: string }>;
  const Probe = defineComponent({
    setup() {
      list = useLiveWindows(OP, () => query.value, size) as unknown as LiveWindows<{ id: string }>;
      return () => h('div');
    },
  });
  const m = await mountSale(Probe);
  await m.live();
  return { ...m, query, list: () => list };
}

describe('useLiveWindows', () => {
  it('asks the first window with the query, the size as limit and offset 0', async () => {
    const s = await setup();
    expect(s.params(OP)).toEqual([{ status: 'open', limit: 2, offset: 0 }]);
    expect(s.list().status.value).toBe('loading');
    await s.result(OP, { rows: [row('a'), row('b')], total: 3, limit: 2, offset: 0 });
    expect(s.list().rows.value).toEqual([row('a'), row('b')]);
    expect(s.list().total.value).toBe(3);
    expect(s.list().hasMore.value).toBe(true);
    expect(s.list().status.value).toBe('live');
  });

  it('«load more» opens the next window as one more subscription and appends its rows in order', async () => {
    const s = await setup();
    await s.result(OP, { rows: [row('a'), row('b')], total: 3, limit: 2, offset: 0 });
    s.list().loadMore();
    await s.reopen();
    expect(s.params(OP)).toEqual([
      { status: 'open', limit: 2, offset: 0 },
      { status: 'open', limit: 2, offset: 2 },
    ]);
    expect(s.list().status.value).toBe('loading');
    await s.result(OP, { rows: [row('a'), row('b')], total: 3, limit: 2, offset: 0 }, { offset: 0 });
    await s.result(OP, { rows: [row('c')], total: 3, limit: 2, offset: 2 }, { offset: 2 });
    expect(s.list().rows.value).toEqual([row('a'), row('b'), row('c')]);
    expect(s.list().hasMore.value).toBe(false);
  });

  it('never asks more than one window at a time while the last one is still loading', async () => {
    const s = await setup();
    await s.result(OP, { rows: [row('a'), row('b')], total: 9, limit: 2, offset: 0 });
    s.list().loadMore();
    s.list().loadMore();
    await s.reopen();
    expect(s.params(OP).map((p) => p.offset)).toEqual([0, 2]);
  });

  it('a new query starts again from a single window and lets the others go', async () => {
    const s = await setup();
    await s.result(OP, { rows: [row('a'), row('b')], total: 3, limit: 2, offset: 0 });
    s.list().loadMore();
    await s.reopen();
    s.query.value = { status: 'open', search: 'ana' };
    // The window let go is released after the SDK's grace (a quick way back reuses it).
    await s.clock.advance(2000);
    await s.reopen();
    expect(s.params(OP)).toEqual([{ status: 'open', search: 'ana', limit: 2, offset: 0 }]);
  });

  it('refuses a window bigger than the server takes (100)', () => {
    expect(() => useLiveWindows(OP, () => ({}), 101)).toThrow(/100/);
  });

  it('says the error of a window and keeps the rows it has', async () => {
    const s = await setup();
    await s.result(OP, { rows: [row('a'), row('b')], total: 3, limit: 2, offset: 0 });
    s.net.lastStream().push(errorFrame(s.subId(OP), 'app_inactive'));
    await s.reopen();
    expect(s.list().status.value).toBe('error');
    expect(s.list().error.value?.code).toBe('app_inactive');
    expect(s.list().rows.value).toEqual([row('a'), row('b')]);
  });
});
