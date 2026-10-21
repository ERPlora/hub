// Reservations → Waitlist (WORKBOOK «Pantallas · Lista de espera»; RESERVATION-F14 to F16): who waits, in
// the order they were written down — Date, Pref. time, Guest, Phone, Party, Contacted and Status —, search
// and filters, «Add guest»; per row Contacted, Convert (a full slot asks first: «Convert anyway») and
// Remove (asks first). Empty: «Waitlist is empty.».
import { ConfirmDialog, DataTable, EmptyState } from '@erplora/ui/components';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import { flush, type MountOptions, mountReservation, page } from '../__tests__/mount-reservation';
import { entryRow, reservationRow } from '../__tests__/rows';
import WaitlistFormModal from '../components/WaitlistFormModal.vue';
import WaitlistPage from './WaitlistPage.vue';
import { listFillProblems } from '../../../../frontend/testing/list-fill';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const OP = 'reservation.waitlist.list';
const WAITING = entryRow();
const CONTACTED = entryRow({ id: 'w2', guest_name: '', is_contacted: true, preferred_time: '21:30:00' });
const CONVERTED = entryRow({ id: 'w3', guest_name: 'Pepa', is_converted: true, reservation_id: 'r9' });

async function setup(options: MountOptions = {}) {
  const m = await mountReservation(WaitlistPage, { path: '/reservation/waitlist', ...options });
  await m.live();
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const rows = () => m.wrapper.findAll('[data-testid="reservation-waitlist-row"]');
  const cells = (i: number) => rows()[i].findAll('[role="cell"]').map((c) => c.text().trim());
  const action = (actionId: string, row: unknown) => {
    table().vm.$emit('action', { actionId, row });
    return flush();
  };
  const visible = (row: unknown) =>
    prop<Array<{ id: string; hidden?: (r: unknown) => boolean }>>('actions')
      .filter((a) => !a.hidden?.(row))
      .map((a) => a.id);
  const dialog = (testid: string) => m.wrapper.findAllComponents(ConfirmDialog).find((d) => d.props('testid') === testid)!;
  return { ...m, table, prop, rows, cells, action, visible, dialog, list: () => m.params(OP) };
}

describe('WaitlistPage', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date('2026-10-15T10:00:00Z'));
  });
  afterEach(() => vi.useRealTimers());

  it('lists who waits in the order they were written down', async () => {
    const s = await setup();
    expect(s.list()).toEqual([{ sort: 'position', limit: 50, offset: 0 }]);
    await s.result(OP, page([WAITING, CONTACTED, CONVERTED]));
    expect(s.prop<Array<{ key: string; label: string }>>('columns').map((c) => [c.key, c.label])).toEqual([
      ['date', 'Date'],
      ['preferred_time', 'Pref. time'],
      ['guest_name', 'Guest'],
      ['guest_phone', 'Phone'],
      ['party_size', 'Party'],
      ['is_contacted', 'Contacted'],
      ['is_converted', 'Status'],
    ]);
    expect(s.cells(0).slice(0, 7)).toEqual(['10/15/2026', '9:00 PM', 'Luis Pérez', '+34600333444', '2', 'No', 'Waiting']);
    expect(s.cells(1).slice(2, 7)).toEqual(['Deleted customer', '+34600333444', '2', 'Yes', 'Waiting']);
    expect(s.cells(2)[6]).toBe('Converted');
    expect([s.prop('searchPlaceholder'), s.prop<{ add: string }>('labels').add]).toEqual(['Search guest, phone or email…', 'Add guest']);
  });

  it('searches and filters on the server', async () => {
    const s = await setup();
    await s.result(OP, page([WAITING]));
    s.table().vm.$emit('update:search', 'luis');
    s.table().vm.$emit('filtersChange', { is_contacted: 'false', is_converted: 'false', date: '2026-10-15' });
    await flush();
    expect(s.list()).toEqual([
      { search: 'luis', is_contacted: false, is_converted: false, date_from: '2026-10-15', date_to: '2026-10-15', sort: 'position', limit: 50, offset: 0 },
    ]);
  });

  it('offers Contacted until called, Convert until converted, and Remove', async () => {
    const s = await setup();
    await s.result(OP, page([WAITING]));
    expect(s.visible(WAITING)).toEqual(['contact', 'convert', 'remove']);
    expect(s.visible(CONTACTED)).toEqual(['convert', 'remove']);
    expect(s.visible(CONVERTED)).toEqual(['remove']);
  });

  it('marks contacted and converts at once; a full slot asks before converting anyway', async () => {
    const s = await setup();
    await s.result(OP, page([WAITING]));
    s.answer(200, { ...WAITING, is_contacted: true });
    await s.action('contact', WAITING);
    const message = 'That time slot is fully booked for that date.';
    s.answer(409, { error: { code: 'reservation.no_capacity', message, fields: { time: message, overbook: 'Send overbook as true.' } } });
    await s.action('convert', WAITING);
    await flush();
    expect([s.dialog('reservation-waitlist-overbook').props('open'), s.dialog('reservation-waitlist-overbook').props('confirmLabel')]).toEqual([
      true,
      'Convert anyway',
    ]);
    s.answer(200, { entry: { ...WAITING, is_converted: true, reservation_id: 'r1' }, reservation: reservationRow() });
    s.dialog('reservation-waitlist-overbook').vm.$emit('confirm');
    await flush();
    await flush();
    expect(s.sent().map((call) => [call.path, call.body])).toEqual([
      ['/api/reservation/waitlist/update', { id: 'w1', is_contacted: true }],
      ['/api/reservation/waitlist/convert', { id: 'w1', overbook: false }],
      ['/api/reservation/waitlist/convert', { id: 'w1', overbook: true }],
    ]);
    expect(s.find('reservation-waitlist-outcome').text()).toBe('Ana García now has a reservation on Thursday, October 15 · 9:00 PM.');
  });

  it('a full slot the server does not let overbook is said above the list', async () => {
    const s = await setup();
    await s.result(OP, page([WAITING]));
    s.answer(409, { error: { code: 'reservation.no_capacity', message: 'That time slot is fully booked for that date.' } });
    await s.action('convert', WAITING);
    await flush();
    expect(s.dialog('reservation-waitlist-overbook').props('open')).toBe(false);
    expect(s.find('reservation-waitlist-page-error').text()).toContain('That time slot is fully booked for that date.');
  });

  it('removing asks first', async () => {
    const s = await setup();
    await s.result(OP, page([WAITING]));
    await s.action('remove', WAITING);
    const remove = s.dialog('reservation-waitlist-remove');
    expect([remove.props('open'), remove.props('message')]).toEqual([true, 'Luis Pérez · Thursday, October 15 · 9:00 PM.']);
    s.answer(200, { id: 'w1' });
    remove.vm.$emit('confirm');
    await flush();
    expect(s.sent().at(-1)).toMatchObject({ path: '/api/reservation/waitlist/delete', body: { id: 'w1' } });
  });

  it('«Add guest» opens the form on today; an empty list says so', async () => {
    const s = await setup();
    await s.result(OP, page([]));
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('Waitlist is empty.');
    s.table().vm.$emit('add');
    await flush();
    const form = s.wrapper.findComponent(WaitlistFormModal);
    expect([form.props('open'), form.props('day')]).toEqual([true, '2026-10-15']);
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.result(OP, page([WAITING]));
    expect(s.cells(0).slice(0, 7)).toEqual(['15/10/2026', '21:00', 'Luis Pérez', '+34600333444', '2', 'No', 'En espera']);
    expect(s.prop<{ add: string }>('labels').add).toBe('Añadir cliente');
  });
});

describe('WaitlistPage: the list fills the page (FIX-DATATABLE-HUB)', () => {
  it('keeps its column filters behind the table’s funnel, as the old table: the list is not pushed down', async () => {
    const s = await setup();
    expect(s.prop('filterable')).toBe(true);
  });

  it('AppPage `fill` and its DataTable `fill`, only stacks between them: from the topbar to the tabbar', async () => {
    const s = await setup();
    expect(listFillProblems(s.wrapper)).toEqual([]);
  });
});
