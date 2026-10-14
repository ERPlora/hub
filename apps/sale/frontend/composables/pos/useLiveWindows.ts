// `useLiveWindows(op, query, size)`: a list query followed live in WINDOWS of `size` rows (at most 100,
// the server's cap on `limit`), each window its own `useLive` subscription; «Load more» opens the next
// one. The rows come in order up to the first window still loading; the total is the first window's.
// A new query (another category, another search) starts again from one window: the others are let go
// (each lives in an effect scope of its own).
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

/** The server's cap on a list's `limit`. */
export const MAX_WINDOW = 100;

interface PageOut<Row> {
  rows: Row[];
  total: number;
}

export interface LiveWindows<Row> {
  rows: ComputedRef<Row[]>;
  /** Rows that match, in every window; `undefined` until the first answer. */
  total: ComputedRef<number | undefined>;
  /** There are rows past the windows open. */
  hasMore: ComputedRef<boolean>;
  status: ComputedRef<LiveStatus>;
  error: ComputedRef<ApiError | null>;
  /** Opens the next window (only once the last one answered). */
  loadMore(): void;
  /** Reopens the stream so the server runs every window again. */
  refresh(): void;
}

export function useLiveWindows<Op extends OpName, Row = unknown>(
  op: Op,
  query: () => object,
  size: number,
): LiveWindows<Row> {
  if (size < 1 || size > MAX_WINDOW) throw new RangeError(`A window holds 1 to ${MAX_WINDOW} rows, not ${size}.`);

  const count = shallowRef(1);
  watch(
    () => stableJson(query()),
    () => {
      count.value = 1;
    },
  );

  const paramsOf = (index: number) => () => ({ ...query(), limit: size, offset: index * size }) as InputOf<Op>;

  // The client is taken in setup: a window opened later (in the watcher) has no component to inject it from.
  const client = useLiveClient();
  const follow = (params: () => InputOf<Op>) =>
    useLive(op as never, params as never, { client } as never) as unknown as UseLive<PageOut<Row>>;
  const first = follow(paramsOf(0));
  const extra = shallowRef<UseLive<PageOut<Row>>[]>([]);
  const parent = effectScope();
  const scopes: EffectScope[] = [];

  watch(count, (wanted) => {
    while (scopes.length < wanted - 1) {
      const scope = parent.run(() => effectScope())!;
      const live = scope.run(() => follow(paramsOf(scopes.length + 1)))!;
      scopes.push(scope);
      extra.value = [...extra.value, live];
    }
    while (scopes.length > wanted - 1) {
      scopes.pop()?.stop();
      extra.value = extra.value.slice(0, -1);
    }
  });
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
  const hasMore = computed(() => total.value !== undefined && count.value * size < total.value);

  const status = computed<LiveStatus>(() => {
    const states = all.value.map((live) => live.status.value);
    if (states.includes('reconnecting')) return 'reconnecting';
    if (states.includes('error')) return 'error';
    if (states.includes('loading')) return 'loading';
    return 'live';
  });

  const error = computed(() => all.value.map((live) => live.error.value).find((e): e is ApiError => !!e) ?? null);

  function loadMore(): void {
    // A window asked for and not opened yet counts as loading too.
    if (count.value !== all.value.length) return;
    const last = all.value.at(-1);
    if (!hasMore.value || !last?.data.value || last.status.value === 'loading') return;
    count.value += 1;
  }

  return { rows, total, hasMore, status, error, loadMore, refresh: () => first.refresh() };
}
