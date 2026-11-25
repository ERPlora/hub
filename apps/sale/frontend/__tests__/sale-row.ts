// A sale as the list of Sales answers it (`sale.sale.list`), for the tests of its page: a ticket of today, completed and
// paid in cash, with nothing given back yet.
import type { SaleRow } from '../operations';

export const saleRow = (id: string, over: Partial<SaleRow> = {}): SaleRow => ({
  id,
  number: `20261014-000${id.slice(1)}`,
  business_day: '2026-10-14',
  currency: 'EUR',
  currency_decimals: 2,
  created_at: '2026-10-14T10:05:00Z',
  status: 'completed',
  document_type: 'ticket',
  customer_id: null,
  customer_name: '',
  payment_method_name: 'Cash',
  staff_id: null,
  total: 1250,
  tax_total: 114,
  refunded_total: 0,
  refundable_total: 1250,
  sessions_to_return: 0,
  has_refunds: false,
  invoice_status: 'issued',
  documents_pending: false,
  ...over,
});
