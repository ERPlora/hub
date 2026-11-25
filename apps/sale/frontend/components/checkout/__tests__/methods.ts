// A payment method of the charge sheet's tests, as `sale.payment_method.list` gives it: allowed, and cash gives change.
import type { PaymentMethodOut } from '../../../operations';

export const method = (id: string, type: PaymentMethodOut['type'], display_name: string): PaymentMethodOut => ({
  id,
  name: id,
  display_name,
  type,
  sort_order: 0,
  requires_change: type === 'cash',
  allowed: true,
});
