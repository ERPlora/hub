// Kitchen → Tickets (WORKBOOK «Pantallas · Comandas»; KITCHEN-F21 to F23): every ticket, newest first, 50 a
// page: Ticket (its full number), Destination, Type, Priority, Status, Dishes, Total and Sent; «Search
// ticket or destination…», filters by type, priority and status, table or cards. Row actions only for
// whoever may and only when the status allows: Fire, Ready, Served, Recall, Reprint and Cancel (asks
// first, with an optional reason). A row opens its detail; «New ticket» opens the form.
import { ConfirmDialog, DataTable } from '@erplora/ui/components';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import { NOW, row, SETTINGS } from '../__tests__/kitchen';
import { EMPLOYEE, flush, ionValue, type MountOptions, mountKitchen, page, settle } from '../__tests__/mount-kitchen';
import TicketDetailModal from '../components/TicketDetailModal.vue';
import TicketFormModal from '../components/TicketFormModal.vue';
import type { TicketRowOut } from '../operations';
import TicketsPage from './TicketsPage.vue';
import { listFillProblems } from '../../../../frontend/testing/list-fill';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const OP = 'kitchen.ticket.list';
const PENDING = row('t1');
const READY = row('t2', { number: '20261014-0013', short_number: '0013', status: 'ready', label: 'Table 9' });
const SERVED = row('t3', { number: '20261014-0010', short_number: '0010', status: 'served' });

async function setup(options: MountOptions = {}) {
  const m = await mountKitchen(TicketsPage, { path: '/kitchen/tickets', ...options });
  await m.live();
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const show = async (rows: TicketRowOut[]) => {
    await m.result('kitchen.settings.get', SETTINGS);
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

  it('searches and filters on the server', async () => {
    const s = await setup();
    await s.show([PENDING]);
    s.table().vm.$emit('update:search', 'table');
    s.table().vm.$emit('filtersChange', { status: 'ready', priority: 'rush' });
    await flush();
    await s.reopen();
    expect(s.params(OP)).toEqual([{ search: 'table', sort: '-received_at', status: 'ready', priority: 'rush', limit: 50, offset: 0 }]);
  });

  it('25 a page asks the server for 25 (kitchen#135)', async () => {
    const s = await setup();
    await s.show([PENDING]);
    s.table().vm.$emit('pageSizeChange', 25);
    await flush();
    await s.reopen();
    expect(s.params(OP)).toEqual([{ sort: '-received_at', limit: 25, offset: 0 }]);
  });

  it('type, priority and status filter by a list of their words, never by typing (kitchen#39)', async () => {
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

  it('a ticket made on page 2 is seen: the list goes back to the first page (kitchen#133)', async () => {
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

describe('TicketsPage: the list fills the page (FIX-DATATABLE-HUB)', () => {
  it('AppPage `fill` and its DataTable `fill`, only stacks between them: from the topbar to the tabbar', async () => {
    const s = await setup();
    expect(listFillProblems(s.wrapper)).toEqual([]);
  });
});
