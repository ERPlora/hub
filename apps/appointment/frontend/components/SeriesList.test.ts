// «Repeating» (APPOINTMENT-F12 to F15): the series as a table — Customer, Service, Professional, Repeats
// («Every week · Monday · 11:00»), Starts, Ends («No end», «After {n} appointments» or the date) and an
// «Active» switch — with «Edit series», «Book appointments» and «Delete» (asked first) per row, and add.
// Booking runs turn after turn until the window is booked, then says what was booked and skipped.
import { ConfirmDialog, DataTable } from '@erplora/ui/components';
import { describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import type { MaterializeOut, RecurringOut } from '../operations';
import { ionChecked, mountAppointment, page, settle } from '../__tests__/mount-appointment';
import SeriesFormModal from './SeriesFormModal.vue';
import SeriesList from './SeriesList.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const OP = 'appointment.recurring.list';
const series = (id: string, over: Partial<RecurringOut> = {}): RecurringOut => ({
  id,
  customer_id: 'c1',
  customer_name: 'Lucía Pérez',
  staff_id: 's1',
  staff_name: 'Ana López',
  services: [{ service_id: 'cut', name: 'Haircut' }],
  service_names: 'Haircut',
  frequency: 'weekly',
  day_of_week: 0,
  time: '11:00:00',
  duration_minutes: 30,
  start_date: '2026-10-19',
  end_date: null,
  max_occurrences: null,
  is_active: true,
  split_from_id: null,
  created_at: '2026-10-14T10:00:00+02:00',
  ...over,
});
const outcome = (over: Partial<MaterializeOut>): MaterializeOut => ({
  recurring: series('r1'),
  booked: 50,
  already_booked: 0,
  skipped: [],
  next_from: null,
  to: '2027-01-12',
  upcoming_date: null,
  ...over,
});

async function setup() {
  const m = await mountAppointment(SeriesList, { props: { canAdd: true, canChange: true, businessToday: '2026-10-14' } });
  await m.live();
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const cells = (i: number) => m.wrapper.findAll('[data-testid="appointment-series-row"]')[i].findAll('[role="cell"]').map((c) => c.text().trim());
  return { ...m, table, cells };
}

describe('SeriesList', () => {
  it('follows the series and paints their rule as the old table', async () => {
    const s = await setup();
    expect(s.params(OP)).toEqual([{ sort: 'customer_name', limit: 100, offset: 0 }]);
    await s.result(OP, page([series('r1'), series('r2', { frequency: 'monthly', day_of_week: null, max_occurrences: 6, staff_id: null, staff_name: '' }), series('r3', { end_date: '2027-03-01' })], 3, 100));
    expect(s.cells(0).slice(0, 6)).toEqual(['Lucía Pérez', 'Haircut', 'Ana López', 'Every week · Monday · 11:00 AM', 'Oct 19, 2026', 'No end']);
    expect(s.cells(1).slice(2, 6)).toEqual(['Nobody: edit it', 'Every month · 11:00 AM', 'Oct 19, 2026', 'After 6 appointments']);
    expect(s.cells(2)[5]).toBe('Mar 1, 2027');
  });

  it('the Active switch pauses and reactivates a series', async () => {
    const s = await setup();
    await s.result(OP, page([series('r1')], 1, 100));
    s.answer(200, series('r1', { is_active: false }));
    await ionChecked(s.find('appointment-series-toggle-r1').element, false);
    expect(s.sent().map((call) => [call.path, call.body])).toEqual([['/api/appointment/recurring/deactivate', { id: 'r1' }]]);
  });

  it('«Book appointments» books turn after turn and says what was booked and skipped', async () => {
    const s = await setup();
    await s.result(OP, page([series('r1')], 1, 100));
    const answers = [
      outcome({ next_from: '2026-12-08', to: '2027-01-12' }),
      outcome({ booked: 4, skipped: [{ occurrence_date: '2026-12-08', code: 'outside_schedule', message: 'Closed.' }] }),
    ];
    s.net.onApi(() => Response.json(answers.shift(), { status: 200 }));
    s.table().vm.$emit('action', { actionId: 'materialize', row: series('r1') });
    await settle();
    await settle();
    expect(s.sent().map((call) => call.body)).toEqual([{ id: 'r1' }, { id: 'r1', from_date: '2026-12-08', to_date: '2027-01-12' }]);
    expect(s.find('appointment-series-outcome').text()).toContain('54 appointments booked · 1 could not be booked');
    expect(s.find('appointment-series-outcome').text()).toContain('Tuesday, December 8, 2026: Closed.');
  });

  // APPOINTMENT-F14 · appointments#256, #293, #220: saving an edit says to whom the appointments go, only what
  // happened, and each one that kept its time with its date as the reader reads dates.
  it('after «Edit series» says who the appointments go to and what kept its time', async () => {
    const s = await setup();
    await s.result(OP, page([series('r1')], 1, 100));
    s.wrapper.findComponent(SeriesFormModal).vm.$emit(
      'updated',
      {
        recurring: series('r1', { staff_name: 'Bea Ruiz' }),
        moved: 3,
        cancelled: 0,
        locked: 0,
        skipped: [{ occurrence_date: '2026-09-26', code: 'blocked', message: 'Blocked.' }],
        booked: 0,
      },
      { id: 'r1', from_date: '2026-09-21', staff_id: 'm2' },
    );
    await settle();
    const said = s.find('appointment-series-outcome').text();
    expect(said).toContain('3 appointments now with Bea Ruiz · 1 could not be moved and keep their time:');
    expect(said).toContain('Saturday, September 26, 2026: Blocked.');
    expect(said).not.toContain('0 cancelled');
  });

  it('«Delete» asks first, «Edit series» and add open the panel', async () => {
    const s = await setup();
    await s.result(OP, page([series('r1')], 1, 100));
    s.table().vm.$emit('action', { actionId: 'delete', row: series('r1') });
    await settle();
    const dialog = s.wrapper.findComponent(ConfirmDialog);
    expect([dialog.props('open'), dialog.props('title')]).toEqual([true, 'Delete Lucía Pérez’s repeating appointments?'.replace('’', "'")]);
    s.answer(200, { id: 'r1' });
    dialog.vm.$emit('confirm');
    await settle();
    expect(s.sent().at(-1)).toMatchObject({ path: '/api/appointment/recurring/delete', body: { id: 'r1' } });
    s.table().vm.$emit('action', { actionId: 'edit', row: series('r1') });
    await settle();
    expect(s.wrapper.findComponent(SeriesFormModal).props()).toMatchObject({ open: true, series: series('r1') });
    s.table().vm.$emit('add');
    await settle();
    expect(s.wrapper.findComponent(SeriesFormModal).props()).toMatchObject({ open: true, series: null });
  });
});
