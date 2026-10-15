// Online booking → Bookings (WORKBOOK «Reservas (bandeja)»; ONLINE_BOOKING-F02 to F06, F08): the live
// `online_booking.booking.list` in a server-side DataTable — No., Customer (with her phone), Service,
// Professional, Date, Time, Status and Booked —, the newest first, «Search no., customer, phone, service…»,
// column filters, list or cards, 50 a page. Per row Confirm, Complete, No-show, Cancel (with its dialog and
// reason) and Delete (with its confirmation, only for who may delete), greyed out when the state does not
// allow them (the diary's rules). Changes come back through the stream.
import { ConfirmDialog, DataTable, EmptyState, InlineFeedback } from '@erplora/ui/components';
import { AppPage } from '@erplora/ui/shell';
import { describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import type { BookingRow } from '../operations';
import { EMPLOYEE, flush, MANAGER, type MountOptions, mountOnlineBooking, page, settle } from '../__tests__/mount-online-booking';
import CancelDialog from '../components/CancelDialog.vue';
import BookingsPage from './BookingsPage.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const OP = 'online_booking.booking.list';
const booking = (id: string, over: Partial<BookingRow> = {}): BookingRow => ({
  id,
  number: 'APT-20300305-0001',
  customer_id: 'c1',
  customer_name: 'Lucía Pérez',
  customer_phone: '+34600111222',
  customer_email: 'lucia@example.com',
  staff_id: 's1',
  staff_name: 'Ana López',
  services: [{ service_id: 'v1', name: 'Haircut', price: 2000, duration_minutes: 30 }],
  service_names: 'Haircut',
  start: '2030-03-05T10:00:00+01:00',
  end: '2030-03-05T10:30:00+01:00',
  duration_minutes: 30,
  status: 'pending',
  total: 2000,
  notes: '',
  booked_at: '2030-03-04T08:00:00+01:00',
  via_page: true,
  sale_id: null,
  order_id: null,
  ...over,
});
const ROWS = [booking('b1'), booking('b2', { number: 'APT-20300305-0002', status: 'confirmed', customer_name: '', customer_phone: '' })];

async function setup(options: MountOptions = {}) {
  const m = await mountOnlineBooking(BookingsPage, { path: '/online_booking/bookings', ...options });
  await m.live();
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const rows = () => m.wrapper.findAll('[data-testid="ob-bookings-row"]');
  const cells = (i: number) => rows()[i].findAll('[role="cell"]').map((c) => c.text().trim());
  const actions = () => prop<Array<{ id: string; disabled?: (r: BookingRow) => boolean }>>('actions');
  const enabled = (row: BookingRow) => actions().filter((a) => !a.disabled?.(row)).map((a) => a.id);
  return { ...m, table, prop, rows, cells, actions, enabled, list: () => m.params(OP), show: (data: unknown) => m.result(OP, data) };
}

describe('BookingsPage', () => {
  it('follows the online bookings, the newest first, 50 from the first', async () => {
    const s = await setup();
    expect(s.list()).toEqual([{ sort: 'booked_at', dir: 'desc', limit: 50, offset: 0 }]);
    await s.show(page(ROWS));
    expect(s.table().props()).toMatchObject({ serverSide: true, searchable: true, testid: 'ob-bookings', total: 2, views: ['table', 'cards'] });
    expect(s.prop('searchPlaceholder')).toBe('Search no., customer, phone, service…');
    expect(s.prop('addable')).toBe(false);
    const shell = s.wrapper.findComponent(AppPage);
    expect(shell.props('title')).toBe('Online booking');
    expect((shell.props('tabs') as Array<{ id: string }>).map((t) => t.id)).toEqual(['bookings', 'settings']);
  });

  it('paints No., Customer with her phone, Service, Professional, Date, Time, Status and Booked', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    expect(s.prop<Array<{ key: string; label: string }>>('columns').map((c) => [c.key, c.label])).toEqual([
      ['number', 'No.'],
      ['customer_name', 'Customer'],
      ['service_names', 'Service'],
      ['staff_name', 'Professional'],
      ['start', 'Date'],
      ['time', 'Time'],
      ['status', 'Status'],
      ['booked_at', 'Booked'],
    ]);
    const first = s.cells(0);
    expect(first.slice(0, 8)).toEqual([
      'APT-20300305-0001',
      expect.stringMatching(/Lucía Pérez\s*\+34600111222/),
      'Haircut',
      'Ana López',
      'Mar 5, 2030',
      '10:00 AM',
      'Pending',
      'Mar 4, 2030 · 8:00 AM',
    ]);
    expect(s.cells(1)[1]).toBe('Deleted customer');
  });

  it('filters by column, a day as its first and last day, and searches and sorts on the server', async () => {
    const s = await setup();
    s.table().vm.$emit('filtersChange', {
      number: '3',
      customer_name: 'luc',
      service: 'cut',
      staff_name: 'ana',
      date: '2030-03-05',
      status: 'pending',
    });
    await flush();
    expect(s.list()).toEqual([
      {
        number: '3',
        customer_name: 'luc',
        service: 'cut',
        staff_name: 'ana',
        date_from: '2030-03-05',
        date_to: '2030-03-05',
        status: 'pending',
        sort: 'booked_at',
        dir: 'desc',
        limit: 50,
        offset: 0,
      },
    ]);
    s.table().vm.$emit('filtersChange', {});
    s.table().vm.$emit('sortChange', { sort: 'start', dir: 'asc' });
    s.table().vm.$emit('update:search', 'lucia');
    await flush();
    expect(s.list()).toEqual([{ search: 'lucia', sort: 'start', dir: 'asc', limit: 50, offset: 0 }]);
  });

  it('says there are no online bookings yet, or that none matches', async () => {
    const s = await setup();
    await s.show(page([]));
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No online bookings yet.');
    s.table().vm.$emit('update:search', 'zz');
    await flush();
    await s.result(OP, page([]), { search: 'zz' });
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No booking matches the search.');
  });

  it('greys out what the state does not allow, and offers each person what they may do', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    expect(s.actions().map((a) => a.id)).toEqual(['confirm', 'complete', 'no_show', 'cancel', 'delete']);
    expect(s.enabled(ROWS[1])).toEqual(['complete', 'cancel', 'delete']);
    const manager = await setup({ session: MANAGER });
    expect(manager.actions().map((a) => a.id)).toEqual(['confirm', 'complete', 'no_show', 'cancel']);
    expect((manager.wrapper.findComponent(AppPage).props('tabs') as Array<{ id: string }>).map((t) => t.id)).toEqual(['bookings']);
    const employee = await setup({ session: EMPLOYEE });
    expect(employee.actions()).toEqual([]);
  });

  it('confirms, completes and marks a no-show through the inbox, and says why it could not', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    s.answer(200, { ...ROWS[0], status: 'confirmed' });
    s.table().vm.$emit('action', { actionId: 'confirm', row: ROWS[0] });
    await settle();
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/online_booking/bookings/confirm', query: {}, body: { id: 'b1' } }]);
    s.answer(409, { error: { code: 'appointment.no_show_too_early', message: 'It is not the appointment’s time yet.' } });
    s.table().vm.$emit('action', { actionId: 'no_show', row: ROWS[1] });
    await settle();
    const banner = s.wrapper.findAllComponents(InlineFeedback).find((b) => b.attributes('data-testid') === 'ob-bookings-row-error');
    expect(banner?.text()).toContain('It is not the appointment’s time yet.');
    expect(banner?.props('heading')).toBe('The booking could not be updated');
  });

  it('cancelling opens its dialog for that booking', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    s.table().vm.$emit('action', { actionId: 'cancel', row: ROWS[1] });
    await settle();
    const dialog = s.wrapper.findComponent(CancelDialog);
    expect([dialog.props('open'), dialog.props('booking')]).toEqual([true, ROWS[1]]);
  });

  it('deleting asks first and deletes on confirming', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    s.table().vm.$emit('action', { actionId: 'delete', row: ROWS[0] });
    await settle();
    const confirm = s.wrapper.findComponent(ConfirmDialog);
    expect(confirm.props('open')).toBe(true);
    expect(confirm.props('message')).toBe('Delete booking APT-20300305-0001? It is better to cancel it, which keeps its history.');
    s.answer(200, { id: 'b1', deleted: true });
    confirm.vm.$emit('confirm');
    await settle();
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/online_booking/bookings/delete', query: {}, body: { id: 'b1' } }]);
    expect(s.wrapper.findComponent(ConfirmDialog).props('open')).toBe(false);
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.show(page(ROWS));
    expect(s.prop<Array<{ label: string }>>('columns').map((c) => c.label)).toEqual([
      'Nº',
      'Cliente',
      'Servicio',
      'Profesional',
      'Fecha',
      'Hora',
      'Estado',
      'Reservada',
    ]);
    expect(s.cells(0)[6]).toBe('Pendiente');
  });
});
