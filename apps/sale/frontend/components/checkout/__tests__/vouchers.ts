// Fixtures of the voucher at the till's tests (SALE-F27): Services' options for a line and the preview
// lines of the charge.
import type { TenderOptionOut } from '../../../../../service/frontend/operations';
import type { PreviewLineOut } from '../../../operations';

export const option = (grant: string, over: Partial<TenderOptionOut> = {}): TenderOptionOut => ({
  grant_id: grant,
  package_id: `p-${grant}`,
  package_name: 'Bono 5 cortes',
  granted_at: '2026-10-01T10:00:00Z',
  max_uses: 5,
  used: 0,
  remaining_before: 5,
  remaining_after: 4,
  is_unlimited: false,
  expires_at: null,
  is_default: false,
  default_reason: '',
  candidate_count: 1,
  ...over,
});

export const previewLine = (id: string, over: Partial<PreviewLineOut> = {}): PreviewLineOut => ({
  order_line_id: id,
  name: 'Corte de pelo',
  quantity: '1.000',
  unit: 'ud',
  unit_price: 2500,
  discount_percent: '0.00',
  is_gift: false,
  service_id: 'sv1',
  paid_by_voucher: false,
  voucher_name: '',
  voucher_remaining: null,
  tax_category_key: 'service.generic',
  tax_rate: '21.00',
  net_amount: 2066,
  tax_amount: 434,
  line_total: 2500,
  ...over,
});
