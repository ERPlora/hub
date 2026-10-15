// A voucher of the catalog, as `service.package.list` answers it, for the tests of the packages screen.
import type { PackageOut } from '../operations';

export const PACKAGE: PackageOut = {
  id: 'p1',
  name: 'Bono 5 cortes',
  description: '',
  discount_type: 'percentage',
  discount_percent_bp: 1050,
  discount_amount: 0,
  fixed_price: 9000,
  validity_days: 180,
  max_uses: 5,
  is_active: true,
  is_featured: false,
  sort_order: 0,
  status: 'active',
  item_count: 1,
  items: [{ id: 'i1', service_id: 's1', service_name: 'Cut', service_price: 2000, sessions: 5, sort_order: 0 }],
  grant_count: 2,
  created_at: '2026-10-01T10:00:00Z',
  updated_at: '2026-10-01T10:00:00Z',
};

export const pkg = (over: Partial<PackageOut> = {}): PackageOut => ({ ...PACKAGE, ...over });
