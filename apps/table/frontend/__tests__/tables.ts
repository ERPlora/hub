// Rows of the table app's lists, as the server answers them, for the page and component tests.
import type { Business } from '../../../../base/frontend/operations';
import type { SessionOut, TableOut, ZoneOut } from '../operations';

export function tableRow(overrides: Partial<TableOut> = {}): TableOut {
  return {
    id: 't1',
    number: '4',
    label: '4 (Dining room)',
    name: '',
    capacity: 4,
    shape: 'square',
    status: 'available',
    blocked: false,
    is_active: true,
    zone_id: 'z1',
    zone_name: 'Dining room',
    in_service: true,
    position_x: 16,
    position_y: 16,
    width: 72,
    height: 72,
    guests: null,
    since: null,
    waiter_name: '',
    checks: [],
    hold: null,
    ...overrides,
  };
}

/** An occupied table: one check of 3 guests seated at 19:05 UTC by Luis, with its check of Sales. */
export function occupied(overrides: Partial<TableOut> = {}): TableOut {
  return tableRow({
    status: 'occupied',
    guests: 3,
    since: '2026-10-14T19:05:00Z',
    waiter_name: 'Luis',
    checks: [
      {
        id: 's1',
        order_id: 'o1',
        guests_count: 3,
        opened_at: '2026-10-14T19:05:00Z',
        waiter_name: 'Luis',
        customer_id: null,
        customer_name: null,
        split_from_id: null,
      },
    ],
    ...overrides,
  });
}

export function zoneRow(overrides: Partial<ZoneOut> = {}): ZoneOut {
  return {
    id: 'z1',
    name: 'Dining room',
    description: '',
    color: 'primary',
    sort_order: 0,
    is_active: true,
    table_count: 0,
    available_count: 0,
    ...overrides,
  };
}

export function sessionRow(overrides: Partial<SessionOut> = {}): SessionOut {
  return {
    id: 's1',
    table_id: 't1',
    table_number: '4',
    label: '4 (Dining room)',
    zone_id: 'z1',
    zone_name: 'Dining room',
    order_id: 'o1',
    guests_count: 3,
    status: 'open',
    waiter_id: '2',
    waiter_name: 'Luis',
    opened_at: '2026-10-14T19:05:00Z',
    closed_at: null,
    notes: '',
    split_from_id: null,
    transferred_from_id: null,
    merged_into_id: null,
    paid_total: null,
    currency: null,
    currency_decimals: null,
    customer_id: null,
    customer_name: null,
    ...overrides,
  };
}

/** What a check charged, in the currency its sales were charged in (`currency`, `currency_decimals`). */
export const charged = (paid_total: number, currency = 'EUR', currency_decimals = 2): Partial<SessionOut> => ({ paid_total, currency, currency_decimals });

/** The hub's business (`base.business.get`, the platform's): one in Spain, in euros, unless a test says another. */
export function business(fields: Partial<Business> = {}): Business {
  return {
    name: 'Bar Pepe',
    country: 'ES',
    country_name: 'Spain',
    timezone: 'Europe/Madrid',
    language: 'es',
    language_name: 'Spanish',
    currency: 'EUR',
    currency_label: 'EUR · Euro',
    currency_decimals: 2,
    demo: false,
    settings_url: 'https://erplora.com/hubs/bar-pepe/settings',
    ...fields,
  };
}

/** A business in Poland: it sells in złoty. */
export const POLISH: Partial<Business> = { country: 'PL', country_name: 'Poland', currency: 'PLN', currency_label: 'PLN · Polish Zloty' };

/** A business in Japan: the yen has no minor units. */
export const JAPANESE: Partial<Business> = { country: 'JP', country_name: 'Japan', currency: 'JPY', currency_label: 'JPY · Japanese Yen', currency_decimals: 0 };

export const SETTINGS = {
  prompt_guests_on_seat: true,
  timer_warning_minutes: 60,
  timer_critical_minutes: 90,
  reserved_lead_minutes: 60,
  timezone: 'Europe/Madrid',
};

/** 21:40 in Madrid: 35 minutes after the occupied table sat down. */
export const NOW = new Date('2026-10-14T19:40:00Z');
