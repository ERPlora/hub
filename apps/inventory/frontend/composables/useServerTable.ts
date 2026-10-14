// The state of an inventory list on the server (products, movements, categories, low stock): search,
// sort, page and page size are the server's; the sort travels as the API takes it («name», «-name»).
// Anything that changes WHICH rows there are (a search, a filter, a sort, a page size) starts again
// from the first page. On a phone «Load more» grows ONE live window from the first row, so every row
// on screen stays live; a desk pages one page at a time. The API serves at most 100 rows per query
// (`PageIn.limit` ≤ 100), so the window is cut into `windows` of at most 100 rows, each its own live
// query (useLiveList joins them).
import type { DataTableSort, DataTableSortDir } from '@erplora/ui/components';
import { computed, type Ref, ref, watch } from 'vue';

export interface ServerTableOptions<S extends string> {
  /** The API's sort at first: a column, `-` in front to reverse it. */
  sort: S;
  pageSize?: number;
}

/** Rows the API serves in one query (`PageIn.limit` ≤ 100). */
export const MAX_ROWS = 100;

export interface ServerTableParams<S extends string = string> {
  search?: string;
  /** The list's own sorts; a column the table offers as sortable is one of them. */
  sort: S;
}

/** One live query of the window: at most `MAX_ROWS` rows. */
export interface RowWindow {
  limit: number;
  offset: number;
}

/** The part of a result page the table needs to step back from an emptied page. */
interface PageShape {
  rows: readonly unknown[];
  total: number;
  offset: number;
}

export function useServerTable<S extends string>(options: ServerTableOptions<S>) {
  const text = ref('');
  /** 0-based, as the DataTable counts. */
  const page = ref(0);
  const pageSize = ref(options.pageSize ?? 50);
  /** Pages the live window holds from `page` on: 1 on a desk; each «Load more» on a phone adds one. */
  const windowPages = ref(1);
  const sort = ref<S>(options.sort) as Ref<S>;
  /** The page's own filters narrow the rows (set by `restart`). */
  const narrowed = ref(false);

  const sortKey = computed(() => sort.value.replace(/^-/, ''));
  const sortDir = computed<DataTableSortDir>(() => (sort.value.startsWith('-') ? 'desc' : 'asc'));

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

  function setSort(next: DataTableSort): void {
    // The table only offers the columns the page declared sortable, all of them sorts of the list.
    sort.value = (next.dir === 'desc' ? `-${next.sort}` : next.sort) as S;
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

  const params = computed<ServerTableParams<S>>(() => ({
    ...(text.value.trim() ? { search: text.value.trim() } : {}),
    sort: sort.value,
  }));

  /** The rows on screen, from `page` on, as queries of at most `MAX_ROWS`. */
  const windows = computed<RowWindow[]>(() => {
    const start = page.value * pageSize.value;
    const count = pageSize.value * windowPages.value;
    const out: RowWindow[] = [];
    for (let taken = 0; taken < count; taken += MAX_ROWS) {
      out.push({ limit: Math.min(MAX_ROWS, count - taken), offset: start + taken });
    }
    return out;
  });

  /** A page emptied by changes elsewhere steps back to the last page that still has rows. */
  function followResult(result: Readonly<Ref<PageShape | undefined>>): void {
    watch(result, (now) => {
      if (now && now.rows.length === 0 && now.total > 0 && now.offset >= now.total) {
        goToPage(Math.ceil(now.total / pageSize.value) - 1);
      }
    });
  }

  return { search, page, pageSize, sortKey, sortDir, filtered, params, windows, goToPage, setPageSize, setSort, loadMore, restart, followResult };
}
