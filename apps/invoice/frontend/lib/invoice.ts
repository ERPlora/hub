// What the invoice screens say about a document, the same in the list, the detail and the paper (the old
// `typeLabel`, `statusLabel`, `parseTaxes` and `documentNote`): the closed lists the server knows, the tone of
// a status, the breakdown as printed rows and the note of a rectifying invoice, composed here in the
// reader's language from what it rectifies and why (the server keeps no sentence).
import type { StatusPillTone } from '@erplora/ui/components';

import type { BreakdownOut, InvoiceOut, InvoiceSource, InvoiceStatus, InvoiceType } from '../operations';
import { formatPercent } from './format';

type Translate = (key: string, named?: Record<string, unknown>) => string;

export const TYPE_CODES: readonly InvoiceType[] = ['F1', 'F2', 'F3', 'R1', 'R2', 'R3', 'R4', 'R5'];
export const STATUS_CODES: readonly InvoiceStatus[] = ['issued', 'paid', 'cancelled'];
export const SOURCE_CODES: readonly InvoiceSource[] = ['sale', 'manual', 'substitution', 'rectification', 'refund', 'void'];

const TONES: Record<InvoiceStatus, StatusPillTone> = { issued: 'info', paid: 'success', cancelled: 'danger' };

/** The colour of a status: issued in progress, paid done, cancelled blocked. */
export function statusTone(status: InvoiceStatus): StatusPillTone {
  return TONES[status] ?? 'neutral';
}

/** A ticket (F2) or its rectification (R5): it identifies no customer. */
export function isSimplified(type: string): boolean {
  return type === 'F2' || type === 'R5';
}

/** A full invoice (or the rectification of one) without the customer's tax ID: the ticket printer cannot
 *  print it as a full invoice, and the screen says so before anyone presses Print. */
export function missingTaxId(invoice: Pick<InvoiceOut, 'invoice_type' | 'customer_tax_id'>): boolean {
  return !isSimplified(invoice.invoice_type) && !invoice.customer_tax_id.trim();
}

/** One printed row of the breakdown. */
export interface TaxRow {
  label: string;
  base: number;
  amount: number;
}

/** The breakdown as it is printed: «VAT 21%» (IGIC and IPSI by their own name), «Exempt (E1)», «Not
 *  subject», «Reverse charge»; the equivalence surcharge is a row of its own over the same base. */
export function taxRows(breakdown: readonly BreakdownOut[], t: Translate, locale: string): TaxRow[] {
  const rows: TaxRow[] = [];
  for (const entry of breakdown) {
    let label: string;
    if (entry.qualification === 'exempt') {
      label = entry.exempt_reason ? t('invoice.taxes.exemptCause', { cause: entry.exempt_reason }) : t('invoice.taxes.exempt');
    } else if (entry.qualification === 'not_subject' || entry.qualification === 'not_subject_location') {
      label = t('invoice.taxes.notSubject');
    } else if (entry.qualification === 'subject_reverse') {
      label = t('invoice.taxes.reverseCharge');
    } else {
      const name = entry.tax === 'vat' ? t('invoice.taxes.vat') : entry.tax.toUpperCase();
      label = `${name} ${formatPercent(entry.rate, locale)}`;
    }
    rows.push({ label, base: entry.base, amount: entry.quota });
    if (Number(entry.surcharge_rate) > 0) {
      rows.push({
        label: `${t('invoice.taxes.surcharge')} ${formatPercent(entry.surcharge_rate, locale)}`,
        base: entry.base,
        amount: entry.surcharge_quota,
      });
    }
  }
  return rows;
}

/** The note a document carries: a rectifying one names the invoice it rectifies and its reason; any other,
 *  its own notes. */
export function documentNote(invoice: Pick<InvoiceOut, 'rectifies' | 'description' | 'notes'>, t: Translate): string {
  if (!invoice.rectifies) return invoice.notes;
  const reason = invoice.description.trim();
  return reason
    ? t('invoice.detail.rectifiesNote', { number: invoice.rectifies.number, reason })
    : t('invoice.detail.rectifiesNoteNoReason', { number: invoice.rectifies.number });
}
