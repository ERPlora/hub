// A live list bigger than what one query takes: the server answers at most 100 rows a query
// (`PageIn.limit`), and a phone that pressed «Load more» a few times shows more. One live query per
// window of `useListState` (each ≤ 100 rows, in its own effect scope), merged into ONE page for the
// DataTable: rows in order, the total of the first. Every row on screen stays live.
import { type ApiError, type LiveStatus, type OutputOf, type UseLive, useLive, useLiveClient } from '@erplora/ui/sdk';
import { computed, effectScope, type EffectScope, onScopeDispose, type Ref, shallowRef, watch } from 'vue';

import type { ListWindow } from './useListState';

/** The customer app's paginated lists (the four sections, and a card's activity, purchases and orders). */
export type ListOp =
  | 'customer.customer.list'
  | 'customer.group.list'
  | 'customer.tag.list'
  | 'customer.field.list'
  | 'customer.activity.list'
  | 'customer.purchase.list'
  | 'customer.order.list';

interface Piece<Op extends ListOp> {
  scope: EffectScope;
  live: UseLive<OutputOf<Op>>;
}

interface PageShape {
  rows: unknown[];
  total: number;
  limit: number;
  offset: number;
}

export function useLiveList<Op extends ListOp>(op: Op, base: () => object, windows: Readonly<Ref<ListWindow[]>>) {
  const pieces = shallowRef<Piece<Op>[]>([]);
  // Windows added later («Load more») are created outside setup, where nothing can be injected.
  const client = useLiveClient();

  function piece(index: number): Piece<Op> {
    const scope = effectScope();
    // Each window reads its own limit and offset: a new page or search re-subscribes it in place.
    const params = () => ({ ...base(), ...windows.value[index] });
    const live = scope.run(() => useLive(op, params as never, { client })) as UseLive<OutputOf<Op>>;
    return { scope, live };
  }

  // Pieces come and go with the number of windows; the first one lives as long as the page.
  watch(
    () => windows.value.length,
    (count) => {
      const next = [...pieces.value];
      while (next.length < count) next.push(piece(next.length));
      while (next.length > count) next.pop()?.scope.stop();
      pieces.value = next;
    },
    { immediate: true },
  );
  onScopeDispose(() => {
    for (const p of pieces.value) p.scope.stop();
  });

  const data = computed<OutputOf<Op> | undefined>(() => {
    const parts = pieces.value.map((p) => p.live.data.value as PageShape | undefined);
    const first = parts[0];
    if (!first) return undefined;
    const rows: unknown[] = [];
    let limit = 0;
    for (const part of parts) {
      if (!part) break;
      rows.push(...part.rows);
      limit += part.limit;
    }
    return { ...first, rows, limit } as OutputOf<Op>;
  });

  const error = computed<ApiError | null>(() => pieces.value.map((p) => p.live.error.value).find((e) => e !== null) ?? null);
  const status = computed<LiveStatus>(() => {
    const all = pieces.value.map((p) => p.live.status.value);
    if (all.includes('reconnecting')) return 'reconnecting';
    if (all.includes('error')) return 'error';
    if (all.includes('loading')) return 'loading';
    return 'live';
  });

  return { data, status, error, refresh: () => pieces.value[0]?.live.refresh() };
}
