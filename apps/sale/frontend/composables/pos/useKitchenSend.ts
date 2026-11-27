import { useCommand } from '@erplora/ui/sdk';

import { refusal } from '../../lib/refusal';
import { useT } from '../useT';
import type { CheckWrites } from './useCheckWrites';
import type { WriteResult } from './useTill';

export function useKitchenSend({ serial, order, check, accept, wordsOf }: CheckWrites) {
  const t = useT();
  const kitchenSend = useCommand('kitchen.ticket.send');
  const readCheck = useCommand('sale.order.get');

  function sendToKitchen(rush: boolean): Promise<WriteResult & { round?: number; printed?: boolean; code?: string }> {
    return serial(async () => {
      const id = order.value?.id ?? check.id.value;
      if (!id) return { ok: false, message: t('sale.pos.kitchen.notSent') };
      try {
        const ticket = await kitchenSend.run({ order_id: id, priority: rush ? 'rush' : 'normal' });
        accept(await readCheck.run({ order_id: id }));
        return { ok: true, round: ticket.round_no, printed: !ticket.print_error };
      } catch (error) {
        const code = refusal(error, '')?.code;
        return { ok: false, message: wordsOf(error, 'sale.pos.kitchen.notSent'), ...(code ? { code } : {}) };
      }
    });
  }

  return sendToKitchen;
}
