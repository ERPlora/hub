// The state of an inventory list on the server (products, movements, categories, low stock): search,
// sort («name», «-name»: the API's own form), page and page size are the server's. Whatever changes
// WHICH rows there are starts from the first page; on a phone «Load more» grows one live window from
// the first row. The API serves at most 100 rows per query (`PageIn.limit` ≤ 100): the window is cut
// into queries of at most 100 rows, never one bigger. A page emptied by changes elsewhere steps back.
import { describe, expect, it } from 'vitest';
import { nextTick, ref } from 'vue';

import { useServerTable } from './useServerTable';

describe('useServerTable', () => {
  it('starts on the first page with the default sort and page size', () => {
    const table = useServerTable({ sort: 'name', pageSize: 25 });
    expect(table.params.value).toEqual({ sort: 'name' });
    expect(table.windows.value).toEqual([{ limit: 25, offset: 0 }]);
    expect([table.sortKey.value, table.sortDir.value, table.filtered.value]).toEqual(['name', 'asc', false]);
  });

  it('a descending default sort reads as its column and «desc»', () => {
    const table = useServerTable({ sort: '-created_at' });
    expect([table.sortKey.value, table.sortDir.value]).toEqual(['created_at', 'desc']);
  });

  it('pages, and every change of the rows starts from the first page', () => {
    const table = useServerTable({ sort: 'name' });
    table.goToPage(2);
    expect(table.windows.value).toEqual([{ limit: 50, offset: 100 }]);
    table.search.value = '  caf ';
    expect([table.params.value, table.windows.value]).toEqual([{ search: 'caf', sort: 'name' }, [{ limit: 50, offset: 0 }]]);
    table.goToPage(1);
    table.setSort({ sort: 'price', dir: 'desc' });
    expect([table.params.value, table.windows.value]).toEqual([{ search: 'caf', sort: '-price' }, [{ limit: 50, offset: 0 }]]);
    table.goToPage(1);
    table.setPageSize(10);
    expect(table.windows.value).toEqual([{ limit: 10, offset: 0 }]);
    table.goToPage(1);
    table.restart({ narrowed: true });
    expect([table.windows.value[0].offset, table.filtered.value]).toEqual([0, true]);
  });

  it('«Load more» grows one window from the first row, cut into queries of at most 100 rows', () => {
    const table = useServerTable({ sort: 'name', pageSize: 50 });
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
  });

  it('never asks for more than 100 rows in one query, whatever the page size and the loads', () => {
    for (const pageSize of [10, 25, 50, 100]) {
      const table = useServerTable({ sort: 'name', pageSize });
      for (let i = 0; i < 12; i++) {
        table.loadMore();
        for (const window of table.windows.value) expect(window.limit, `${pageSize} × ${i + 2}`).toBeLessThanOrEqual(100);
        const rows = table.windows.value.reduce((sum, window) => sum + window.limit, 0);
        expect(rows).toBe(pageSize * (i + 2));
      }
    }
  });

  it('a page emptied elsewhere steps back to the last page that has rows', async () => {
    const table = useServerTable({ sort: 'name', pageSize: 10 });
    const result = ref<{ rows: unknown[]; total: number; offset: number }>();
    table.followResult(result);
    table.goToPage(3);
    result.value = { rows: [], total: 15, offset: 30 };
    await nextTick();
    expect(table.windows.value[0].offset).toBe(10);
  });
});
