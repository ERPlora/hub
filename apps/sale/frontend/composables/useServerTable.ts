// `useServerTable(op, options)`: a list query of the sale app followed live behind a server-side
// DataTable (the back-office lists: quick notes, departments). Search, sort, page and page size are the
// server's; anything that changes WHICH rows there are (a search, a sort, a page size) starts again from
// the first page. On a phone «Load more» grows the rows from the first one: they are asked in WINDOWS of
// at most `MAX_LIMIT` rows (the server refuses a bigger `limit`), each its own `useLive` subscription,
// merged into one page for the table (the rows in order, the query's total, «loading» until every window
// answered, the first error). A window less releases its subscription. A page emptied by changes
// elsewhere steps back to the last page that still has rows.
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

/** The largest page the server serves (`schemas.PageIn.limit`). */
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

  const filtered = computed(() => text.value.trim() !== '');

  /** Search and sort, what every window shares. */
  const query = computed(() => ({
    ...(text.value.trim() ? { search: text.value.trim().slice(0, options.maxSearch) } : {}),
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

  // ── One live subscription per window ───────────────────────────────────────────────────────────
  /** The params of window `index`; while it is being let go, the last ones it had. */
  function paramsOf(index: number): () => InputOf<Op> {
    let last: ListWindow = windows.value[index] ?? { limit: 1, offset: 0 };
    return () => {
      last = windows.value[index] ?? last;
      return { ...query.value, ...last } as InputOf<Op>;
    };
  }

  // The client is taken in setup: a window added later (in the watcher) has no component to inject it
  // from. `useLive` is typed per operation; here the operation is generic, so its params pass as such.
  const client = useLiveClient();
  const follow = (params: () => InputOf<Op>) =>
    useLive(op as never, params as never, { client } as never) as unknown as UseLive<OutputOf<Op>>;
  const first = follow(paramsOf(0));
  const extra = shallowRef<UseLive<OutputOf<Op>>[]>([]);
  const parent = effectScope();
  const scopes: EffectScope[] = [];

  watch(
    () => windows.value.length,
    (count) => {
      while (scopes.length < count - 1) {
        const getter = paramsOf(scopes.length + 1);
        const scope = parent.run(() => effectScope())!;
        const live = scope.run(() => follow(getter))!;
        scopes.push(scope);
        extra.value = [...extra.value, live];
      }
      while (scopes.length > Math.max(count - 1, 0)) {
        scopes.pop()?.stop();
        extra.value = extra.value.slice(0, -1);
      }
    },
    { immediate: true },
  );
  onScopeDispose(() => parent.stop());

  const all = computed(() => [first, ...extra.value]);

  const data = computed(() => {
    const pages = all.value.map((live) => live.data.value as PageOut | undefined);
    const head = pages[0];
    if (!head) return undefined;
    const rows: unknown[] = [];
    for (const one of pages) {
      if (!one) break;
      rows.push(...one.rows);
    }
    const shown = windows.value;
    return {
      rows,
      total: head.total,
      limit: shown.reduce((sum, window) => sum + window.limit, 0),
      offset: shown[0]?.offset ?? head.offset,
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
    status,
    error,
    /** Reopens the stream so the server runs every window again. */
    refresh: () => first.refresh(),
  };
}
