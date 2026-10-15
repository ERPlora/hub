// `useServerTable(op, options)`: a list query of the verifactu app followed live in a server-side DataTable.
// Search, sort, page and page size are the server's; anything that changes WHICH rows there are starts
// again from the first page. On a phone «Load more» grows the rows from the first one, asked in WINDOWS
// of at most 100 rows (the server refuses `limit` > 100 with a 422: the bug of tax's first copy, which
// asked `pageSize * pages` at once), each window its own live subscription, merged into one page.
import { describe, expect, it } from 'vitest';
import { shallowRef } from 'vue';

import { errorFrame, flush, mountComposable } from '../__tests__/mount-verifactu';
import type { EventOut } from '../operations';
import { MAX_LIMIT, useServerTable } from './useServerTable';

const OP = 'verifactu.event.list';

const note = (n: number): EventOut => ({
  id: `n${n}`,
  created_at: '2026-10-14T10:00:00Z',
  kind: 'record_created',
  severity: 'info',
  message: `event ${n}`,
  record_id: null,
  invoice_number: '',
});
const notes = (from: number, count: number) => Array.from({ length: count }, (_, i) => note(from + i));

let captured: ReturnType<typeof useServerTable<typeof OP>> | undefined;

async function setup(pageSize?: number) {
  const m = await mountComposable(() => {
    captured = useServerTable(OP, { sort: 'created_at', maxSearch: 80, pageSize });
  });
  await m.live();
  const table = captured!;
  /** Applies a change of the table and lets the SDK reopen the stream with the new subscriptions. */
  async function change(action: () => void) {
    action();
    await flush();
    await m.reopen();
  }
  return { ...m, table, change };
}

describe('useServerTable: the query', () => {
  it('starts on the first page of 50, sorted as asked, with no search, waiting for the first result', async () => {
    const s = await setup();
    expect(s.params(OP)).toEqual([{ sort: 'created_at', dir: 'asc', limit: 50, offset: 0 }]);
    expect(s.table.status.value).toBe('loading');
    await s.result(OP, { rows: notes(0, 2), total: 2, limit: 50, offset: 0 });
    expect(s.table.status.value).toBe('live');
    expect(s.table.data.value).toEqual({ rows: notes(0, 2), total: 2, limit: 50, offset: 0 });
  });

  it('pages on the server; a new page size goes back to the first page', async () => {
    const s = await setup();
    await s.change(() => s.table.goToPage(2));
    expect(s.params(OP)).toEqual([{ sort: 'created_at', dir: 'asc', limit: 50, offset: 100 }]);
    await s.change(() => s.table.setPageSize(25));
    expect(s.table.page.value).toBe(0);
    expect(s.params(OP)).toEqual([{ sort: 'created_at', dir: 'asc', limit: 25, offset: 0 }]);
  });

  it('searches the trimmed text from the first page, at most as long as the list takes; blank is no search', async () => {
    const s = await setup();
    await s.change(() => s.table.goToPage(1));
    await s.change(() => (s.table.search.value = '  sin sal '));
    expect(s.params(OP)).toEqual([{ search: 'sin sal', sort: 'created_at', dir: 'asc', limit: 50, offset: 0 }]);
    expect(s.table.filtered.value).toBe(true);
    await s.change(() => (s.table.search.value = 'x'.repeat(200)));
    expect(s.params(OP)[0].search).toBe('x'.repeat(80));
    await s.change(() => (s.table.search.value = '   '));
    expect(s.params(OP)).toEqual([{ sort: 'created_at', dir: 'asc', limit: 50, offset: 0 }]);
    expect(s.table.filtered.value).toBe(false);
  });

  it('a new sort goes back to the first page', async () => {
    const s = await setup();
    await s.change(() => s.table.goToPage(3));
    await s.change(() => s.table.setSort({ sort: 'name', dir: 'desc' }));
    expect([s.table.sort.value, s.table.dir.value, s.table.page.value]).toEqual(['name', 'desc', 0]);
    expect(s.params(OP)).toEqual([{ sort: 'name', dir: 'desc', limit: 50, offset: 0 }]);
  });
});

describe('useServerTable: «Load more» in windows of at most 100', () => {
  it('never asks a limit over 100: 50 + 50 is one window of 100, one more is a second window of 50', async () => {
    const s = await setup();
    await s.result(OP, { rows: notes(0, 50), total: 230, limit: 50, offset: 0 });
    await s.change(() => s.table.loadMore());
    expect(s.params(OP)).toEqual([{ sort: 'created_at', dir: 'asc', limit: 100, offset: 0 }]);
    await s.change(() => s.table.loadMore());
    expect(s.params(OP)).toEqual([
      { sort: 'created_at', dir: 'asc', limit: 100, offset: 0 },
      { sort: 'created_at', dir: 'asc', limit: 50, offset: 100 },
    ]);
    for (const params of s.params(OP)) expect(params.limit as number).toBeLessThanOrEqual(MAX_LIMIT);
  });

  it('a page of 100 grows by whole windows of 100', async () => {
    const s = await setup(100);
    await s.change(() => s.table.loadMore());
    await s.change(() => s.table.loadMore());
    expect(s.params(OP).map((p) => [p.limit, p.offset])).toEqual([
      [100, 0],
      [100, 100],
      [100, 200],
    ]);
  });

  it('merges the windows in order, «loading» until every window answered', async () => {
    const s = await setup();
    await s.change(() => s.table.loadMore());
    await s.change(() => s.table.loadMore());
    await s.result(OP, { rows: notes(0, 100), total: 130, limit: 100, offset: 0 }, { offset: 0 });
    expect(s.table.status.value, 'the second window has not answered').toBe('loading');
    await s.result(OP, { rows: notes(100, 30), total: 130, limit: 50, offset: 100 }, { offset: 100 });
    expect(s.table.status.value).toBe('live');
    const page = s.table.data.value!;
    expect([page.rows.length, page.total, page.limit, page.offset]).toEqual([130, 130, 150, 0]);
    expect(page.rows.map((r) => r.id)).toEqual(notes(0, 130).map((r) => r.id));
  });

  it('a new search starts again from one window and releases the others', async () => {
    const s = await setup();
    await s.change(() => s.table.loadMore());
    await s.change(() => s.table.loadMore());
    await s.change(() => (s.table.search.value = 'hielo'));
    await s.clock.advance(2500);
    expect(s.params(OP)).toEqual([{ search: 'hielo', sort: 'created_at', dir: 'asc', limit: 50, offset: 0 }]);
  });

  it('an error in any window is the list’s error', async () => {
    const s = await setup();
    await s.change(() => s.table.loadMore());
    await s.change(() => s.table.loadMore());
    s.net.lastStream().push(errorFrame(s.subId(OP, { offset: 100 }), 'verifactu.boom'));
    await flush();
    expect([s.table.status.value, s.table.error.value?.code]).toEqual(['error', 'verifactu.boom']);
  });
});

describe('useServerTable: a page emptied elsewhere', () => {
  it('steps back to the last page that still has rows', async () => {
    const s = await setup();
    await s.change(() => s.table.goToPage(2));
    await s.result(OP, { rows: [], total: 60, limit: 50, offset: 100 });
    expect(s.table.page.value).toBe(1);
  });
});

// Records filters its list by status, type, environment, dates and total: the page's own filters travel with
// every window, a change of them starts again from the first page (one window), and the page says
// whether they narrow the rows (the empty state then says «No results», not «Nothing yet»).
describe('useServerTable: the page’s own filters', () => {
  const SALES = 'verifactu.record.list';
  let filtered: ReturnType<typeof useServerTable<typeof SALES>> | undefined;
  const filters = shallowRef<Record<string, unknown>>({ issue_date_from: '2026-10-14', issue_date_to: '2026-10-14' });
  const narrowed = shallowRef(false);

  async function setupFiltered() {
    filters.value = { issue_date_from: '2026-10-14', issue_date_to: '2026-10-14' };
    narrowed.value = false;
    const m = await mountComposable(() => {
      filtered = useServerTable(SALES, {
        sort: 'created_at',
        dir: 'desc',
        maxSearch: 200,
        filters: () => filters.value,
        narrowed: () => narrowed.value,
      });
    });
    await m.live();
    const table = filtered!;
    async function change(action: () => void) {
      action();
      await flush();
      await m.reopen();
    }
    return { ...m, table, change };
  }

  it('travel with every window', async () => {
    const s = await setupFiltered();
    expect(s.params(SALES)).toEqual([{ issue_date_from: '2026-10-14', issue_date_to: '2026-10-14', sort: 'created_at', dir: 'desc', limit: 50, offset: 0 }]);
    await s.change(() => s.table.loadMore());
    await s.change(() => s.table.loadMore());
    expect(s.params(SALES).map((p) => [p.issue_date_from, p.limit, p.offset])).toEqual([
      ['2026-10-14', 100, 0],
      ['2026-10-14', 50, 100],
    ]);
  });

  it('a change of them starts again from the first page, in one window', async () => {
    const s = await setupFiltered();
    await s.change(() => s.table.goToPage(2));
    await s.change(() => s.table.loadMore());
    await s.change(() => (filters.value = { status: 'rejected' }));
    await s.clock.advance(2500);
    expect(s.table.page.value).toBe(0);
    expect(s.params(SALES)).toEqual([{ status: 'rejected', sort: 'created_at', dir: 'desc', limit: 50, offset: 0 }]);
  });

  it('the list is filtered while the page says they narrow it, or while there is a search', async () => {
    const s = await setupFiltered();
    expect(s.table.filtered.value).toBe(false);
    narrowed.value = true;
    expect(s.table.filtered.value).toBe(true);
    narrowed.value = false;
    s.table.search.value = 'FACT';
    expect(s.table.filtered.value).toBe(true);
  });
});
