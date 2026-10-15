// `useServerTable(op, options)`: a list query of the invoice app followed live behind a server-side
// DataTable (Invoices, Series). Search, sort, page and page size are the server's; anything that changes
// WHICH rows there are (a search, a sort, a page size) starts again from the first page. On a phone «Load
// more» grows the rows from the first one: they are asked through the app's one live-windows engine
// (`useLiveWindows`), in WINDOWS of at most `MAX_LIMIT` rows (the server refuses a bigger `limit`), each
// its own `useLive` subscription, merged into one page for the table (the rows in order, the query's
// total, «loading» until every window answered, the first error). A window less releases its
// subscription. A page emptied by changes elsewhere steps back to the last page that still has rows. A
// page with filters of its own (Invoices: status, type, series, source, dates, total) passes them as
// `filters`: they travel with every window, a change of them starts again from the first page, and
// `narrowed` says whether they narrow the rows.
import type { OpName, OutputOf } from '@erplora/ui/sdk';
import { computed, ref, watch } from 'vue';

import type { SortDir } from '../operations';
import { type ListWindow, MAX_WINDOW, useLiveWindows } from './useLiveWindows';

/** The largest page the server serves (`schemas.PageIn.limit`). */
export const MAX_LIMIT = MAX_WINDOW;

export type { ListWindow };

export interface ServerTableOptions {
  /** Column the server sorts by at first. */
  sort: string;
  dir?: SortDir;
  pageSize?: number;
  /** The longest search the list takes (`max_length` of its schema's `search`). */
  maxSearch: number;
  /** The page's own filters, as the list query takes them: sent with every window. */
  filters?: () => object;
  /** The page's filters narrow the rows (the empty state says «No results»). */
  narrowed?: () => boolean;
}

/** What a list query answers: a page of rows. */
interface PageOut {
  rows: unknown[];
  total: number;
  limit: number;
  offset: number;
}

export function useServerTable<Op extends OpName>(op: Op, options: ServerTableOptions) {
  const text = ref('');
  /** 0-based, as the DataTable counts. */
  const page = ref(0);
  const pageSize = ref(options.pageSize ?? 50);
  /** Pages shown from `page` on: 1 on a desk; each «Load more» on a phone adds one. */
  const windowPages = ref(1);
  const sort = ref(options.sort);
  const dir = ref<SortDir>(options.dir ?? 'asc');

  /** Shows page `n` alone (the desk pager, a new search, a crossed breakpoint). */
  function goToPage(n: number): void {
    page.value = n;
    windowPages.value = 1;
  }

  /** `v-model:search` of the DataTable: a new search starts from the first page. */
  const search = computed({
    get: () => text.value,
    set: (value: string) => {
      text.value = value;
      goToPage(0);
    },
  });

  function setPageSize(size: number): void {
    pageSize.value = size;
    goToPage(0);
  }

  function setSort(next: { sort: string; dir: SortDir }): void {
    sort.value = next.sort;
    dir.value = next.dir;
    goToPage(0);
  }

  function loadMore(): void {
    windowPages.value += 1;
  }

  const filtered = computed(() => text.value.trim() !== '' || (options.narrowed?.() ?? false));

  /** The page's filters, by content: a new object with the same filters is no change. */
  const pageFilters = computed(() => JSON.stringify(options.filters?.() ?? {}));
  watch(pageFilters, () => goToPage(0));

  /** The page's filters, search and sort: what every window shares. */
  const query = computed(() => ({
    ...(JSON.parse(pageFilters.value) as object),
    ...(text.value.trim() ? { search: text.value.trim().slice(0, options.maxSearch) } : {}),
    sort: sort.value,
    dir: dir.value,
  }));

  /** The rows on screen, from the page's first row, as windows of at most `MAX_LIMIT` (the engine's). */
  const list = useLiveWindows(op, () => query.value, MAX_LIMIT, {
    start: () => page.value * pageSize.value,
    rows: () => pageSize.value * windowPages.value,
  });
  const windows = list.windows;

  /** One page for the table: the rows of every window, the query's total, the span asked. */
  const data = computed(() => {
    const total = list.total.value;
    if (total === undefined) return undefined;
    const shown = windows.value;
    return {
      rows: list.rows.value,
      total,
      limit: shown.reduce((sum, window) => sum + window.limit, 0),
      offset: shown[0]?.offset ?? 0,
    } as OutputOf<Op>;
  });

  // A page emptied by changes elsewhere (rows deleted on another device) steps back.
  watch(data, (now) => {
    const shape = now as PageOut | undefined;
    if (shape && shape.rows.length === 0 && shape.total > 0 && shape.offset >= shape.total) {
      goToPage(Math.ceil(shape.total / pageSize.value) - 1);
    }
  });

  return {
    search,
    page,
    pageSize,
    sort,
    dir,
    filtered,
    windows,
    goToPage,
    setPageSize,
    setSort,
    loadMore,
    data,
    status: list.status,
    error: list.error,
    /** Reopens the stream so the server runs every window again. */
    refresh: list.refresh,
  };
}
