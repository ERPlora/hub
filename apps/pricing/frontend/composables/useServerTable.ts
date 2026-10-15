// The state of a server-side list (the demo's list, made reusable by the pricing tables): search,
// sort, page and page size are the server's. Anything that changes WHICH rows there are (a search, a
// filter, a sort, a page size) starts again from the first page. On a phone «Load more» grows the rows
// from the first one; they are asked in WINDOWS of at most 100 (`MAX_LIMIT`: the server refuses a
// bigger `limit`), each its own live subscription (`useLiveList`), so every row on screen stays live.
// A desk pages one page at a time.
import { computed, type Ref, ref, watch } from 'vue';

import type { SortDir } from '../operations';

/** The largest page the server serves (`schemas.PageIn.limit`). */
export const MAX_LIMIT = 100;
/** The longest search the server takes (`search` of the list schemas). */
export const MAX_SEARCH = 120;

/** One live window of rows. */
export interface ListWindow {
  limit: number;
  offset: number;
}

export interface ServerTableOptions {
  /** Column the server sorts by at first. */
  sort: string;
  dir?: SortDir;
  pageSize?: number;
}

/** What the list query takes from the table (the page adds its filters). */
export interface ServerTableParams {
  search?: string;
  sort: string;
  dir: SortDir;
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
  const sort = ref(options.sort);
  const dir = ref<SortDir>(options.dir ?? 'asc');
  /** The page's own filters narrow the rows (set by `restart`). */
  const narrowed = ref(false);

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

  /** The page changed its filters: from the first page again, and say whether they narrow the rows. */
  function restart(state: { narrowed: boolean }): void {
    narrowed.value = state.narrowed;
    goToPage(0);
  }

  const filtered = computed(() => text.value.trim() !== '' || narrowed.value);

  /** Search and sort, what every window shares. */
  const query = computed(() => ({
    search: text.value.trim().slice(0, MAX_SEARCH) || undefined,
    sort: sort.value,
    dir: dir.value,
  }));

  /** The rows on screen as windows of at most `MAX_LIMIT`, from the page's first row. */
  const windows = computed<ListWindow[]>(() => {
    const start = page.value * pageSize.value;
    const rows = pageSize.value * windowPages.value;
    const out: ListWindow[] = [];
    for (let from = 0; from < rows; from += MAX_LIMIT) out.push({ limit: Math.min(MAX_LIMIT, rows - from), offset: start + from });
    return out;
  });

  /** The first window with the query: the params of a list that is one window. */
  const params = computed<ServerTableParams>(() => ({ ...query.value, ...windows.value[0] }));

  /** A page emptied by changes elsewhere steps back to the last page that still has rows. */
  function followResult(result: Readonly<Ref<PageShape | undefined>>): void {
    watch(result, (now) => {
      if (now && now.rows.length === 0 && now.total > 0 && now.offset >= now.total) {
        goToPage(Math.ceil(now.total / pageSize.value) - 1);
      }
    });
  }

  return { search, page, pageSize, sort, dir, filtered, query, windows, params, goToPage, setPageSize, setSort, loadMore, restart, followResult };
}
