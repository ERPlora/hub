// How a line of a shift reads (CASH_REGISTER-F11): a sale is named by its document, a void and a refund by
// theirs, and a line written by hand shows its concept; a factory payment method (Sales keeps «Cash» and
// «Card» in English) and a line without one read in the reader's language.
import type { MethodType, MovementRow } from '../operations';

type Translate = (key: string, named?: Record<string, unknown>) => string;

/** Sales' factory payment methods, stored with their English name. */
const FACTORY_NAMES = new Set(['Cash', 'Card']);

/** The concept of a line: its document for a sale line, what was typed for one written by hand. */
export function conceptOf(row: Pick<MovementRow, 'type' | 'description' | 'sale_number' | 'document_type'>, t: Translate): string {
  if (row.type === 'in' || row.type === 'out') return row.description;
  const document = row.sale_number
    ? t(row.document_type === 'invoice' ? 'cash_register.concept.invoice' : 'cash_register.concept.ticket', { number: row.sale_number })
    : t('cash_register.concept.saleUnnumbered');
  if (row.type === 'void') return t('cash_register.concept.voidOf', { document });
  if (row.type === 'refund') return t('cash_register.concept.refundOf', { document });
  return document;
}

/** The payment method of a line as the person reads it. */
export function methodOf(row: { method_type: MethodType; method_name: string }, t: Translate): string {
  if (!row.method_name || FACTORY_NAMES.has(row.method_name)) return t(`cash_register.methods.${row.method_type}`);
  return row.method_name;
}
