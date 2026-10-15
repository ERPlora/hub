// `useMarkPaid()`: «Mark as paid» (INVOICE-F19), the same from a row of Invoices and from the open invoice.
// It asks first, as every invoicing back office does (the old «Mark {number} as paid?» / «The payment is
// recorded with the current date and time.»), then runs `invoice.invoice.mark_paid` by the invoice's id
// and says so; the list and the detail catch up by themselves, live. A refusal (paid or rectified
// meanwhile elsewhere) is kept in `refused`, in the server's words, for the screen to show where the
// button was; a failure the server did not word says «Could not mark it as paid».
import { useConfirm } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { toastSuccess } from '@erplora/ui/shell';
import { type Ref, shallowRef } from 'vue';

import { refusal } from '../lib/refusal';
import type { InvoiceRowOut } from '../operations';
import { useT } from './useT';

export interface MarkPaid {
  /** Asks and marks; `true` when it was marked. */
  mark(invoice: Pick<InvoiceRowOut, 'id' | 'number'>): Promise<boolean>;
  /** Why the last attempt was refused; `null` after a fresh one. */
  refused: Ref<string | null>;
  /** The invoice being marked now. */
  pending: Ref<string | null>;
}

export function useMarkPaid(): MarkPaid {
  const t = useT();
  const { confirm } = useConfirm();
  const command = useCommand('invoice.invoice.mark_paid');
  const refused = shallowRef<string | null>(null);
  const pending = shallowRef<string | null>(null);

  async function mark(invoice: Pick<InvoiceRowOut, 'id' | 'number'>): Promise<boolean> {
    refused.value = null;
    const yes = await confirm({
      title: t('invoice.markPaid.title', { number: invoice.number }),
      message: t('invoice.markPaid.message'),
      confirmLabel: t('invoice.markPaid.confirm'),
      cancelLabel: t('invoice.cancel'),
      confirmIcon: 'ion:checkmark-circle-outline',
      tone: 'primary',
    });
    if (!yes) return false;
    pending.value = invoice.id;
    try {
      await command.run({ invoice_id: invoice.id });
    } catch {
      refused.value = refusal(command.error.value, t('invoice.markPaid.failed'))?.message ?? t('invoice.markPaid.failed');
      return false;
    } finally {
      pending.value = null;
    }
    void toastSuccess(t('invoice.markPaid.done', { number: invoice.number }));
    return true;
  }

  return { mark, refused, pending };
}
