// The check on screen and a write to it. The screen shows only what the operations answer — the check comes back
// whole from every write and from the live `sale.order.get` (`follow`), the newer version wins — so nothing about
// money is decided here. A refusal shows the server's own sentence; without a connection, that it is missing; any other
// failure nobody worded, the product's sentence for that action.
import { toastError } from '@erplora/ui/shell';
import { shallowRef } from 'vue';

import type { OrderOut } from '../../operations';
import { useT } from '../useT';
import { useCurrentCheck } from './useCurrentCheck';
import type { WriteResult } from './useTill';
import { useWordsOf } from './useWordsOf';
import { useWriteQueue } from './useWriteQueue';

export type CheckWrites = ReturnType<typeof useCheckWrites>;

export async function toast(result: Promise<WriteResult>): Promise<void> {
  const done = await result;
  if (!done.ok) toastError(done.message);
}

export function useCheckWrites() {
  const t = useT();
  const check = useCurrentCheck();
  const { inFlight, busy, serial, afterWrites } = useWriteQueue();

  const wordsOf = useWordsOf();

  const order = shallowRef<OrderOut | null>(null);
  const pendingLabel = shallowRef('');

  function release(): void {
    check.forget();
    order.value = null;
    pendingLabel.value = '';
  }

  /** The check as a write answered it. */
  function accept(next: OrderOut): void {
    if (next.status !== 'open') {
      release();
      return;
    }
    const current = order.value;
    if (!current || current.id !== next.id || next.version >= current.version) order.value = next;
  }

  /** Runs a write on the check; on a refusal, its words (or `fallbackKey`'s when nobody answered). */
  function attempt(write: (orderId: string) => Promise<OrderOut>, fallbackKey: string): Promise<WriteResult> {
    return serial(async () => {
      const id = order.value?.id ?? check.id.value;
      if (!id) return { ok: false, message: t(fallbackKey) };
      try {
        accept(await write(id));
        return { ok: true };
      } catch (error) {
        return { ok: false, message: wordsOf(error, fallbackKey) };
      }
    });
  }

  return { check, order, pendingLabel, inFlight, busy, serial, afterWrites, wordsOf, release, accept, attempt };
}
