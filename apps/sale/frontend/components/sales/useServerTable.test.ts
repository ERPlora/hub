// The state of the Sales list (SALE-F28; the tax lists' server table, made the sale app's own): search,
// sort and page are the server's; anything that changes WHICH rows there are starts again from the
// first page; a phone's «Load more» grows the rows from the first one in WINDOWS of at most 100 rows
// (the server refuses `limit` > 100 with a 422), each its own live subscription; a page emptied by
// changes elsewhere steps back to the last page that still has rows.
import { describe, expect, it } from 'vitest';
import { effectScope, nextTick, shallowRef } from 'vue';

import { MAX_LIMIT, MAX_SEARCH, useServerTable } from './useServerTable';

function setup(options: Parameters<typeof useServerTable>[0] = { sort: 'created_at', dir: 'desc' }) {
  const scope = effectScope();
  const table = scope.run(() => useServerTable(options))!;
  return { table, scope };
}

describe('useServerTable', () => {
  it('starts on the first page of 50, newest first, with no search', () => {
    const { table } = setup();
    expect(table.params.value).toEqual({ sort: 'created_at', dir: 'desc', limit: 50, offset: 0 });
    expect([table.page.value, table.pageSize.value, table.filtered.value]).toEqual([0, 50, false]);
  });

  it('pages on the server', () => {
    const { table } = setup();
    table.goToPage(2);
    expect(table.windows.value).toEqual([{ limit: 50, offset: 100 }]);
  });

  it('searches the trimmed text from the first page; blank is no search', () => {
    const { table } = setup();
    table.goToPage(3);
    table.search.value = '  0007 ';
    expect(table.params.value).toEqual({ search: '0007', sort: 'created_at', dir: 'desc', limit: 50, offset: 0 });
    expect(table.filtered.value).toBe(true);
    table.search.value = '   ';
    expect(JSON.parse(JSON.stringify(table.params.value))).not.toHaveProperty('search');
    expect(table.filtered.value).toBe(false);
  });

  it('a new sort goes back to the first page', () => {
    const { table } = setup();
    table.goToPage(1);
    table.setSort({ sort: 'total', dir: 'asc' });
    expect(table.params.value).toMatchObject({ sort: 'total', dir: 'asc', offset: 0 });
  });

  it('a filter of the page restarts from the first page and counts as filtering', () => {
    const { table } = setup();
    table.goToPage(1);
    table.restart({ narrowed: true });
    expect([table.page.value, table.filtered.value]).toEqual([0, true]);
    table.restart({ narrowed: false });
    expect(table.filtered.value).toBe(false);
  });

  it('«Load more» never asks for more than 100 rows at once: the second one already needs two windows', () => {
    const { table } = setup();
    expect(MAX_LIMIT).toBe(100);
    table.loadMore();
    expect(table.windows.value).toEqual([{ limit: 100, offset: 0 }]);
    // The second «Load more» (150 rows) was the 422 of a single `limit: 150`.
    table.loadMore();
    expect(table.windows.value).toEqual([
      { limit: 100, offset: 0 },
      { limit: 50, offset: 100 },
    ]);
    for (let i = 0; i < 7; i += 1) table.loadMore();
    expect(table.windows.value.every((w) => w.limit <= MAX_LIMIT)).toBe(true);
    expect(table.windows.value.reduce((rows, w) => rows + w.limit, 0)).toBe(500);
    // Windows follow each other with no gap nor overlap.
    table.windows.value.forEach((w, i, all) => expect(w.offset).toBe(i === 0 ? 0 : all[i - 1].offset + all[i - 1].limit));
    table.search.value = 'x';
    expect(table.windows.value).toEqual([{ limit: 50, offset: 0 }]);
  });

  it('the search goes at most as long as the server takes it', () => {
    const { table } = setup();
    expect(MAX_SEARCH).toBe(200);
    table.search.value = 'x'.repeat(300);
    expect(table.params.value.search).toHaveLength(200);
  });

  it('a page left empty by changes elsewhere steps back to the last page that has rows', async () => {
    const { table, scope } = setup();
    const result = shallowRef<{ rows: unknown[]; total: number; offset: number } | undefined>();
    scope.run(() => table.followResult(result));
    table.goToPage(2);
    result.value = { rows: [], total: 60, offset: 100 };
    await nextTick();
    expect(table.page.value).toBe(1);
  });
});
