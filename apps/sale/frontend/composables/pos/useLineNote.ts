import type { AllergenCode } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';

import type { OrderLineOut, OrderOut } from '../../operations';

export type NoteWriteResult = { ok: true } | { ok: false; message: string };
type Attempt = (write: (orderId: string) => Promise<OrderOut>, fallbackKey: string) => Promise<NoteWriteResult>;

export function useLineNote(attempt: Attempt) {
  const updateLine = useCommand('sale.order.update_line');
  const lineAllergy = useCommand('sale.order.set_line_allergy');

  return (line: OrderLineOut, notes: string, allergy?: AllergenCode[]) =>
    attempt(async (id) => {
      const next = await updateLine.run({ order_id: id, line_id: line.id, notes });
      if (allergy === undefined) return next;
      return lineAllergy.run({ order_id: id, line_id: line.id, allergy });
    }, 'sale.pos.lineChangeFailed');
}
