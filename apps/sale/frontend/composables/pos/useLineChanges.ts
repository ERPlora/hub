import { useCommand } from '@erplora/ui/sdk';

import { withApproval } from '../../lib/approval';
import type { OrderLineOut } from '../../operations';
import { useT } from '../useT';
import { type CheckWrites, toast } from './useCheckWrites';
import { useLineNote } from './useLineNote';

export function useLineChanges({ attempt }: CheckWrites) {
  const t = useT();
  const updateLine = useCommand('sale.order.update_line');
  const removeLine = useCommand('sale.order.remove_line');
  const lineStaff = useCommand('sale.order.set_line_staff');
  const voidLineCommand = useCommand('sale.order.void_line');

  const setQuantity = (line: OrderLineOut, quantity: string) =>
    toast(
      attempt(
        (id) =>
          Number(quantity) === 0
            ? removeLine.run({ order_id: id, line_id: line.id })
            : updateLine.run({ order_id: id, line_id: line.id, quantity }),
        'sale.pos.lineChangeFailed',
      ),
    );

  const toggleGift = (line: OrderLineOut) =>
    toast(
      attempt(
        (id) =>
          updateLine.run({
            order_id: id,
            line_id: line.id,
            is_gift: !line.is_gift,
            gift_reason: line.is_gift ? '' : t('sale.pos.giftReason'),
          }),
        'sale.pos.lineChangeFailed',
      ),
    );

  const setNote = useLineNote(attempt);

  const setLineStaff = (line: OrderLineOut, staffId: string | null) =>
    toast(attempt((id) => lineStaff.run({ order_id: id, line_id: line.id, staff_id: staffId }), 'sale.pos.lineStaffFailed'));

  const voidLine = (line: OrderLineOut, reason: string) =>
    attempt((id) => withApproval(() => voidLineCommand.run({ order_id: id, line_id: line.id, reason })), 'sale.pos.voidLineFailed');

  return { setQuantity, toggleGift, setNote, setLineStaff, voidLine };
}
