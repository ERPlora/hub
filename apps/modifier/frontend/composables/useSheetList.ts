// `useSheetList(op, query)`: the lists of a group's sheet (its options, what it
// applies to), followed live: the first 20, «Load more» 20 more each time.
// The server gives at most 100 rows at once (`PageIn`), so past 100 the rows are windows of 100, each
// its own live subscription (`useLiveList`).
import type { InputOf, OutputOf } from '@erplora/ui/sdk';
import { computed, ref } from 'vue';

import { type ListOp, useLiveList } from './useLiveList';
import { MAX_LIMIT, type ListWindow } from './useServerTable';

/** Rows a sheet shows first and adds with each «Load more». */
export const SHEET_STEP = 20;

type Row<Op extends ListOp> = OutputOf<Op> extends { rows: Array<infer R> } ? R : never;

export function useSheetList<Op extends ListOp>(op: Op, query: () => Omit<InputOf<Op>, 'limit' | 'offset'>) {
  const shown = ref(SHEET_STEP);
  const windows = computed<ListWindow[]>(() => {
    const out: ListWindow[] = [];
    for (let taken = 0; taken < shown.value; taken += MAX_LIMIT) out.push({ limit: Math.min(MAX_LIMIT, shown.value - taken), offset: taken });
    return out;
  });
  const { data, status, error, refresh } = useLiveList(op, query, () => windows.value);
  const rows = computed(() => ((data.value as { rows?: Row<Op>[] } | undefined)?.rows ?? []) as Row<Op>[]);
  const total = computed(() => (data.value as { total?: number } | undefined)?.total ?? 0);
  const hasMore = computed(() => rows.value.length < total.value);

  function loadMore(): void {
    shown.value += SHEET_STEP;
  }

  return { data, status, error, refresh, rows, total, hasMore, loadMore };
}
