import { toastError, toastInfo } from '@erplora/ui/shell';

import type { OrderOut } from '../../operations';
import { useT } from '../useT';
import type { CheckWrites } from './useCheckWrites';
import type { TillOptions } from './useTill';

export function useFollowCheck(writes: CheckWrites, options: Pick<TillOptions, 'onJoined'>) {
  const { order, check, pendingLabel, inFlight, afterWrites, accept, release } = writes;
  const t = useT();

  function resume(orderId: string): void {
    order.value = null;
    pendingLabel.value = '';
    check.remember(orderId);
  }

  function follow(next: OrderOut): void {
    if (next.id !== check.id.value) return;
    if (next.status !== 'open') {
      // A write of this screen in flight answers first (a void or a charge of its own closes the check itself, and
      // then this is somebody else's check); whatever it left is decided once it has.
      if (inFlight.value > 0) {
        afterWrites(() => follow(next));
        return;
      }
      // Joined with another check (Tables' «Merge», here or on another device): nothing was closed, its lines
      // are in the one that stays, and the till shows that one.
      const joined = next.merged_into_id;
      if (joined) {
        resume(joined);
        options.onJoined?.(joined);
        toastInfo(t('sale.pos.checkJoined'));
        return;
      }
      release();
      toastError(t('sale.pos.checkGone'));
      return;
    }
    accept(next);
  }

  function gone(): void {
    if (!check.id.value) return;
    release();
    toastError(t('sale.pos.checkGone'));
  }

  return { resume, follow, gone };
}
