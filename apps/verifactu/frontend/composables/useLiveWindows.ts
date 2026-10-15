// `useLiveWindows(op, query, size, plan?)`: THE engine of the verifactu app's live lists. A list query
// followed live in WINDOWS of at most `size` rows (never more than 100, the server's cap on `limit`: a
// bigger one is a 422), each window its own `useLive` subscription; the rows come merged in order up to
// the first window still loading, with the first window's total, one status and the first error.
// Left to itself it starts with one window, «Load more» opens the next one and a new
// query (another category, another search) starts again from one window. A table passes a `plan`
// instead: from which row and how many rows its pages show; they are cut in windows of at most `size`.
// A window less releases its subscription (each lives in an effect scope of its own).
import {
  type ApiError,
  type InputOf,
  type LiveStatus,
  type OpName,
  stableJson,
  type UseLive,
  useLive,
  useLiveClient,
} from '@erplora/ui/sdk';
import { computed, type ComputedRef, type EffectScope, effectScope, onScopeDispose, shallowRef, watch } from 'vue';

/** The server's cap on a list's `limit` (`schemas.PageIn.limit`). */
export const MAX_WINDOW = 100;

/** One live window of rows. */
export interface ListWindow {
  limit: number;
  offset: number;
}

/** The rows a table shows: from its page's first row, as many as its pages hold. */
export interface WindowPlan {
  start: () => number;
  rows: () => number;
}

interface PageOut<Row> {
  rows: Row[];
  total: number;
}

export interface LiveWindows<Row> {
  rows: ComputedRef<Row[]>;
  /** Rows that match, in every window; `undefined` until the first window answers. */
  total: ComputedRef<number | undefined>;
  /** There are rows past the windows open. */
  hasMore: ComputedRef<boolean>;
  /** The windows asked, in order. */
  windows: ComputedRef<ListWindow[]>;
  status: ComputedRef<LiveStatus>;
  error: ComputedRef<ApiError | null>;
  /** Opens the next window (only once the last one answered; a planned list grows by its plan). */
  loadMore(): void;
  /** Reopens the stream so the server runs every window again. */
  refresh(): void;
}

/** `rows` rows from row `start`, cut in windows of at most `size`. */
export function windowsOf(start: number, rows: number, size: number): ListWindow[] {
  const out: ListWindow[] = [];
  for (let from = 0; from < rows; from += size) out.push({ limit: Math.min(size, rows - from), offset: start + from });
  return out;
}

export function useLiveWindows<Op extends OpName, Row = unknown>(
  op: Op,
  query: () => object,
  size: number,
  plan?: WindowPlan,
): LiveWindows<Row> {
  if (size < 1 || size > MAX_WINDOW) throw new RangeError(`A window holds 1 to ${MAX_WINDOW} rows, not ${size}.`);

  /** Windows open when the list grows by «Load more». */
  const count = shallowRef(1);
  if (!plan) {
    watch(
      () => stableJson(query()),
      () => {
        count.value = 1;
      },
    );
  }

  const windows = computed<ListWindow[]>(() =>
    plan ? windowsOf(plan.start(), plan.rows(), size) : windowsOf(0, count.value * size, size),
  );

  /** The params of window `index`; while it is being let go, the last ones it had. */
  function paramsOf(index: number): () => InputOf<Op> {
    let last: ListWindow = windows.value[index] ?? { limit: 1, offset: 0 };
    return () => {
      last = windows.value[index] ?? last;
      return { ...query(), ...last } as InputOf<Op>;
    };
  }

  // The client is taken in setup: a window opened later (in the watcher) has no component to inject it
  // from. `useLive` is typed per operation; here the operation is generic, so its params pass as such.
  const client = useLiveClient();
  const follow = (params: () => InputOf<Op>) =>
    useLive(op as never, params as never, { client } as never) as unknown as UseLive<PageOut<Row>>;
  const first = follow(paramsOf(0));
  const extra = shallowRef<UseLive<PageOut<Row>>[]>([]);
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

  const rows = computed(() => {
    const out: Row[] = [];
    for (const live of all.value) {
      const page = live.data.value;
      if (!page) break;
      out.push(...page.rows);
    }
    return out;
  });

  const total = computed(() => first.data.value?.total);
  const hasMore = computed(() => {
    const last = windows.value.at(-1);
    return total.value !== undefined && !!last && last.offset + last.limit < total.value;
  });

  const status = computed<LiveStatus>(() => {
    const states = all.value.map((live) => live.status.value);
    if (states.includes('reconnecting')) return 'reconnecting';
    if (states.includes('error')) return 'error';
    if (states.includes('loading')) return 'loading';
    return 'live';
  });

  const error = computed(() => all.value.map((live) => live.error.value).find((e): e is ApiError => !!e) ?? null);

  function loadMore(): void {
    if (plan) return;
    // A window asked for and not opened yet counts as loading too.
    if (windows.value.length !== all.value.length) return;
    const last = all.value.at(-1);
    if (!hasMore.value || !last?.data.value || last.status.value === 'loading') return;
    count.value += 1;
  }

  return { rows, total, hasMore, windows, status, error, loadMore, refresh: () => first.refresh() };
}
