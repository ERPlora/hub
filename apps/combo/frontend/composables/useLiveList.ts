// `useLiveList(op, query, windows)`: a list query followed live in WINDOWS of at most 100 rows (the
// server's cap on `limit`; `useServerTable().windows`), each its own `useLive` subscription, merged into
// one page for the DataTable: the rows in order (up to the first window still loading), the query's
// total, «loading» until every window answered, the first error. A window more is a subscription more;
// a window less releases its subscription (each lives in an effect scope of its own). (The tax app's.)
import { type ApiError, type InputOf, type LiveStatus, type OpName, type OutputOf, type UseLive, useLive, useLiveClient } from '@erplora/ui/sdk';
import { computed, type ComputedRef, type EffectScope, effectScope, onScopeDispose, shallowRef, watch } from 'vue';

import type { ListWindow } from './useServerTable';

/** What a list query answers: a page of rows. */
interface PageOut {
  rows: unknown[];
  total: number;
  limit: number;
  offset: number;
}

export interface LiveList<T> {
  data: ComputedRef<T | undefined>;
  status: ComputedRef<LiveStatus>;
  error: ComputedRef<ApiError | null>;
  /** Reopens the stream so the server runs every window again. */
  refresh(): void;
}

export function useLiveList<Op extends OpName>(
  op: Op,
  query: () => object,
  windows: () => readonly ListWindow[],
): LiveList<OutputOf<Op>> {
  /** The params of window `index`; while it is being let go, the last ones it had. */
  function paramsOf(index: number): () => InputOf<Op> {
    let last: ListWindow = windows()[index] ?? { limit: 1, offset: 0 };
    return () => {
      last = windows()[index] ?? last;
      return { ...query(), ...last } as InputOf<Op>;
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
    () => windows().length,
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
    for (const page of pages) {
      if (!page) break;
      rows.push(...page.rows);
    }
    const shown = windows();
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

  return { data, status, error, refresh: () => first.refresh() };
}
