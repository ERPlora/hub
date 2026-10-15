// `useLiveWindows(op, query, size, plan)`: THE engine of the app's live lists. A list followed live in
// windows of at most 100 rows (the server's cap: a bigger `limit` is a 422), each window its own
// subscription, the rows merged in order, the first window's total, the status and the first error.
// Left to itself it grows by «Load more» and a new query (another category, another search) starts
// again from one window; a table plans its rows instead (from its page's first row, as many as its
// pages show), cut in windows of at most `size`.
import { describe, expect, it } from 'vitest';
import { shallowRef } from 'vue';

import { errorFrame, mountComposable } from '../__tests__/mount-verifactu';
import { type LiveWindows, useLiveWindows, windowsOf } from './useLiveWindows';

const OP = 'verifactu.record.list';

const row = (id: string) => ({ id });

async function setup(size = 2) {
  const query = shallowRef<Record<string, unknown>>({ status: 'issued' });
  let list!: LiveWindows<{ id: string }>;
  const m = await mountComposable(() => {
    list = useLiveWindows(OP, () => query.value, size) as unknown as LiveWindows<{ id: string }>;
  });
  await m.live();
  return { ...m, query, list: () => list };
}

describe('useLiveWindows', () => {
  it('asks the first window with the query, the size as limit and offset 0', async () => {
    const s = await setup();
    expect(s.params(OP)).toEqual([{ status: 'issued', limit: 2, offset: 0 }]);
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
      { status: 'issued', limit: 2, offset: 0 },
      { status: 'issued', limit: 2, offset: 2 },
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
    s.query.value = { status: 'issued', search: 'ana' };
    // The window let go is released after the SDK's grace (a quick way back reuses it).
    await s.clock.advance(2000);
    await s.reopen();
    expect(s.params(OP)).toEqual([{ status: 'issued', search: 'ana', limit: 2, offset: 0 }]);
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

describe('useLiveWindows: rows planned by the caller (a table)', () => {
  async function planned(start: () => number, rows: () => number) {
    let list!: LiveWindows<{ id: string }>;
    const m = await mountComposable(() => {
      list = useLiveWindows(OP, () => ({ status: 'issued' }), 100, { start, rows }) as unknown as LiveWindows<{ id: string }>;
    });
    await m.live();
    return { ...m, list: () => list };
  }

  it('asks the rows from the page’s first row, cut in windows of at most 100', async () => {
    const page = shallowRef(2);
    const pages = shallowRef(1);
    const s = await planned(
      () => page.value * 50,
      () => pages.value * 50,
    );
    expect(s.params(OP)).toEqual([{ status: 'issued', limit: 50, offset: 100 }]);
    pages.value = 3;
    await s.reopen();
    expect(s.params(OP)).toEqual([
      { status: 'issued', limit: 100, offset: 100 },
      { status: 'issued', limit: 50, offset: 200 },
    ]);
    expect(s.list().windows.value).toEqual([
      { limit: 100, offset: 100 },
      { limit: 50, offset: 200 },
    ]);
  });

  it('has more while the rows asked end before the total', async () => {
    const s = await planned(
      () => 0,
      () => 50,
    );
    await s.result(OP, { rows: [row('a')], total: 80, limit: 50, offset: 0 });
    expect(s.list().hasMore.value).toBe(true);
  });
});

describe('windowsOf', () => {
  it('cuts the rows asked into windows of at most `size`, from the first row', () => {
    expect(windowsOf(0, 50, 100)).toEqual([{ limit: 50, offset: 0 }]);
    expect(windowsOf(0, 150, 100)).toEqual([
      { limit: 100, offset: 0 },
      { limit: 50, offset: 100 },
    ]);
    expect(windowsOf(40, 60, 20)).toEqual([
      { limit: 20, offset: 40 },
      { limit: 20, offset: 60 },
      { limit: 20, offset: 80 },
    ]);
  });
});
