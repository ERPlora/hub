// `useLiveAllRows(op, query)`: every row of a live list a screen needs whole (a sheet to print), read in windows of a
// hundred, the server's cap on a list's `limit`. The first window is subscribed in setup, so it pauses with the page as
// any `useLive`; the others, as many as its total asks, in effect scopes of their own, dropped when the total shrinks.
// The rows are joined in order as long as each window has come, so they never jump.
import type { ApiError, InputOf, LiveStatus, OpName, OutputOf } from '@erplora/ui/sdk';
import { useLive, useLiveClient } from '@erplora/ui/sdk';
import { computed, effectScope, type EffectScope, onScopeDispose, shallowRef, watch } from 'vue';

/** The server's cap on a list's `limit`. */
export const WINDOW = 100;

interface Page<Row> {
  rows: Row[];
  total: number;
}

type RowOf<Op extends OpName> = OutputOf<Op> extends Page<infer Row> ? Row : never;
type Query<Op extends OpName> = Omit<InputOf<Op>, 'limit' | 'offset'>;

export function useLiveAllRows<Op extends OpName>(op: Op, query: () => Query<Op> = () => ({}) as Query<Op>) {
  const client = useLiveClient();
  const paramsOf = (index: number) => () => ({ ...query(), limit: WINDOW, offset: index * WINDOW }) as InputOf<Op>;
  const pageOf = (live: { data: { value: unknown } }) => live.data.value as Page<RowOf<Op>> | undefined;

  const first = useLive(op, paramsOf(0));
  const extras = shallowRef<{ scope: EffectScope; live: ReturnType<typeof useLive<Op>> }[]>([]);
  const total = computed(() => pageOf(first)?.total ?? 0);

  watch(
    () => Math.max(0, Math.ceil(total.value / WINDOW) - 1),
    (count) => {
      const now = [...extras.value];
      while (now.length > count) now.pop()?.scope.stop();
      while (now.length < count) {
        const scope = effectScope();
        const live = scope.run(() => useLive(op, paramsOf(now.length + 1), { client }))!;
        now.push({ scope, live });
      }
      extras.value = now;
    },
  );
  onScopeDispose(() => {
    for (const extra of extras.value) extra.scope.stop();
  });

  const all = computed(() => [first, ...extras.value.map((extra) => extra.live)]);
  const arrived = computed(() => {
    const pages: Page<RowOf<Op>>[] = [];
    for (const live of all.value) {
      const part = pageOf(live);
      if (!part) break;
      pages.push(part);
    }
    return pages;
  });

  const rows = computed<RowOf<Op>[]>(() => arrived.value.flatMap((part) => part.rows));
  const complete = computed(() => arrived.value.length > 0 && arrived.value.length === all.value.length);

  const status = computed<LiveStatus>(() => {
    const statuses = all.value.map((live) => live.status.value);
    if (statuses.includes('reconnecting')) return 'reconnecting';
    if (statuses.includes('error')) return 'error';
    return first.status.value === 'loading' ? 'loading' : 'live';
  });
  const error = computed<ApiError | null>(() => all.value.map((live) => live.error.value).find((e) => e !== null) ?? null);

  return { rows, total, complete, status, error, refresh: first.refresh };
}
