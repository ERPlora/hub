// `useLiveList(op, query, windows)`: a server-side list that may show more rows than the server gives at
// once (100, `PageIn`): one live subscription per window of `useServerTable` — the first one made in
// setup (so it pauses with the page, as any `useLive`), the extra ones of a phone's «Load more» in
// effect scopes of their own, dropped when the windows shrink. The result joins the windows' rows in
// order, as long as each one has arrived, with the count of the first.
import type { ApiError, InputOf, LiveStatus, OutputOf } from '@erplora/ui/sdk';
import { useLive, useLiveClient } from '@erplora/ui/sdk';
import { computed, effectScope, type EffectScope, onScopeDispose, shallowRef, watch } from 'vue';

import type { ListWindow } from './useServerTable';

/** The payment lists that page on the server. */
export type ListOp = 'payment.payment.list' | 'payment.method.list';

type Query<Op extends ListOp> = Omit<InputOf<Op>, 'limit' | 'offset'>;

interface Extra<Op extends ListOp> {
  scope: EffectScope;
  live: ReturnType<typeof useLive<Op>>;
}

export function useLiveList<Op extends ListOp>(op: Op, query: () => Query<Op>, windows: () => readonly ListWindow[]) {
  const client = useLiveClient();
  const paramsOf = (index: number) => () => ({ ...query(), ...(windows()[index] ?? windows()[0]) }) as InputOf<Op>;

  const first = useLive(op, paramsOf(0));
  const extras = shallowRef<Extra<Op>[]>([]);

  watch(
    () => windows().length,
    (count) => {
      const now = [...extras.value];
      while (now.length > Math.max(0, count - 1)) now.pop()?.scope.stop();
      while (now.length < count - 1) {
        const scope = effectScope();
        const live = scope.run(() => useLive(op, paramsOf(now.length + 1), { client }))!;
        now.push({ scope, live });
      }
      extras.value = now;
    },
    { immediate: true },
  );
  onScopeDispose(() => {
    for (const extra of extras.value) extra.scope.stop();
  });

  const all = computed(() => [first, ...extras.value.map((extra) => extra.live)]);

  const data = computed<OutputOf<Op> | undefined>(() => {
    const head = first.data.value as { rows: unknown[]; total: number; offset: number } | undefined;
    if (!head) return undefined;
    const rows = [...head.rows];
    let limit = (windows()[0] ?? { limit: head.rows.length }).limit;
    for (const [index, extra] of extras.value.entries()) {
      const part = extra.live.data.value as { rows: unknown[] } | undefined;
      if (!part) break;
      rows.push(...part.rows);
      limit += windows()[index + 1]?.limit ?? 0;
    }
    return { rows, total: head.total, limit, offset: head.offset } as OutputOf<Op>;
  });

  const status = computed<LiveStatus>(() => {
    const statuses = all.value.map((live) => live.status.value);
    if (statuses.includes('reconnecting')) return 'reconnecting';
    if (statuses.includes('error')) return 'error';
    return first.status.value === 'loading' ? 'loading' : 'live';
  });

  const error = computed<ApiError | null>(() => all.value.map((live) => live.error.value).find((e) => e !== null) ?? null);

  return { data, status, error, refresh: first.refresh };
}
