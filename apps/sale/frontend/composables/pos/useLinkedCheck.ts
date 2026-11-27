// `useLinkedCheck()`: the check the till's address names (`/sale/pos?order=<id>`, Appointments' «Charge», SALE-F26).
// It is `pending` from the moment the address names it until the till shows it (`shown`), so the page shows only that
// it is opening it: nothing is sold on, or charged from, another check meanwhile. It is read once the till can show it
// (`ready`): an open one goes on the till (`open`, as «Open checks» does); one no longer open, gone or refused stays
// pending with its `error` until the person leaves it (`dismiss`), which gives the till back as it was.
import { ApiError, useCommand } from '@erplora/ui/sdk';
import { computed, type ComputedRef, type Ref, shallowRef, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { refusal } from '../../lib/refusal';
import type { OrderOut } from '../../operations';
import { useT } from '../useT';

/** The till's own address: Ionic keeps the till alive behind other pages, whose `order` may mean a sort. */
const POS_PATH = '/sale/pos';

export interface LinkedCheckOptions {
  /** The till can show a check: its settings are read. */
  ready: () => boolean;
  /** The check the till shows whole (its lines and its customer read); `null` with none. */
  shown: () => string | null;
  /** Puts the open check on the till. */
  open: (check: OrderOut) => void;
}

export interface LinkedCheck {
  /** The check the address named is not on the till yet, or could not be opened (`error`). */
  pending: ComputedRef<boolean>;
  /** Why it could not be opened; `null` while it is on its way. */
  error: Readonly<Ref<string | null>>;
  /** Leaves it: the till as it was. */
  dismiss(): void;
}

export function useLinkedCheck(options: LinkedCheckOptions): LinkedCheck {
  const t = useT();
  const route = useRoute();
  const router = useRouter();
  const read = useCommand('sale.order.get');
  /** Each time the address names a check, a new ask: an answer to an older one is dropped. */
  const asked = shallowRef<{ id: string } | null>(null);
  const error = shallowRef<string | null>(null);

  function dismiss(): void {
    asked.value = null;
    error.value = null;
  }

  async function fetch(ask: { id: string }): Promise<void> {
    try {
      const check = await read.run({ order_id: ask.id });
      if (asked.value !== ask) return;
      if (check.status === 'open') options.open(check);
      else error.value = t('sale.pos.linkedCheckGone');
    } catch (failed) {
      if (asked.value !== ask) return;
      const gone = failed instanceof ApiError && failed.status === 404;
      const fallback = t('sale.pos.linkedCheckGone');
      error.value = gone ? fallback : (refusal(failed, fallback)?.message ?? fallback);
    }
  }

  watch(
    () => (route.path === POS_PATH ? route.query.order : undefined),
    (id) => {
      if (typeof id !== 'string' || !id) return;
      error.value = null;
      asked.value = { id };
      void router.replace({ path: route.path, query: {} });
    },
    { immediate: true },
  );
  watch(
    () => (options.ready() ? asked.value : null),
    (ask) => {
      if (ask) void fetch(ask);
    },
    { immediate: true },
  );
  watch(
    () => !!asked.value && options.shown() === asked.value.id,
    (done) => {
      if (done) dismiss();
    },
    { immediate: true },
  );

  return { pending: computed(() => asked.value !== null), error, dismiss };
}
