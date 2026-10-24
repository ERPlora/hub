// Reservations → Reservations (WORKBOOK «Pantallas · Reservas»; RESERVATION-F05 to F12, F20): the book of a
// day on the business's clock — the day bar with its figures, the reservations by time with Date, Time,
// Guest, Phone, Party, Table and Status; «Search guest, phone or email…» looks through the whole book;
// «New reservation»; per row Confirm, Seat, Complete, Cancel, No-show, Edit and Delete as its status and
// the person allow. Empty: «No reservations this day» with «New reservation»; searching without matches,
// «Clear filters».
import { DataTable, EmptyState } from '@erplora/ui/components';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import { click, EMPLOYEE, flush, ionValue, type MountOptions, mountReservation, page } from '../__tests__/mount-reservation';
import { dayOut, reservationRow, settingsOut } from '../__tests__/rows';
import DayBar from '../components/DayBar.vue';
import ReservationFormModal from '../components/ReservationFormModal.vue';
import StepDialog from '../components/StepDialog.vue';
import ReservationsPage from './ReservationsPage.vue';
import { listFillProblems } from '../../../../frontend/testing/list-fill';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const OP = 'reservation.reservation.list';
/** Thursday 15 October 2026, 12:00 in Madrid. */
const NOW = new Date('2026-10-15T10:00:00Z');
const PENDING = reservationRow();
const SEATED = reservationRow({ id: 'r2', guest_name: '', time: '13:30:00', status: 'seated', table_id: null, table_label: '', party_size: 2 });

async function setup(options: MountOptions = {}) {
  const m = await mountReservation(ReservationsPage, { path: '/reservation/reservations', ...options });
  await m.live();
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const rows = () => m.wrapper.findAll('[data-testid="reservation-list-row"]');
  const cells = (i: number) => rows()[i].findAll('[role="cell"]').map((c) => c.text().trim());
  const show = async (list: unknown[], total = list.length) => {
    await m.result('reservation.settings.get', settingsOut());
    await m.result('reservation.availability.day', dayOut());
    await m.result(OP, page(list, total));
  };
  const action = (actionId: string, row: unknown) => {
    table().vm.$emit('action', { actionId, row });
    return flush();
  };
  const visible = (row: unknown) =>
    prop<Array<{ id: string; hidden?: (r: unknown) => boolean }>>('actions')
      .filter((a) => !a.hidden?.(row))
      .map((a) => a.id);
  return { ...m, table, prop, rows, cells, show, action, visible, list: () => m.params(OP) };
}

describe('ReservationsPage', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(NOW);
  });
  afterEach(() => vi.useRealTimers());

  it('opens on today’s book, by day and time, with its figures', async () => {
    const s = await setup();
    expect(s.list()).toEqual([{ date_from: '2026-10-15', date_to: '2026-10-15', sort: 'starts_at', limit: 50, offset: 0 }]);
    expect(s.params('reservation.availability.day')).toEqual([{ date: '2026-10-15' }]);
    await s.show([PENDING, SEATED]);
    expect(s.prop<Array<{ key: string; label: string }>>('columns').map((c) => [c.key, c.label])).toEqual([
      ['date', 'Date'],
      ['time', 'Time'],
      ['guest_name', 'Guest'],
      ['guest_phone', 'Phone'],
      ['party_size', 'Party'],
      ['table', 'Table'],
      ['status', 'Status'],
      ['source', 'Booked through'],
    ]);
    expect(s.cells(0).slice(0, 7)).toEqual(['10/15/2026', '9:00 PM', 'Ana García', '+34 600 111 222', '4', '5 (Terrace)', 'Pending']);
    expect(s.cells(1).slice(2, 7)).toEqual(['Deleted customer', '+34 600 111 222', '2', '—', 'Seated']);
    expect([s.prop('searchPlaceholder'), s.prop<{ add: string }>('labels').add]).toEqual(['Search guest, phone or email…', 'New reservation']);
    expect(s.wrapper.findComponent(DayBar).props()).toMatchObject({ day: '2026-10-15', today: '2026-10-15', now: '12:00' });
  });

  it('paints the guest’s phone as Customers does, in the list and in the cards (+34 600 111 222)', async () => {
    const s = await setup();
    await s.show([PENDING, reservationRow({ id: 'r3', guest_name: 'John Smith', guest_phone: '+447911123456' })]);
    expect([s.cells(0)[3], s.cells(1)[3]]).toEqual(['+34 600 111 222', '+44 791 112 3456']);
    await ionValue(s.wrapper.find('[data-testid="reservation-list-view"]').element, 'cards');
    const phones = s.wrapper
      .findAll('.data-table__field')
      .filter((field) => field.find('.data-table__field-label').text() === 'Phone')
      .map((field) => field.find('.data-table__field-value').text().trim());
    expect(phones).toEqual(['+34 600 111 222', '+44 791 112 3456']);
  });

  it('moves to another day with the bar, and a search looks through the whole book', async () => {
    const s = await setup();
    await s.show([PENDING]);
    s.wrapper.findComponent(DayBar).vm.$emit('update:day', '2026-10-16');
    await flush();
    expect(s.list()).toEqual([{ date_from: '2026-10-16', date_to: '2026-10-16', sort: 'starts_at', limit: 50, offset: 0 }]);
    expect(s.params('reservation.availability.day')).toEqual([{ date: '2026-10-16' }]);
    s.table().vm.$emit('update:search', 'ana');
    s.table().vm.$emit('filtersChange', { status: 'pending', party_size_from: '2', time: '21' });
    await flush();
    expect(s.list()).toEqual([{ search: 'ana', status: 'pending', party_size_from: 2, time: '21', sort: 'starts_at', limit: 50, offset: 0 }]);
  });

  it('offers each row the steps its status allows; the host never deletes', async () => {
    const s = await setup();
    await s.show([PENDING]);
    expect(s.visible(PENDING)).toEqual(['confirm', 'seat', 'cancel', 'no_show', 'edit', 'delete']);
    expect(s.visible(reservationRow({ status: 'confirmed' }))).toEqual(['seat', 'cancel', 'no_show', 'edit', 'delete']);
    expect(s.visible(SEATED)).toEqual(['complete', 'edit', 'delete']);
    expect(s.visible(reservationRow({ status: 'cancelled' }))).toEqual(['edit', 'delete']);
    const host = await setup({ session: EMPLOYEE });
    await host.show([PENDING]);
    expect(host.visible(PENDING)).toEqual(['confirm', 'seat', 'cancel', 'no_show', 'edit']);
  });

  it('confirms, seats and completes at once, and says where a party was seated', async () => {
    const s = await setup();
    await s.show([PENDING]);
    s.answer(200, reservationRow({ status: 'confirmed' }));
    await s.action('confirm', PENDING);
    s.answer(200, reservationRow({ status: 'seated', table_session_id: 'ts1' }));
    await s.action('seat', PENDING);
    await flush();
    expect(s.sent().map((call) => [call.path, call.body])).toEqual([
      ['/api/reservation/reservations/confirm', { id: 'r1' }],
      ['/api/reservation/reservations/seat', { id: 'r1' }],
    ]);
    expect(s.find('reservation-list-outcome').text()).toBe('Ana García is seated at table 5 (Terrace): its check is open in Sales.');
  });

  it('a refused step says why above the list', async () => {
    const s = await setup();
    await s.show([PENDING]);
    s.answer(409, { error: { code: 'reservation.table_not_free', message: 'Table 5 (Terrace) is taken right now.' } });
    await s.action('seat', PENDING);
    await flush();
    expect(s.find('reservation-list-page-error').text()).toContain('Table 5 (Terrace) is taken right now.');
  });

  it('cancelling, a no-show and deleting ask first; Edit and a row open the reservation', async () => {
    const s = await setup();
    await s.show([PENDING]);
    await s.action('cancel', PENDING);
    const step = () => s.wrapper.findComponent(StepDialog);
    expect([step().props('kind'), step().props('open'), step().props('reservation')]).toEqual(['cancel', true, PENDING]);
    await s.action('no_show', PENDING);
    expect(step().props('kind')).toBe('no_show');
    await s.action('delete', PENDING);
    expect(step().props('kind')).toBe('delete');
    const form = () => s.wrapper.findComponent(ReservationFormModal);
    await s.action('edit', PENDING);
    expect([form().props('open'), form().props('reservation')]).toEqual([true, PENDING]);
    form().vm.$emit('update:open', false);
    s.table().vm.$emit('rowClick', SEATED);
    await flush();
    expect(form().props('reservation')).toEqual(SEATED);
  });

  it('«New reservation» opens an empty one on the day of the book', async () => {
    const s = await setup();
    await s.show([PENDING]);
    s.table().vm.$emit('add');
    await flush();
    const form = s.wrapper.findComponent(ReservationFormModal);
    expect([form.props('open'), form.props('reservation'), form.props('day')]).toEqual([true, null, '2026-10-15']);
  });

  it('an empty day says so and offers a new one; a search without matches offers to clear it', async () => {
    const s = await setup();
    await s.show([]);
    const empty = () => s.wrapper.findComponent(EmptyState);
    expect([empty().props('heading'), empty().props('message')]).toEqual([
      'No reservations this day',
      'Bookings you take by phone, online or at the door show up here, with the table held for the guest until they arrive.',
    ]);
    await click(s.find('reservation-list-empty-new').element);
    expect(s.wrapper.findComponent(ReservationFormModal).props('open')).toBe(true);
    s.table().vm.$emit('update:search', 'zzz');
    await flush();
    await s.result(OP, page([]));
    expect(empty().props('heading')).toBe('No reservations match your search');
    await click(s.find('reservation-list-clear').element);
    expect(s.list()).toEqual([{ date_from: '2026-10-15', date_to: '2026-10-15', sort: 'starts_at', limit: 50, offset: 0 }]);
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.show([PENDING]);
    expect(s.cells(0).slice(0, 7)).toEqual(['15/10/2026', '21:00', 'Ana García', '+34 600 111 222', '4', '5 (Terrace)', 'Pendiente']);
    expect([s.prop('searchPlaceholder'), s.prop<{ add: string }>('labels').add]).toEqual(['Buscar cliente, teléfono o correo…', 'Nueva reserva']);
  });
});

describe('ReservationsPage: the list fills the page (FIX-DATATABLE-HUB)', () => {
  it('keeps its column filters behind the table’s funnel, as the old table: the list is not pushed down', async () => {
    const s = await setup();
    expect(s.prop('filterable')).toBe(true);
  });

  it('AppPage `fill` and its DataTable `fill`, only stacks between them: from the topbar to the tabbar', async () => {
    const s = await setup();
    expect(listFillProblems(s.wrapper)).toEqual([]);
  });
});
