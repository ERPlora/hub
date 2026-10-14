// The state of a server-side customer list (the demo's list, made reusable by the four sections):
// search, sort, page and page size are the server's. Anything that changes WHICH rows there are (a
// search, a filter, a sort, a page size) starts again from the first page. On a phone «Load more»
// grows the live window from the first row, so every row on screen stays live; a desk pages one page
// at a time. The server takes at most 100 rows a query (`PageIn`): a window bigger than that is cut
// in `windows` of ≤ 100, each its own live query (`useLiveList`). The customer queries sort with
// `sort` + `descending`.
import { computed, type Ref, ref, watch } from 'vue';

export type SortDir = 'asc' | 'desc';

export interface ListStateOptions {
  sort: string;
  pageSize?: number;
}

/** The most rows a list query takes (`PageIn.limit`). */
export const MAX_LIMIT = 100;

/** What every window of the list asks for: the search and the sort. */
export interface ListBase {
  search?: string;
  sort: string;
  descending: boolean;
}

/** A piece of the window: at most `MAX_LIMIT` rows. */
export interface ListWindow {
  limit: number;
  offset: number;
}

export type ListParams = ListBase & ListWindow;

/** `count` rows from `start`, cut in pieces of at most `MAX_LIMIT` (what one query takes). */
export function windowsOf(start: number, count: number): ListWindow[] {
  const out: ListWindow[] = [];
  const end = start + count;
  for (let offset = start; offset < end; offset += MAX_LIMIT) out.push({ limit: Math.min(MAX_LIMIT, end - offset), offset });
  return out;
}

interface PageShape {
  rows: readonly unknown[];
  total: number;
  offset: number;
}

export function useListState(options: ListStateOptions) {
  const text = ref('');
  /** 0-based, as the DataTable counts. */
  const page = ref(0);
  const pageSize = ref(options.pageSize ?? 50);
  /** Pages the live window holds from `page` on: 1 on a desk; each «Load more» on a phone adds one. */
  const windowPages = ref(1);
  const sort = ref(options.sort);
  const dir = ref<SortDir>('asc');
  const narrowed = ref(false);

  function goToPage(n: number): void {
    page.value = n;
    windowPages.value = 1;
  }

  /** `v-model:search` of the DataTable. */
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

  /** The page changed its own filters: from the first page again. */
  function restart(state: { narrowed: boolean }): void {
    narrowed.value = state.narrowed;
    goToPage(0);
  }

  const filtered = computed(() => text.value.trim() !== '' || narrowed.value);

  const base = computed<ListBase>(() => ({
    ...(text.value.trim() ? { search: text.value.trim() } : {}),
    sort: sort.value,
    descending: dir.value === 'desc',
  }));

  /** The rows on screen, from `page` on, cut in pieces the server takes. */
  const windows = computed<ListWindow[]>(() => windowsOf(page.value * pageSize.value, pageSize.value * windowPages.value));

  /** The first window with the base: one page on a desk. */
  const params = computed<ListParams>(() => ({ ...base.value, ...windows.value[0] }));

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
    base,
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
