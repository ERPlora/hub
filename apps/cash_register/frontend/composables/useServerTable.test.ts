// `useServerTable(op, options)`: a list query of the drawer followed live behind a server-side DataTable.
// Search, sort, page and page size are the server's; anything that changes WHICH rows there are starts
// again from the first page. On a phone «Load more» grows the rows from the first one, asked in WINDOWS of
// at most 100 rows (the server refuses `limit` > 100 with a 422), each window its own live subscription,
// merged into one page. The page's own filters travel with every window.
import { describe, expect, it } from 'vitest';
import { shallowRef } from 'vue';

import { errorFrame, flush, mountComposable } from '../__tests__/mount-cash-register';
import type { SessionRow } from '../operations';
import { MAX_LIMIT, useServerTable, windowsOf } from './useServerTable';

const OP = 'cash_register.session.list';

const session = (n: number) => ({ id: `s${n}`, number: `S-261014-${String(n).padStart(4, '0')}` }) as SessionRow;
const sessions = (from: number, count: number) => Array.from({ length: count }, (_, i) => session(from + i));

let captured: ReturnType<typeof useServerTable<typeof OP>> | undefined;
const filters = shallowRef<Record<string, unknown>>({});
const narrowed = shallowRef(false);

async function setup(pageSize?: number) {
  filters.value = {};
  narrowed.value = false;
  const m = await mountComposable(() => {
    captured = useServerTable(OP, {
      sort: 'opened_at',
      dir: 'desc',
      maxSearch: 24,
      pageSize,
      filters: () => filters.value,
      narrowed: () => narrowed.value,
    });
  });
  await m.live();
  const table = captured!;
  async function change(action: () => void) {
    action();
    await flush();
    await m.reopen();
  }
  return { ...m, table, change };
}

describe('useServerTable: the query', () => {
  it('starts on the first page of 50, newest first, waiting for the first result', async () => {
    const s = await setup();
    expect(s.params(OP)).toEqual([{ sort: 'opened_at', dir: 'desc', limit: 50, offset: 0 }]);
    expect(s.table.status.value).toBe('loading');
    await s.result(OP, { rows: sessions(0, 2), total: 2, limit: 50, offset: 0 });
    expect(s.table.status.value).toBe('live');
    expect(s.table.data.value).toEqual({ rows: sessions(0, 2), total: 2, limit: 50, offset: 0 });
  });

  it('pages on the server; a new page size, a sort or a search go back to the first page', async () => {
    const s = await setup();
    await s.change(() => s.table.goToPage(2));
    expect(s.params(OP)).toEqual([{ sort: 'opened_at', dir: 'desc', limit: 50, offset: 100 }]);
    await s.change(() => s.table.setPageSize(25));
    expect(s.params(OP)).toEqual([{ sort: 'opened_at', dir: 'desc', limit: 25, offset: 0 }]);
    await s.change(() => s.table.goToPage(3));
    await s.change(() => s.table.setSort({ sort: 'difference', dir: 'asc' }));
    expect(s.params(OP)).toEqual([{ sort: 'difference', dir: 'asc', limit: 25, offset: 0 }]);
    await s.change(() => (s.table.search.value = '  0007 '));
    expect(s.params(OP)).toEqual([{ search: '0007', sort: 'difference', dir: 'asc', limit: 25, offset: 0 }]);
    expect(s.table.filtered.value).toBe(true);
    await s.change(() => (s.table.search.value = 'x'.repeat(40)));
    expect(s.params(OP)[0].search).toBe('x'.repeat(24));
  });

  it('the page’s filters travel with every window and start again from the first page', async () => {
    const s = await setup();
    await s.change(() => s.table.goToPage(2));
    await s.change(() => (filters.value = { status: 'closed' }));
    expect(s.table.page.value).toBe(0);
    expect(s.params(OP)).toEqual([{ status: 'closed', sort: 'opened_at', dir: 'desc', limit: 50, offset: 0 }]);
    narrowed.value = true;
    expect(s.table.filtered.value).toBe(true);
  });
});

describe('useServerTable: «Load more» in windows of at most 100', () => {
  it('never asks a limit over 100', async () => {
    const s = await setup();
    await s.result(OP, { rows: sessions(0, 50), total: 230, limit: 50, offset: 0 });
    await s.change(() => s.table.loadMore());
    expect(s.params(OP)).toEqual([{ sort: 'opened_at', dir: 'desc', limit: 100, offset: 0 }]);
    await s.change(() => s.table.loadMore());
    expect(s.params(OP).map((p) => [p.limit, p.offset])).toEqual([
      [100, 0],
      [50, 100],
    ]);
    for (const params of s.params(OP)) expect(params.limit as number).toBeLessThanOrEqual(MAX_LIMIT);
  });

  it('merges the windows in order, «loading» until every window answered', async () => {
    const s = await setup();
    await s.change(() => s.table.loadMore());
    await s.change(() => s.table.loadMore());
    await s.result(OP, { rows: sessions(0, 100), total: 130, limit: 100, offset: 0 }, { offset: 0 });
    expect(s.table.status.value).toBe('loading');
    await s.result(OP, { rows: sessions(100, 30), total: 130, limit: 50, offset: 100 }, { offset: 100 });
    expect(s.table.status.value).toBe('live');
    const page = s.table.data.value!;
    expect([page.rows.length, page.total, page.limit, page.offset]).toEqual([130, 130, 150, 0]);
  });

  it('an error in any window is the list’s error', async () => {
    const s = await setup();
    await s.change(() => s.table.loadMore());
    await s.change(() => s.table.loadMore());
    s.net.lastStream().push(errorFrame(s.subId(OP, { offset: 100 }), 'cash_register.boom'));
    await flush();
    expect([s.table.status.value, s.table.error.value?.code]).toEqual(['error', 'cash_register.boom']);
  });

  it('a page emptied elsewhere steps back to the last page that still has rows', async () => {
    const s = await setup();
    await s.change(() => s.table.goToPage(2));
    await s.result(OP, { rows: [], total: 60, limit: 50, offset: 100 });
    expect(s.table.page.value).toBe(1);
  });
});

describe('windowsOf', () => {
  it('cuts the rows asked into windows of at most `size`, from the first row', () => {
    expect(windowsOf(0, 50, 100)).toEqual([{ limit: 50, offset: 0 }]);
    expect(windowsOf(0, 150, 100)).toEqual([
      { limit: 100, offset: 0 },
      { limit: 50, offset: 100 },
    ]);
  });
});
