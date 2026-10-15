// `useServerTable(op, options)`: a list query of printing followed live behind a server-side DataTable
// (the print queue). Search, sort, page and page size are the server's;
// anything that changes WHICH rows there are (a search, a sort, a page size, the page's filters) starts
// again from the first page. On a phone «Load more» grows the rows from the first one: they are asked in
// WINDOWS of at most `MAX_LIMIT` rows (the server refuses a bigger `limit`), each its own `useLive`
// subscription, merged into one page for the table (the rows in order, the query's total, «loading» until
// every window answered, the first error). A window less releases its subscription. A page emptied by
// changes elsewhere steps back to the last page that still has rows.
import {
  type ApiError,
  type InputOf,
  type LiveStatus,
  type OpName,
  type OutputOf,
  type UseLive,
  useLive,
  useLiveClient,
} from '@erplora/ui/sdk';
import { computed, type EffectScope, effectScope, onScopeDispose, ref, shallowRef, watch } from 'vue';

import type { SortDir } from '../operations';

/** The server's cap on a list's `limit` (`schemas.PageIn.limit`). */
export const MAX_LIMIT = 100;

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
  /** The longest search the list takes (`max_length` of its schema's `search`). */
  maxSearch: number;
  /** The page's own filters, as the list query takes them: sent with every window. */
  filters?: () => object;
  /** The page's filters narrow the rows (the empty state says «No results»). */
  narrowed?: () => boolean;
}

interface PageOut {
  rows: unknown[];
  total: number;
  limit: number;
  offset: number;
}

/** `rows` rows from row `start`, cut in windows of at most `size`. */
export function windowsOf(start: number, rows: number, size: number): ListWindow[] {
  const out: ListWindow[] = [];
  for (let from = 0; from < rows; from += size) out.push({ limit: Math.min(size, rows - from), offset: start + from });
  return out;
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

  const query = computed(() => ({
    ...(JSON.parse(pageFilters.value) as object),
    ...(text.value.trim() ? { search: text.value.trim().slice(0, options.maxSearch) } : {}),
    sort: sort.value,
    dir: dir.value,
  }));

  const windows = computed(() => windowsOf(page.value * pageSize.value, pageSize.value * windowPages.value, MAX_LIMIT));

  /** The params of window `index`; while it is being let go, the last ones it had. */
  function paramsOf(index: number): () => InputOf<Op> {
    let last: ListWindow = windows.value[index] ?? { limit: 1, offset: 0 };
    return () => {
      last = windows.value[index] ?? last;
      return { ...query.value, ...last } as InputOf<Op>;
    };
  }

  // The client is taken in setup: a window opened later (in the watcher) has no component to inject it from.
  const client = useLiveClient();
  const follow = (params: () => InputOf<Op>) => useLive(op as never, params as never, { client } as never) as unknown as UseLive<PageOut>;
  const first = follow(paramsOf(0));
  const extra = shallowRef<UseLive<PageOut>[]>([]);
  const parent = effectScope();
  const scopes: EffectScope[] = [];

  watch(
    () => windows.value.length,
    (wanted) => {
      while (scopes.length < wanted - 1) {
        const params = paramsOf(scopes.length + 1);
        const scope = parent.run(() => effectScope())!;
        const live = scope.run(() => follow(params))!;
        scopes.push(scope);
        extra.value = [...extra.value, live];
      }
      while (scopes.length > Math.max(wanted - 1, 0)) {
        scopes.pop()?.stop();
        extra.value = extra.value.slice(0, -1);
      }
    },
    { immediate: true },
  );
  onScopeDispose(() => parent.stop());

  const all = computed(() => [first, ...extra.value]);

  const data = computed(() => {
    const head = first.data.value;
    if (!head) return undefined;
    const rows: unknown[] = [];
    for (const live of all.value) {
      const answer = live.data.value;
      if (!answer) break;
      rows.push(...answer.rows);
    }
    const shown = windows.value;
    return {
      rows,
      total: head.total,
      limit: shown.reduce((sum, window) => sum + window.limit, 0),
      offset: shown[0]?.offset ?? 0,
    } as OutputOf<Op>;
  });

  const status = computed<LiveStatus>(() => {
    const states = all.value.map((live) => live.status.value);
    if (states.includes('reconnecting')) return 'reconnecting';
    if (states.includes('error')) return 'error';
    if (states.includes('loading')) return 'loading';
    return 'live';
  });

  const error = computed(() => all.value.map((live) => live.error.value).find((e): e is ApiError => !!e) ?? null);

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
    status,
    error,
    /** Reopens the stream so the server runs every window again. */
    refresh: () => first.refresh(),
  };
}
