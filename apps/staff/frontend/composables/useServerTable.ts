// The state of a server-side list of the staff screens: search, sort, page and page size are the
// server's. The staff lists take the sort as one value (`name`, `-start_date`: a leading «-» sorts
// descending); the DataTable speaks column + direction, so both are kept here. Anything that changes
// WHICH rows there are (a search, a filter, a sort, a page size) starts again from the first page. On
// a phone «Load more» grows the rows from the first one, so every row on screen stays live; a desk
// pages one page at a time. The server never gives more than 100 rows at once (`PageIn`, 422 above),
// so the rows on screen are cut into `windows` of at most 100, each its own live subscription
// (`useLiveList`); `params` is the first window, which is the whole page on a desk.
import { computed, type Ref, ref, watch } from 'vue';

export type SortDir = 'asc' | 'desc';

/** The most rows the server gives at once (`PageIn.limit`, schemas.py). */
export const MAX_LIMIT = 100;

/** One slice of the rows on screen: one live subscription. */
export interface ListWindow {
  limit: number;
  offset: number;
}

/** What every window of the list shares: the search and the sort. */
export interface ServerTableQuery {
  search?: string;
  sort: string;
}

export interface ServerTableOptions {
  /** The first sort, as the server takes it (`name`, `-start_date`). */
  sort: string;
  pageSize?: number;
}

/** What the list query takes from the table (the page adds its filters). */
export interface ServerTableParams {
  search?: string;
  sort: string;
  limit: number;
  offset: number;
}

/** The part of a result page the table needs to step back from an emptied page. */
interface PageShape {
  rows: readonly unknown[];
  total: number;
  offset: number;
}

export function useServerTable(options: ServerTableOptions) {
  const text = ref('');
  /** 0-based, as the DataTable counts. */
  const page = ref(0);
  const pageSize = ref(options.pageSize ?? 50);
  /** Pages the live window holds from `page` on: 1 on a desk; each «Load more» on a phone adds one. */
  const windowPages = ref(1);
  const sort = ref(options.sort.replace(/^-/, ''));
  const dir = ref<SortDir>(options.sort.startsWith('-') ? 'desc' : 'asc');
  /** The page's own filters narrow the rows (set by `restart`). */
  const narrowed = ref(false);

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

  /** The page changed its filters: from the first page again, and say whether they narrow the rows. */
  function restart(state: { narrowed: boolean }): void {
    narrowed.value = state.narrowed;
    goToPage(0);
  }

  const filtered = computed(() => text.value.trim() !== '' || narrowed.value);

  const query = computed<ServerTableQuery>(() => ({
    search: text.value.trim() || undefined,
    sort: dir.value === 'desc' ? `-${sort.value}` : sort.value,
  }));

  /** The rows on screen in slices of at most 100, from the page's first row. */
  const windows = computed<ListWindow[]>(() => {
    const start = page.value * pageSize.value;
    const rows = pageSize.value * windowPages.value;
    const out: ListWindow[] = [];
    for (let taken = 0; taken < rows; taken += MAX_LIMIT) {
      out.push({ limit: Math.min(MAX_LIMIT, rows - taken), offset: start + taken });
    }
    return out;
  });

  /** The first window with the query: the whole page on a desk. */
  const params = computed<ServerTableParams>(() => ({ ...query.value, ...windows.value[0] }));

  /** A page emptied by changes elsewhere steps back to the last page that still has rows. */
  function followResult(result: Readonly<Ref<PageShape | undefined>>): void {
    watch(result, (now) => {
      if (now && now.rows.length === 0 && now.total > 0 && now.offset >= now.total) {
        goToPage(Math.ceil(now.total / pageSize.value) - 1);
      }
    });
  }

  return {
    search,
    page,
    pageSize,
    sort,
    dir,
    filtered,
    query,
    windows,
    params,
    goToPage,
    setPageSize,
    setSort,
    loadMore,
    restart,
    followResult,
  };
}
