// Rows of the pricing app as the server sends them, for the page and component tests.
import type { Business } from '../../../../base/frontend/operations';
import type { PriceItemOut, PriceListOut, RuleOut } from '../operations';

/** The hub's business (`base.business.get`, the platform's): one in Spain, in euros, unless a test says another
 *  (the money pricing paints and reads is the business's, and a list's own). */
export function business(fields: Partial<Business> = {}): Business {
  return {
    name: 'Salón Lucía',
    country: 'ES',
    country_name: 'Spain',
    timezone: 'Europe/Madrid',
    language: 'es',
    language_name: 'Spanish',
    currency: 'EUR',
    currency_label: 'EUR · Euro',
    currency_decimals: 2,
    demo: false,
    settings_url: 'https://erplora.com/hubs/salon-lucia/settings',
    ...fields,
  };
}

/** A business in Poland: it sells in złoty. */
export const POLISH: Partial<Business> = { country: 'PL', country_name: 'Poland', currency: 'PLN', currency_label: 'PLN · Polish Zloty' };

export function priceList(overrides: Partial<PriceListOut> = {}): PriceListOut {
  return {
    id: 'l1',
    code: 'VIP',
    name: 'VIP members',
    currency: 'EUR',
    tax_included: null,
    customer_group_id: 'g1',
    customer_group_name: 'VIP',
    valid_from: null,
    valid_until: null,
    is_default: false,
    is_active: true,
    item_count: 2,
    updated_at: '2026-07-15T10:00:00+02:00',
    ...overrides,
  };
}

export function priceItem(overrides: Partial<PriceItemOut> = {}): PriceItemOut {
  return {
    id: 'i1',
    price_list_id: 'l1',
    price_list_code: 'VIP',
    price_list_name: 'VIP members',
    kind: 'product',
    product_id: 'p1',
    service_id: null,
    name: 'Shampoo',
    sku: 'SH-1',
    unit: 'ud',
    base_price: 1500,
    min_quantity: '1.000',
    price: 1200,
    updated_at: '2026-07-15T10:00:00+02:00',
    ...overrides,
  };
}

export function rule(overrides: Partial<RuleOut> = {}): RuleOut {
  return {
    id: 'r1',
    code: 'TEN',
    name: 'Ten off',
    rule_type: 'percent',
    percent: '10.00',
    amount: null,
    buy_quantity: null,
    get_quantity: null,
    tiers: [],
    applies_to: 'all',
    category_id: null,
    category_name: null,
    product_id: null,
    product_name: null,
    service_id: null,
    service_name: null,
    target_deleted: false,
    customer_group_id: null,
    customer_group_name: null,
    min_quantity: null,
    valid_from: null,
    valid_until: null,
    priority: 100,
    is_active: true,
    updated_at: '2026-07-15T10:00:00+02:00',
    ...overrides,
  };
}
