// A server-side list followed live as ONE page, whatever its window: the API serves at most 100 rows
// per query, so each window of useServerTable (≤ 100 rows) is its own `useLive` subscription and their
// rows are joined in order. The first window lives with the page (Ionic's view lifecycle pauses it);
// a phone's «Load more» past 100 rows adds the next ones in their own effect scope, and fewer windows
// stop the extra scopes. Status and error are the list's: loading while any window has no result,
// the first error otherwise.
import { type ApiError, type InputOf, type LiveStatus, type OpName, type OutputOf, useLive, useLiveClient, type UseLive } from '@erplora/ui/sdk';
import { computed, type ComputedRef, effectScope, type EffectScope, onScopeDispose, type Ref, shallowRef, watch } from 'vue';

import type { RowWindow } from './useServerTable';

interface PageOf<R> {
  rows: R[];
  total: number;
  limit: number;
  offset: number;
}

type ListOp = {
  [Op in OpName]: OutputOf<Op> extends PageOf<unknown> ? (InputOf<Op> extends { limit?: number; offset?: number } ? Op : never) : never;
}[OpName];

type Filters<Op extends ListOp> = Omit<InputOf<Op>, 'limit' | 'offset'>;

export interface LiveList<Op extends ListOp> {
  data: ComputedRef<OutputOf<Op> | undefined>;
  status: ComputedRef<LiveStatus>;
  error: ComputedRef<ApiError | null>;
  refresh: () => void;
}

export function useLiveList<Op extends ListOp>(op: Op, filters: () => Filters<Op>, windows: Readonly<Ref<RowWindow[]>>): LiveList<Op> {
  const client = useLiveClient();
  /** The params of window `index`; a window being dropped keeps its last one until its scope stops. */
  const paramsOf = (index: number): InputOf<Op> => {
    const window = windows.value[index] ?? windows.value.at(-1) ?? { limit: 50, offset: 0 };
    return { ...filters(), limit: window.limit, offset: window.offset } as InputOf<Op>;
  };

  const first = useLive(op, () => paramsOf(0)) as UseLive<OutputOf<Op>>;
  const extra = shallowRef<Array<{ scope: EffectScope; live: UseLive<OutputOf<Op>> }>>([]);

  watch(
    () => windows.value.length,
    (count) => {
      const now = [...extra.value];
      while (now.length > Math.max(0, count - 1)) now.pop()?.scope.stop();
      while (now.length < count - 1) {
        const index = now.length + 1;
        const scope = effectScope();
        const live = scope.run(() => useLive(op, () => paramsOf(index), { client }) as UseLive<OutputOf<Op>>);
        if (live) now.push({ scope, live });
      }
      extra.value = now;
    },
    { immediate: true },
  );
  onScopeDispose(() => {
    for (const window of extra.value) window.scope.stop();
  });

  const all = computed(() => [first, ...extra.value.map((window) => window.live)]);

  const data = computed(() => {
    const head = first.data.value as PageOf<unknown> | undefined;
    if (!head) return undefined;
    const rows = [...head.rows, ...extra.value.flatMap((window) => (window.live.data.value as PageOf<unknown> | undefined)?.rows ?? [])];
    const limit = windows.value.reduce((sum, window) => sum + window.limit, 0);
    return { ...head, rows, limit } as OutputOf<Op>;
  });

  const error = computed(() => all.value.map((live) => live.error.value).find((value) => value !== null) ?? null);

  const status = computed<LiveStatus>(() => {
    const states = all.value.map((live) => live.status.value);
    if (states.includes('reconnecting')) return 'reconnecting';
    if (states.includes('error')) return 'error';
    return states.includes('loading') ? 'loading' : 'live';
  });

  return { data, status, error, refresh: () => first.refresh() };
}
