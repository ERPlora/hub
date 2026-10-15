// The state of a server-side list of the schedule screens (SCHEDULE-F04, F05): search, sort, page and page
// size are the server's; anything that changes what the rows are starts again from the first page; on a
// phone «Load more» grows the rows from the first one, in WINDOWS of at most 100 (the server refuses a
// bigger `limit` with a 422), each a live subscription; a page emptied by deletions elsewhere steps back
// to the last page that still has rows.
import { describe, expect, it } from 'vitest';
import { effectScope, nextTick, shallowRef } from 'vue';

import { useServerTable } from './useServerTable';

function setup(options: Parameters<typeof useServerTable>[0] = { sort: 'date' }) {
  const scope = effectScope();
  const table = scope.run(() => useServerTable(options))!;
  return { table, scope };
}

describe('useServerTable', () => {
  it('starts on the first page of 50, sorted as asked, with no search', () => {
    const { table } = setup({ sort: 'start_date' });
    expect(table.params.value).toEqual({ sort: 'start_date', dir: 'asc', limit: 50, offset: 0 });
    expect([table.page.value, table.pageSize.value, table.filtered.value]).toEqual([0, 50, false]);
  });

  it('pages on the server, and a new page size goes back to the first page', () => {
    const { table } = setup();
    table.goToPage(2);
    expect(table.params.value).toMatchObject({ limit: 50, offset: 100 });
    table.setPageSize(25);
    expect(table.params.value).toMatchObject({ limit: 25, offset: 0 });
    expect(table.page.value).toBe(0);
  });

  it('searches the trimmed text from the first page; blank is no search', () => {
    const { table } = setup();
    table.goToPage(3);
    table.search.value = '  navidad ';
    expect(table.params.value).toEqual({ search: 'navidad', sort: 'date', dir: 'asc', limit: 50, offset: 0 });
    expect(table.search.value).toBe('  navidad ');
    expect(table.filtered.value).toBe(true);
    table.search.value = '   ';
    // `undefined` never reaches the wire: the subscription is JSON.
    expect(JSON.parse(JSON.stringify(table.params.value))).not.toHaveProperty('search');
    expect(table.filtered.value).toBe(false);
  });

  it('a new sort goes back to the first page', () => {
    const { table } = setup();
    table.goToPage(1);
    table.setSort({ sort: 'name', dir: 'desc' });
    expect(table.params.value).toMatchObject({ sort: 'name', dir: 'desc', offset: 0 });
    expect([table.sort.value, table.dir.value]).toEqual(['name', 'desc']);
  });

  it('a filter of the page restarts from the first page and counts as filtering', () => {
    const { table } = setup();
    table.goToPage(1);
    table.restart({ narrowed: true });
    expect([table.page.value, table.filtered.value]).toEqual([0, true]);
    table.restart({ narrowed: false });
    expect(table.filtered.value).toBe(false);
  });

  it('«Load more» grows the rows from the first one, in windows of at most 100; anything new starts again', () => {
    const { table } = setup();
    expect(table.windows.value).toEqual([{ limit: 50, offset: 0 }]);
    table.loadMore();
    expect(table.windows.value).toEqual([{ limit: 100, offset: 0 }]);
    table.loadMore();
    table.loadMore();
    table.loadMore();
    expect(table.windows.value).toEqual([
      { limit: 100, offset: 0 },
      { limit: 100, offset: 100 },
      { limit: 50, offset: 200 },
    ]);
    // The server caps `limit` at 100 (schemas.PageIn): no window ever asks for more.
    for (let i = 0; i < 6; i += 1) table.loadMore();
    expect(table.windows.value.every((w) => w.limit <= 100)).toBe(true);
    expect(table.windows.value.reduce((rows, w) => rows + w.limit, 0)).toBe(550);
    expect(table.params.value).toMatchObject({ limit: 100, offset: 0 });
    table.search.value = 'x';
    expect(table.windows.value).toEqual([{ limit: 50, offset: 0 }]);
    table.loadMore();
    table.goToPage(0);
    expect(table.windows.value).toEqual([{ limit: 50, offset: 0 }]);
  });

  it('a page of 100 grows by whole windows of 100', () => {
    const { table } = setup();
    table.setPageSize(100);
    table.loadMore();
    expect(table.windows.value).toEqual([
      { limit: 100, offset: 0 },
      { limit: 100, offset: 100 },
    ]);
  });

  it('the search goes at most 200 characters, as the server takes it', () => {
    const { table } = setup();
    table.search.value = 'x'.repeat(200);
    expect(table.params.value.search).toHaveLength(200);
    expect(table.query.value.search).toHaveLength(200);
  });

  it('a page left empty by changes elsewhere steps back to the last page that has rows', async () => {
    const { table, scope } = setup();
    const result = shallowRef<{ rows: unknown[]; total: number; offset: number } | undefined>();
    scope.run(() => table.followResult(result));
    table.goToPage(2);
    result.value = { rows: [], total: 60, offset: 100 };
    await nextTick();
    expect(table.page.value).toBe(1);
    result.value = { rows: [], total: 0, offset: 0 };
    await nextTick();
    expect(table.page.value).toBe(1);
  });
});
