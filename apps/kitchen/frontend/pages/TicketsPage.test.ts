// Kitchen → Tickets (WORKBOOK «Pantallas · Comandas»; KITCHEN-F21 to F23): every ticket, newest first, 50 a
// page: Ticket (its full number), Destination, Type, Priority, Status, Dishes, Total and Sent; «Search
// ticket or destination…», filters by type, priority and status, table or cards. Row actions only for
// whoever may and only when the status allows: Fire, Ready, Served, Recall, Reprint and Cancel (asks
// first, with an optional reason). A row opens its detail; «New ticket» opens the form.
import { ConfirmDialog, DataTable } from '@erplora/ui/components';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import { cardIcons, switchToCards } from '../../../../base/frontend/__tests__/data-table-cards';
import { business, NOW, POLISH, row, SETTINGS } from '../__tests__/kitchen';
import {
  EMPLOYEE,
  flush,
  ionValue,
  mountKitchen,
  type MountOptions,
  page,
  settle,
  tabsOf,
} from '../__tests__/mount-kitchen';
import TicketDetailModal from '../components/TicketDetailModal.vue';
import TicketFormModal from '../components/TicketFormModal.vue';
import type { TicketRowOut } from '../operations';
import TicketsPage from './TicketsPage.vue';
import { listFillProblems } from '../../../../frontend/testing/list-fill';

const OP = 'kitchen.ticket.list';
const PENDING = row('t1');
const READY = row('t2', { number: '20261014-0013', short_number: '0013', status: 'ready', label: 'Table 9' });
const SERVED = row('t3', { number: '20261014-0010', short_number: '0010', status: 'served' });

async function setup(options: MountOptions = {}) {
  const m = await mountKitchen(TicketsPage, { path: '/kitchen/tickets', ...options });
  await m.live();
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const show = async (rows: TicketRowOut[], owner = business()) => {
    await m.result('kitchen.settings.get', SETTINGS);
    await m.result('base.business.get', owner);
    await m.result(OP, page(rows));
  };
  const actionsFor = (r: TicketRowOut) =>
    prop<Array<{ id: string; hidden?: (row: TicketRowOut) => boolean }>>('actions')
      .filter((a) => !a.hidden?.(r))
      .map((a) => a.id);
  const action = async (actionId: string, r: unknown) => {
    table().vm.$emit('action', { actionId, row: r });
    await settle();
  };
  return { ...m, table, prop, show, actionsFor, action };
}

describe('TicketsPage', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(NOW);
  });
  afterEach(() => vi.useRealTimers());

  it('lists the tickets newest first, 50 a page, with the old columns', async () => {
    const s = await setup();
    expect(s.params(OP)).toEqual([{ sort: '-received_at', limit: 50, offset: 0 }]);
    await s.show([READY, PENDING, SERVED]);
    expect(s.prop<Array<{ key: string; label: string }>>('columns').map((c) => c.label)).toEqual([
      'Ticket',
      'Destination',
      'Type',
      'Priority',
      'Status',
      'Dishes',
      'Total',
      'Sent',
    ]);
    const text = s.wrapper.text();
    for (const words of ['20261014-0013', 'Table 9', 'Dine in', 'Ready', '€24.50']) expect(text, words).toContain(words);
    expect(s.prop('searchPlaceholder')).toBe('Search ticket or destination…');
  });

  it('the Total is in the business’s currency: a business in Poland reads zlotys, never euros', async () => {
    const s = await setup();
    await s.show([READY], business(POLISH));
    const total = s.prop<Array<{ key: string; format: (v: unknown, r: TicketRowOut) => string }>>('columns').find((c) => c.key === 'total')!;
    expect(total.format(READY.total, READY)).toBe('zł\u00a024.50');
    expect(s.wrapper.text()).toContain('zł\u00a024.50');
    expect(s.wrapper.text()).not.toContain('€');
  });

  it('until the business answers, the Total is a dash, never in euros', async () => {
    const s = await setup();
    await s.result('kitchen.settings.get', SETTINGS);
    await s.result(OP, page([READY]));
    expect(s.wrapper.text()).toContain('—');
    expect(s.wrapper.text()).not.toContain('€');
  });

  it('searches and filters on the server', async () => {
    const s = await setup();
    await s.show([PENDING]);
    s.table().vm.$emit('update:search', 'table');
    s.table().vm.$emit('filtersChange', { status: 'ready', priority: 'rush' });
    await flush();
    await s.reopen();
    expect(s.params(OP)).toEqual([{ search: 'table', sort: '-received_at', status: 'ready', priority: 'rush', limit: 50, offset: 0 }]);
  });

  it('25 a page asks the server for 25', async () => {
    const s = await setup();
    await s.show([PENDING]);
    s.table().vm.$emit('pageSizeChange', 25);
    await flush();
    await s.reopen();
    expect(s.params(OP)).toEqual([{ sort: '-received_at', limit: 25, offset: 0 }]);
  });

  it('type, priority and status filter by a list of their words, never by typing', async () => {
    const s = await setup();
    await s.show([PENDING]);
    const filters = s
      .prop<Array<{ key: string; filter?: { type: string; options?: Array<{ label: string }> } }>>('columns')
      .filter((c) => c.filter)
      .map((c) => [c.key, c.filter!.type, c.filter!.options?.map((o) => o.label)]);
    expect(filters).toEqual([
      ['order_type', 'select', ['Dine in', 'Takeaway', 'Delivery']],
      ['priority', 'select', ['Normal', 'Rush', 'VIP']],
      ['status', 'select', ['To prepare', 'Preparing', 'Ready', 'Served', 'Cancelled']],
    ]);
  });

  it('a ticket made on page 2 is seen: the list goes back to the first page', async () => {
    const s = await setup();
    await s.show([PENDING]);
    s.table().vm.$emit('pageChange', 1);
    await flush();
    await s.reopen();
    expect(s.params(OP)).toEqual([{ sort: '-received_at', limit: 50, offset: 50 }]);
    s.wrapper.findComponent(TicketFormModal).vm.$emit('saved', PENDING);
    await flush();
    await s.reopen();
    expect(s.params(OP)).toEqual([{ sort: '-received_at', limit: 50, offset: 0 }]);
  });

  it('offers only the steps the status allows', async () => {
    const s = await setup();
    await s.show([PENDING, READY, SERVED]);
    expect(s.actionsFor(PENDING)).toEqual(['detail', 'start', 'ready', 'reprint', 'cancel']);
    expect(s.actionsFor(READY)).toEqual(['detail', 'serve', 'recall', 'reprint', 'cancel']);
    expect(s.actionsFor(SERVED)).toEqual(['detail', 'reprint']);
  });

  it('a cook moves tickets but neither cancels nor creates without the permission', async () => {
    const s = await setup({ session: { ...EMPLOYEE, permissions: EMPLOYEE.permissions.filter((p) => p !== 'kitchen.add_ticket') } });
    await s.show([PENDING]);
    expect(s.actionsFor(PENDING)).toEqual(['detail', 'start', 'ready', 'reprint']);
    expect(s.prop('primaryAction')).toBeUndefined();
  });

  it('runs a step and says why a refused one failed', async () => {
    const s = await setup();
    await s.show([PENDING]);
    s.answer(200, { ...PENDING, status: 'preparing' });
    await s.action('start', PENDING);
    expect(s.sent().map((call) => [call.path, call.body])).toEqual([['/api/kitchen/tickets/start', { ticket_id: 't1' }]]);
    s.answer(409, { error: { code: 'kitchen.invalid_transition', message: 'That kitchen ticket is no longer in the state this action requires.' } });
    await s.action('ready', PENDING);
    expect(s.find('kitchen-tickets-action-error').text()).toContain('no longer in the state');
  });

  it('reprints and says so', async () => {
    const s = await setup();
    await s.show([PENDING]);
    s.answer(200, PENDING);
    await s.action('reprint', PENDING);
    expect(s.find('kitchen-tickets-reprinted').text()).toContain('Ticket 20261014-0012 sent to the printer again.');
  });

  it('cancels after asking, with the reason given', async () => {
    const s = await setup();
    await s.show([PENDING]);
    await s.action('cancel', PENDING);
    const dialog = s.wrapper.findAllComponents(ConfirmDialog).find((d) => d.props('testid') === 'kitchen-tickets-cancel');
    expect(dialog?.props('title')).toBe('Cancel ticket 20261014-0012?');
    await ionValue(s.inDoc('kitchen-tickets-cancel-reason'), 'Guest left', 'ionInput');
    s.answer(200, { ...PENDING, status: 'cancelled' });
    dialog!.vm.$emit('confirm');
    await settle();
    expect(s.sent().map((call) => [call.path, call.body])).toEqual([['/api/kitchen/tickets/cancel', { ticket_id: 't1', reason: 'Guest left' }]]);
  });

  it('opens a ticket’s detail and the form of a new one', async () => {
    const s = await setup();
    await s.show([PENDING]);
    s.table().vm.$emit('rowClick', PENDING);
    await settle();
    expect(s.wrapper.findComponent(TicketDetailModal).props('ticketId')).toBe('t1');
    s.table().vm.$emit('primaryAction');
    await settle();
    expect(s.wrapper.findComponent(TicketFormModal).props()).toMatchObject({ open: true, defaultType: 'dine_in' });
  });

  it('says it is empty with the old words', async () => {
    const s = await setup();
    await s.show([]);
    expect(s.find('kitchen-tickets-empty').text()).toContain('No tickets.');
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.show([PENDING]);
    expect(s.prop('searchPlaceholder')).toBe('Buscar comanda o destino…');
    expect(s.wrapper.text()).toContain('Por preparar');
  });
});

describe('TicketsPage: the list fills the page', () => {
  it('AppPage `fill` and its DataTable `fill`, only stacks between them: from the topbar to the tabbar', async () => {
    const s = await setup();
    expect(listFillProblems(s.wrapper)).toEqual([]);
  });
});

// The tablet shows the list as cards: under the title, each datum is told by the icon of its column, the
// dishes say what they count, and the destination the title already names is not said twice (KITCHEN-F21).
describe('TicketsPage in cards: every datum says what it is', () => {
  async function card(locale: 'en' | 'es' = 'en') {
    const s = await setup({ locale });
    await s.show([READY]);
    switchToCards(s.wrapper, 'kitchen-tickets');
    await settle();
    return s.wrapper.get('[data-testid="kitchen-tickets-row"]');
  }

  it('heads the card with its number and destination and marks every other datum with its icon', async () => {
    const ticket = await card();
    expect(ticket.get('.data-table__card-title').text()).toBe('#0013 Table 9');
    expect(cardIcons(ticket)).toEqual({
      number: 'receipt-outline',
      order_type: 'storefront-outline',
      priority: 'speedometer-outline',
      items_count: 'list-outline',
      total: 'cash-outline',
      received_at: 'time-outline',
    });
  });

  it.each([
    ['en', '2 dishes'],
    ['es', '2 platos'],
  ] as const)('says the dishes in words, not as a bare number (%s)', async (locale, said) => {
    const ticket = await card(locale);
    expect(ticket.get('[data-column="items_count"] .data-table__card-meta-value').text()).toBe(said);
  });
});

describe('TicketsPage: Android Back with unsaved changes (hub#1046, BASE-F05)', () => {
  it('the cancel dialog as opened closes; a typed reason asks; emptied again it closes', async () => {
    const s = await setup();
    await s.show([PENDING]);
    await s.action('cancel', PENDING);
    const { expectUnsavedFormAsksBeforeClosing } = await import('../../../../base/frontend/__tests__/unsaved-form');
    await expectUnsavedFormAsksBeforeClosing({
      overlay: () => s.inDoc('kitchen-tickets-cancel'),
      change: () => ionValue(s.inDoc('kitchen-tickets-cancel-reason'), 'Guest left', 'ionInput'),
      restore: () => ionValue(s.inDoc('kitchen-tickets-cancel-reason'), '', 'ionInput'),
    });
  });
});

describe('TicketsPage: its tab bar', () => {
  it('paints only the sections its person may open, each named as in the menu', async () => {
    const s = await setup({ session: EMPLOYEE });
    expect(tabsOf(s.wrapper)).toEqual([['display', 'Display'], ['tickets', 'Tickets'], ['history', 'History']]);
  });
});
