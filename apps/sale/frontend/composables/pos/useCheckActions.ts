import { useCommand } from '@erplora/ui/sdk';
import { useSession } from '@erplora/ui/shell';

import { throughManager } from '../../lib/approval';
import { type CheckWrites, toast } from './useCheckWrites';
import type { WriteResult } from './useTill';

/** What `sale.order.void` answers for a check with something on it, to whoever may not void it. */
const NOT_ALLOWED = 'permission_denied';

export function useCheckActions({ order, check, pendingLabel, attempt, release }: CheckWrites) {
  const session = useSession();
  const label = useCommand('sale.order.set_label');
  const voidOrder = useCommand('sale.order.void');
  const voidOrdered = useCommand('sale.order.void_ordered');

  async function rename(next: string): Promise<void> {
    if (!order.value && !check.id.value) {
      pendingLabel.value = next;
      return;
    }
    await toast(attempt((id) => label.run({ order_id: id, label: next }), 'sale.pos.errorSavingTitle'));
  }

  async function park(next: string): Promise<WriteResult> {
    const done = await attempt((id) => label.run({ order_id: id, label: next }), 'sale.pos.parkCheckFailed');
    if (done.ok) release();
    return done;
  }

  async function voidCheck(): Promise<WriteResult> {
    // An empty check is whoever builds checks' (TABLE-F21); one with something on it, a manager's (SALE-F18).
    const done = await attempt(
      (id) =>
        throughManager(
          () => voidOrder.run({ order_id: id }),
          () => voidOrdered.run({ order_id: id }),
          { code: NOT_ALLOWED, may: session.can('sale.void_sale') },
        ),
      'sale.pos.discardCheckFailed',
    );
    if (done.ok) release();
    return done;
  }

  return { rename, park, voidCheck };
}
