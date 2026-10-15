// `useAllRows(op, query)`: every row of a live list the screen shows whole (the floor plan paints every
// table of its zone), read in windows of 100 — the server's cap on `limit` — through `useLiveList`: one
// window first, then as many as the first answer's total asks. A new query starts again from one window.
import { computed, ref, watch } from 'vue';

import { type ListOp, useLiveList } from './useLiveList';
import type { ListWindow } from './useServerTable';

/** The server's cap on a list's `limit` (`schemas.PageIn.limit`). */
export const WINDOW = 100;

export function useAllRows<Op extends ListOp>(op: Op, query: () => Record<string, unknown>) {
  const total = ref(0);
  const windows = computed<ListWindow[]>(() => {
    const count = Math.max(1, Math.ceil(total.value / WINDOW));
    return Array.from({ length: count }, (_, index) => ({ limit: WINDOW, offset: index * WINDOW }));
  });
  const list = useLiveList(op, query as never, () => windows.value);

  watch(
    () => JSON.stringify(query()),
    () => {
      total.value = 0;
    },
  );
  watch(
    () => (list.data.value as { total?: number } | undefined)?.total,
    (now) => {
      if (now !== undefined) total.value = now;
    },
  );

  type Row = NonNullable<typeof list.data.value> extends { rows: (infer R)[] } ? R : never;
  const rows = computed<Row[]>(() => ((list.data.value as { rows?: Row[] } | undefined)?.rows ?? []) as Row[]);
  return { rows, status: list.status, error: list.error, refresh: list.refresh };
}
