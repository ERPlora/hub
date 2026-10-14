// The state of a server-side customer list (customers, groups, tags, fields: WORKBOOK «Pantallas»):
// search, sort, page and page size are the server's; anything that changes WHICH rows there are
// starts again from the first page; on a phone «Load more» grows one live window from the first row.
import { describe, expect, it } from 'vitest';
import { nextTick, ref } from 'vue';

import { useListState, windowsOf } from './useListState';

describe('windowsOf', () => {
  it('cuts `count` rows from `start` in pieces of at most 100', () => {
    expect(windowsOf(0, 50)).toEqual([{ limit: 50, offset: 0 }]);
    expect(windowsOf(0, 150)).toEqual([
      { limit: 100, offset: 0 },
      { limit: 50, offset: 100 },
    ]);
    expect(windowsOf(200, 100)).toEqual([{ limit: 100, offset: 200 }]);
  });
});

describe('useListState', () => {
  it('asks for 50 sorted by name, from the first row, with no search', () => {
    const list = useListState({ sort: 'name' });
    expect(list.params.value).toEqual({ sort: 'name', descending: false, limit: 50, offset: 0 });
    expect(list.filtered.value).toBe(false);
  });

  it('a search is trimmed, starts from the first page and counts as narrowing', () => {
    const list = useListState({ sort: 'name' });
    list.goToPage(2);
    list.search.value = '  ana ';
    expect(list.search.value).toBe('  ana ');
    expect(list.params.value).toMatchObject({ search: 'ana', offset: 0 });
    expect(list.filtered.value).toBe(true);
  });

  it('pages one page at a time, and a new page size starts again', () => {
    const list = useListState({ sort: 'name' });
    list.goToPage(1);
    expect(list.params.value).toMatchObject({ limit: 50, offset: 50 });
    list.setPageSize(25);
    expect(list.params.value).toMatchObject({ limit: 25, offset: 0 });
  });

  it('a sort from the table header orders asc or desc, from the first page', () => {
    const list = useListState({ sort: 'name' });
    list.goToPage(3);
    list.setSort({ sort: 'total_spent', dir: 'desc' });
    expect(list.params.value).toMatchObject({ sort: 'total_spent', descending: true, offset: 0 });
    expect(list.dir.value).toBe('desc');
  });

  it('«Load more» grows the window from the first row; a new page goes back to one page', () => {
    const list = useListState({ sort: 'name' });
    list.loadMore();
    list.loadMore();
    expect(list.windows.value).toEqual([
      { limit: 100, offset: 0 },
      { limit: 50, offset: 100 },
    ]);
    list.goToPage(0);
    expect(list.windows.value).toEqual([{ limit: 50, offset: 0 }]);
  });

  it('never asks for more than 100 rows at once (the server refuses more): the window is cut in pieces of ≤ 100', () => {
    const list = useListState({ sort: 'name' });
    expect(list.windows.value).toEqual([{ limit: 50, offset: 0 }]);
    list.loadMore();
    list.loadMore();
    list.loadMore();
    list.loadMore();
    expect(list.windows.value).toEqual([
      { limit: 100, offset: 0 },
      { limit: 100, offset: 100 },
      { limit: 50, offset: 200 },
    ]);
    for (const window of list.windows.value) expect(window.limit).toBeLessThanOrEqual(100);
    list.setPageSize(100);
    list.goToPage(3);
    expect(list.windows.value).toEqual([{ limit: 100, offset: 300 }]);
    expect(list.params.value).toMatchObject({ limit: 100, offset: 300 });
  });

  it('the base params carry the search and sort, without limit nor offset', () => {
    const list = useListState({ sort: 'name' });
    list.search.value = 'ana';
    expect(list.base.value).toEqual({ search: 'ana', sort: 'name', descending: false });
  });

  it('the page\'s own filters restart from the first page and say whether they narrow', () => {
    const list = useListState({ sort: 'name' });
    list.goToPage(1);
    list.restart({ narrowed: true });
    expect([list.params.value.offset, list.filtered.value]).toEqual([0, true]);
  });

  it('a page emptied by changes elsewhere steps back to the last page with rows', async () => {
    const list = useListState({ sort: 'name' });
    const result = ref<{ rows: unknown[]; total: number; offset: number } | undefined>();
    list.followResult(result);
    list.goToPage(2);
    result.value = { rows: [], total: 60, offset: 100 };
    await nextTick();
    expect(list.page.value).toBe(1);
  });
});
