// Fixtures of the kitchen app's frontend tests: what the server answers, as schemas.py shapes it.
import type { Business } from '../../../../base/frontend/operations';
import type { BoardOut, ItemOut, LogOut, RouteOut, SettingsOut, StationOut, TicketOut, TicketRowOut } from '../operations';

export const SETTINGS: SettingsOut = {
  show_timer: true,
  warning_minutes: 15,
  critical_minutes: 30,
  color_coding: true,
  sound_enabled: true,
  sound_volume: 70,
  sound_tone: 'chime',
  print_pass: false,
  works_from_screen: true,
  default_order_type: 'dine_in',
  timezone: 'Europe/Madrid',
};

/** The hub's business (`base.business.get`, the platform's): one in Spain, in euros, unless a test says another
 *  (the money the kitchen paints is the business's). */
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

export const POLISH: Partial<Business> = { country: 'PL', country_name: 'Poland', currency: 'PLN', currency_label: 'PLN · Polish Zloty' };

/** 13:00 in Madrid (11:00 UTC) on 2026-10-14: the tests' «now». */
export const NOW = new Date('2026-10-14T11:00:00Z');

/** An ISO moment `minutes` before `NOW`. */
export const ago = (minutes: number): string => new Date(NOW.getTime() - minutes * 60_000).toISOString();

export function item(id: string, fields: Partial<ItemOut> = {}): ItemOut {
  return {
    id,
    position: 1,
    product_id: null,
    name: 'Burger',
    quantity: '1.000',
    unit: 'ud',
    notes: '',
    modifiers: [],
    menu_name: '',
    menu_line_id: null,
    station_id: null,
    station_name: '',
    station_color: '',
    destination: 'both',
    printer_usage: 'kitchen',
    status: 'pending',
    void_reason: '',
    ready_at: null,
    ...fields,
  };
}

export function ticket(id: string, fields: Partial<TicketOut> = {}): TicketOut {
  return {
    id,
    number: '20261014-0012',
    short_number: '0012',
    label: 'Table 4',
    order_type: 'dine_in',
    priority: 'normal',
    status: 'pending',
    round_no: 1,
    waiter: 'luis',
    notes: '',
    order_id: 'order-1',
    received_at: ago(3),
    started_at: null,
    ready_at: null,
    served_at: null,
    cancelled_at: null,
    rush_count: 0,
    total: 1200,
    saved: true,
    items: [item(`${id}-1`)],
    print_error: null,
    ...fields,
  };
}

export function board(fields: Partial<BoardOut> = {}): BoardOut {
  const cooking = fields.cooking ?? [];
  const ready = fields.ready ?? [];
  return {
    cooking,
    ready,
    cooking_count: cooking.length,
    ready_count: ready.length,
    stations: [],
    truncated: false,
    ...fields,
  };
}

export function row(id: string, fields: Partial<TicketRowOut> = {}): TicketRowOut {
  return {
    id,
    number: '20261014-0012',
    short_number: '0012',
    label: 'Table 4',
    order_type: 'dine_in',
    priority: 'normal',
    status: 'pending',
    round_no: 1,
    items_count: 2,
    total: 2450,
    received_at: ago(3),
    order_id: 'order-1',
    saved: true,
    ...fields,
  };
}

export function station(id: string, fields: Partial<StationOut> = {}): StationOut {
  return {
    id,
    name: 'Grill',
    color: '#E03131',
    destination: 'both',
    printer_usage: 'kitchen',
    printer_name: '',
    sort_order: 0,
    is_active: true,
    in_progress: 0,
    routes: 0,
    ...fields,
  };
}

export function route(targetId: string, fields: Partial<RouteOut> = {}): RouteOut {
  return {
    kind: 'product',
    target_id: targetId,
    target_name: 'Burger',
    station_id: 'st-grill',
    station_name: 'Grill',
    ...fields,
  };
}

export function entry(id: string, fields: Partial<LogOut> = {}): LogOut {
  return {
    id,
    action: 'received',
    ticket_id: 't1',
    ticket_number: '20261014-0012',
    item_name: '',
    station_name: '',
    actor: '',
    notes: '',
    created_at: ago(5),
    ...fields,
  };
}
