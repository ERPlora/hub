// A discount above the business's cap goes through the manager's door: directly for whoever holds
// `sale.discount_over_limit`, with a manager's approval on this very device for anybody else (BASE-F84), as an open
// price, a line sent to the kitchen voided and a check with something on it deleted do (`apps.py` `approvals`).
import { useCommand } from '@erplora/ui/sdk';
import { useSession } from '@erplora/ui/shell';

import { throughManager } from '../../lib/approval';
import type { OrderLineOut, OrderOut } from '../../operations';
import type { CheckWrites } from './useCheckWrites';
import type { TillOptions } from './useTill';

const OVER_LIMIT = 'sale.discount_over_limit';

export function useDiscounts({ attempt }: CheckWrites, options: Pick<TillOptions, 'settings'>) {
  const session = useSession();
  const lineDiscount = useCommand('sale.order.set_line_discount');
  const lineDiscountOver = useCommand('sale.order.set_line_discount_over_limit');
  const ticketDiscount = useCommand('sale.order.set_discount');
  const ticketDiscountOver = useCommand('sale.order.set_discount_over_limit');

  const canGoOver = () => session.can('sale.discount_over_limit');
  const overCap = (percent: string) => Number(percent) > (options.settings()?.max_discount_percent ?? 100);

  /** The ordinary door, or the manager's: above the cap, or when the server says it is above it (with a manager's
   *  approval for whoever does not hold the permission). */
  async function throughDoor(ordinary: () => Promise<OrderOut>, manager: () => Promise<OrderOut>, aboveCap: boolean): Promise<OrderOut> {
    if (aboveCap && canGoOver()) return manager();
    return throughManager(ordinary, manager, { code: OVER_LIMIT, may: canGoOver() });
  }

  const setLineDiscount = (line: OrderLineOut, percent: string) =>
    attempt((id) => {
      const input = { order_id: id, line_id: line.id, discount_percent: percent };
      return throughDoor(
        () => lineDiscount.run(input),
        () => lineDiscountOver.run(input),
        overCap(percent),
      );
    }, 'sale.pos.lineChangeFailed');

  const setTicketDiscount = (discount: { percent: string; amount: number }) =>
    attempt((id) => {
      const input = { order_id: id, discount_percent: discount.percent, discount_amount: discount.amount };
      return throughDoor(
        () => ticketDiscount.run(input),
        () => ticketDiscountOver.run(input),
        overCap(discount.percent),
      );
    }, 'sale.pos.ticketDiscountFailed');

  return { setLineDiscount, setTicketDiscount };
}
