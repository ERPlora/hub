// Reservations → Availability (WORKBOOK «Pantallas · Disponibilidad»; RESERVATION-F01, F02, F05): three
// sections. Occupancy — a date (today) with its opening hours and blocks, and per slot Slot, Reserved, Max,
// Guests and Available («Full» dimmed, «Outside opening hours»); Time slots — Day, From, To, Max, Max
// guests, «Add slot», «Remove»; Blocked dates — Date, Reason, Full day, «Add blocked date», «Remove».
import { ConfirmDialog, DataTable } from '@erplora/ui/components';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import { EMPLOYEE, flush, ionValue, type MountOptions, mountReservation, page } from '../__tests__/mount-reservation';
import { blockedRow, dayOut, slotLoad, slotRow } from '../__tests__/rows';
import BlockedDateFormModal from '../components/BlockedDateFormModal.vue';
import SlotFormModal from '../components/SlotFormModal.vue';
import AvailabilityPage from './AvailabilityPage.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const DAY = dayOut({
  hours_restricted: true,
  spans: [{ start: '2026-10-15T13:00:00', end: '2026-10-15T16:00:00' }],
  slots: [
    slotLoad({ id: 's-lunch', start_time: '13:00:00', end_time: '16:00:00', reserved: 2, covers: 6, available: 8 }),
    slotLoad({ id: 's-dinner', reserved: 10, covers: 40, available: 0, full: true, max_covers: 40, in_hours: false }),
  ],
  blocks: [{ id: 'b0', date: '2026-10-15', reason: 'Private event', is_full_day: false, blocked_from: '22:00:00', blocked_until: '23:00:00' }],
});

async function setup(options: MountOptions = {}) {
  const m = await mountReservation(AvailabilityPage, { path: '/reservation/availability', ...options });
  await m.live();
  const tables = () => m.wrapper.findAllComponents(DataTable as unknown as Component);
  const table = (testid: string) => tables().find((tb) => (tb.props() as Record<string, unknown>).testid === testid)!;
  const tprop = (testid: string, name: string) => (table(testid).props() as Record<string, unknown>)[name];
  const rows = (testid: string) => m.wrapper.findAll(`[data-testid="${testid}-row"]`);
  const cells = (testid: string, i: number) => rows(testid)[i].findAll('[role="cell"]').map((c) => c.text().trim());
  const show = async () => {
    await m.result('reservation.availability.day', DAY);
    await m.result('reservation.time_slot.list', page([slotRow(), slotRow({ id: 'ts2', day_of_week: 5, start_time: '13:00:00', end_time: '16:00:00', max_covers: 30 })]));
    await m.result('reservation.blocked_date.list', page([blockedRow(), blockedRow({ id: 'b2', date: '2026-12-31', reason: 'Gala', is_full_day: false, blocked_from: '20:00:00', blocked_until: '23:00:00' })]));
  };
  const dialog = (testid: string) => m.wrapper.findAllComponents(ConfirmDialog).find((d) => d.props('testid') === testid)!;
  return { ...m, table, tprop, rows, cells, show, dialog };
}

describe('AvailabilityPage', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date('2026-10-15T10:00:00Z'));
  });
  afterEach(() => vi.useRealTimers());

  it('follows today’s occupancy, the slots and the blocked dates', async () => {
    const s = await setup();
    expect(s.params('reservation.availability.day')).toEqual([{ date: '2026-10-15' }]);
    expect(s.params('reservation.time_slot.list')).toEqual([{ sort: 'day_of_week', limit: 50, offset: 0 }]);
    expect(s.params('reservation.blocked_date.list')).toEqual([{ sort: 'date', limit: 50, offset: 0 }]);
  });

  it('gives each slot of the day what it holds; a full one dimmed with «Full», one outside the hours marked', async () => {
    const s = await setup();
    await s.show();
    expect(s.find('reservation-availability-hours').text()).toBe('Opening hours: 1:00 PM–4:00 PM');
    expect(s.find('reservation-availability-blocks').text()).toBe('Blocked 10:00 PM–11:00 PM: Private event');
    expect(s.cells('reservation-availability-occupancy', 0)).toEqual(['1:00 PM–4:00 PM', '2', '10', '6', '8']);
    expect(s.cells('reservation-availability-occupancy', 1)).toEqual(['8:00 PM–11:30 PM', '10', '10', '40 / 40', 'Full Outside opening hours']);
    expect(s.rows('reservation-availability-occupancy')[1].find('.reservation-availability__full').exists()).toBe(true);
    // By their start, as the server gives them: the occupancy is not sorted (as the old table).
    const columns = s.tprop('reservation-availability-occupancy', 'columns') as Array<{ sortable?: boolean }>;
    expect(columns.map((column) => column.sortable)).toEqual([false, false, false, false, false]);
  });

  it('says when Schedules does not limit the day, or closes it', async () => {
    const s = await setup();
    await s.result('reservation.availability.day', dayOut());
    expect(s.find('reservation-availability-hours').text()).toBe('No confirmed opening hours in Schedules: they do not limit the book.');
    await s.result('reservation.availability.day', dayOut({ hours_restricted: true, spans: [] }), {}, 2);
    expect(s.find('reservation-availability-hours').text()).toBe('The business is closed this day (Schedules).');
  });

  it('moves the occupancy to another date', async () => {
    const s = await setup();
    await s.show();
    await ionValue(s.find('reservation-availability-date').element, '2026-10-17');
    expect(s.params('reservation.availability.day')).toEqual([{ date: '2026-10-17' }]);
  });

  it('lists the slots with their day, and adds and removes them', async () => {
    const s = await setup();
    await s.show();
    expect(s.cells('reservation-availability-slots', 0).slice(0, 5)).toEqual(['Thursday', '8:00 PM', '11:30 PM', '10', '—']);
    expect(s.cells('reservation-availability-slots', 1).slice(0, 5)).toEqual(['Saturday', '1:00 PM', '4:00 PM', '10', '30']);
    s.table('reservation-availability-slots').vm.$emit('add');
    await flush();
    const form = s.wrapper.findComponent(SlotFormModal);
    expect([form.props('open'), form.props('weekday')]).toEqual([true, 3]);
    s.table('reservation-availability-slots').vm.$emit('action', { actionId: 'remove', row: slotRow() });
    await flush();
    const remove = s.dialog('reservation-availability-remove-slot');
    expect([remove.props('open'), remove.props('message')]).toEqual([
      true,
      'Thursday 8:00 PM–11:30 PM. No more reservations are taken in it; the ones it has stay.',
    ]);
    s.answer(200, { id: 'ts1' });
    remove.vm.$emit('confirm');
    await flush();
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/reservation/time_slots/delete', query: {}, body: { id: 'ts1' } }]);
  });

  it('lists the blocked dates, and blocks and unblocks them', async () => {
    const s = await setup();
    await s.show();
    expect(s.cells('reservation-availability-blocked', 0).slice(0, 3)).toEqual(['12/25/2026', 'Christmas', 'Whole day']);
    expect(s.cells('reservation-availability-blocked', 1).slice(0, 3)).toEqual(['12/31/2026', 'Gala', '8:00 PM–11:00 PM']);
    s.table('reservation-availability-blocked').vm.$emit('add');
    await flush();
    const form = s.wrapper.findComponent(BlockedDateFormModal);
    expect([form.props('open'), form.props('day')]).toEqual([true, '2026-10-15']);
    s.table('reservation-availability-blocked').vm.$emit('action', { actionId: 'remove', row: blockedRow() });
    await flush();
    s.answer(200, { id: 'b1' });
    s.dialog('reservation-availability-remove-blocked').vm.$emit('confirm');
    await flush();
    expect(s.sent().at(-1)).toMatchObject({ path: '/api/reservation/blocked_dates/delete', body: { id: 'b1' } });
  });

  it('keeps the filters of the slots and the blocked dates behind each table’s funnel, as the old table', async () => {
    const s = await setup();
    expect([s.tprop('reservation-availability-slots', 'filterable'), s.tprop('reservation-availability-blocked', 'filterable')]).toEqual([true, true]);
  });

  it('the host only looks', async () => {
    const s = await setup({ session: EMPLOYEE });
    await s.show();
    for (const testid of ['reservation-availability-slots', 'reservation-availability-blocked']) {
      expect([s.tprop(testid, 'addable'), s.tprop(testid, 'actions')]).toEqual([false, []]);
    }
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.show();
    expect(s.find('reservation-availability-hours').text()).toBe('Horario: 13:00–16:00');
    expect(s.cells('reservation-availability-occupancy', 1)[4]).toBe('Lleno Fuera de horario');
    expect(s.cells('reservation-availability-slots', 0)[0]).toBe('Jueves');
  });
});
