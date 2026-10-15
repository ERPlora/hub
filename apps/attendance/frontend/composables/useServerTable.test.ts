// The state of a server-side list of the attendance screens: search, sort, page and page size are the
// server's. The attendance lists take the sort as ONE value, the column with a leading «-» for descending
// (`name`, `-start_date`); the DataTable speaks column + direction, so this keeps both. Anything that
// changes which rows there are starts again from the first page; on a phone «Load more» grows one live
// window from the first row; a page emptied elsewhere steps back to the last page with rows.
import { describe, expect, it } from 'vitest';
import { effectScope, nextTick, shallowRef } from 'vue';

import { useServerTable } from './useServerTable';

function setup(options: Parameters<typeof useServerTable>[0] = { sort: 'name' }) {
  const scope = effectScope();
  const table = scope.run(() => useServerTable(options))!;
  return { table, scope };
}

describe('useServerTable', () => {
  it('starts on the first page of 50, sorted as asked, with no search', () => {
    const { table } = setup({ sort: 'name' });
    expect(table.params.value).toEqual({ sort: 'name', limit: 50, offset: 0 });
    expect([table.sort.value, table.dir.value, table.page.value, table.filtered.value]).toEqual(['name', 'asc', 0, false]);
  });

  it('reads a descending first sort from its «-»', () => {
    const { table } = setup({ sort: '-start_date' });
    expect([table.sort.value, table.dir.value]).toEqual(['start_date', 'desc']);
    expect(table.params.value.sort).toBe('-start_date');
  });

  it('sends a descending sort with a leading «-», and goes back to the first page', () => {
    const { table } = setup();
    table.goToPage(2);
    table.setSort({ sort: 'email', dir: 'desc' });
    expect(table.params.value).toEqual({ sort: '-email', limit: 50, offset: 0 });
    table.setSort({ sort: 'email', dir: 'asc' });
    expect(table.params.value.sort).toBe('email');
  });

  it('pages on the server; a new page size goes back to the first page', () => {
    const { table } = setup();
    table.goToPage(2);
    expect(table.params.value).toMatchObject({ limit: 50, offset: 100 });
    table.setPageSize(25);
    expect(table.params.value).toMatchObject({ limit: 25, offset: 0 });
  });

  it('searches the trimmed text from the first page; blank is no search', () => {
    const { table } = setup();
    table.goToPage(3);
    table.search.value = '  ana ';
    expect(table.params.value).toEqual({ search: 'ana', sort: 'name', limit: 50, offset: 0 });
    expect(table.filtered.value).toBe(true);
    table.search.value = '   ';
    expect(JSON.parse(JSON.stringify(table.params.value))).not.toHaveProperty('search');
    expect(table.filtered.value).toBe(false);
  });

  it('on a phone, «Load more» grows the rows from the first one, in windows of at most 100 (the server’s cap)', () => {
    const { table } = setup();
    expect(table.windows.value).toEqual([{ limit: 50, offset: 0 }]);
    table.loadMore();
    expect(table.windows.value).toEqual([{ limit: 100, offset: 0 }]);
    table.loadMore();
    expect(table.windows.value).toEqual([
      { limit: 100, offset: 0 },
      { limit: 50, offset: 100 },
    ]);
    table.loadMore();
    table.loadMore();
    expect(table.windows.value).toEqual([
      { limit: 100, offset: 0 },
      { limit: 100, offset: 100 },
      { limit: 50, offset: 200 },
    ]);
    table.goToPage(0);
    expect(table.windows.value).toEqual([{ limit: 50, offset: 0 }]);
  });

  it('never asks for more than 100 rows at once, whatever the page size and the «Load more»', () => {
    const { table } = setup();
    table.setPageSize(100);
    for (let i = 0; i < 6; i++) {
      table.loadMore();
      expect(table.params.value.limit).toBeLessThanOrEqual(100);
      for (const window of table.windows.value) expect(window.limit).toBeLessThanOrEqual(100);
    }
    expect(table.windows.value.reduce((sum, w) => sum + w.limit, 0)).toBe(700);
  });

  it('the query without the window: what every window shares (search and sort)', () => {
    const { table } = setup();
    table.search.value = 'ana';
    table.goToPage(2);
    expect(table.query.value).toEqual({ search: 'ana', sort: 'name' });
    expect(table.windows.value).toEqual([{ limit: 50, offset: 100 }]);
  });

  it('restart: the page’s filters narrow the rows and start from the first page', () => {
    const { table } = setup();
    table.goToPage(1);
    table.restart({ narrowed: true });
    expect([table.page.value, table.filtered.value]).toEqual([0, true]);
    table.restart({ narrowed: false });
    expect(table.filtered.value).toBe(false);
  });

  it('a page emptied by changes elsewhere steps back to the last page that has rows', async () => {
    const { table } = setup();
    const result = shallowRef<{ rows: unknown[]; total: number; offset: number } | undefined>(undefined);
    table.followResult(result);
    table.goToPage(2);
    result.value = { rows: [], total: 60, offset: 100 };
    await nextTick();
    expect(table.page.value).toBe(1);
  });
});
