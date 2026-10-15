// A voucher sold, as `service.grant.list` answers it, for the tests of the voucher sheets and dialogs.
import type { GrantOut } from '../operations';

export const GRANT: GrantOut = {
  id: 'g1',
  package_id: 'p1',
  package_name: 'Bono 5 cortes',
  customer_id: 'cust-1',
  customer_name: 'Lucía Pérez',
  customer_deleted_at: null,
  granted_at: '2026-10-01T10:00:00Z',
  source: 'manual',
  sale_id: null,
  amount: 9000,
  net_amount: 0,
  tax_amount: 0,
  note: '',
  max_uses: 5,
  uses_added: 0,
  uses_removed: 0,
  days_added: 0,
  used: 2,
  remaining: 3,
  expires_at: '2027-03-30T10:00:00Z',
  is_expired: false,
  status: 'active',
  voided_at: null,
  voided_by: '',
  void_reason: '',
  can_void: false,
  can_adjust: true,
};

export const grant = (over: Partial<GrantOut> = {}): GrantOut => ({ ...GRANT, ...over });
