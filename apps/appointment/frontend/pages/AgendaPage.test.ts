// Appointments → Agenda (WORKBOOK «Pantallas · Agenda»): the bar, and «List», «By professional» (day or
// week) or «Repeating», all live on the business's clock. The page follows the day's (or the week's)
// appointments — every one of them, in windows of 100 —, the agenda's rows, the blocks and the bookings
// to confirm; a tapped slot books there, an appointment opens its panel, a drag moves it, and the row
// actions run. An employee sees her own agenda, and is told when her account has no staff record.
import { describe, expect, it, vi } from 'vitest';

import type { AppointmentRow, LanesOut, SettingsOut } from '../operations';
import { AppPage } from '@erplora/ui/shell';

import { EMPLOYEE, mountAppointment, OWNER, page, settle } from '../__tests__/mount-appointment';
import AgendaToolbar from '../components/AgendaToolbar.vue';
import AppointmentFormModal from '../components/AppointmentFormModal.vue';
import AppointmentList from '../components/AppointmentList.vue';
import DayGrid from '../components/DayGrid.vue';
import SeriesList from '../components/SeriesList.vue';
import WeekBoard from '../components/WeekBoard.vue';
import AgendaPage from './AgendaPage.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const LIST = 'appointment.appointment.list';
const SETTINGS: SettingsOut = {
  default_duration: 60,
  min_booking_notice: 60,
  max_advance_booking: 90,
  allow_overlapping: true,
  allow_customer_cancellation: true,
  cancellation_notice_hours: 24,
  calendar_start_hour: 9,
  calendar_end_hour: 19,
  slot_interval: 15,
  auto_confirm_online: true,
  timezone: 'Europe/Madrid',
};
const LANES: LanesOut = {
  rows: [{ staff_id: 's1', name: 'Ana López', color: '', takes_bookings: true }],
  unassigned: 0,
  own_staff_id: null,
  sees_everyone: true,
  timezone: 'Europe/Madrid',
};
const row = (id: string, over: Partial<AppointmentRow> = {}): AppointmentRow => ({
  id,
  number: `APT-${id}`,
  customer_id: 'c1',
  customer_name: 'Lucía Pérez',
  staff_id: 's1',
  staff_name: 'Ana López',
  start: '2026-10-19T10:00:00+02:00',
  end: '2026-10-19T10:30:00+02:00',
  duration_minutes: 30,
  status: 'confirmed',
  source: 'counter',
  services: [],
  service_names: 'Haircut',
  total: 2000,
  booked_by_customer: false,
  sale_id: null,
  order_id: null,
  recurring_id: null,
  occurrence_date: null,
  ...over,
});

async function setup(session = OWNER) {
  const m = await mountAppointment(AgendaPage, { session, path: '/appointment/agenda' });
  await m.live();
  await m.result('appointment.settings.get', SETTINGS);
  await m.reopen();
  const toolbar = () => m.wrapper.findComponent(AgendaToolbar);
  const today = () => toolbar().props('today') as string;
  return { ...m, toolbar, today };
}

describe('AgendaPage', () => {
  it('follows today’s appointments on the business’s clock, its rows, its blocks and what waits for confirmation', async () => {
    const s = await setup();
    const day = s.today();
    expect(day).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(s.params(LIST)).toEqual([{ date_from: day, date_to: day, sort: 'start', limit: 100, offset: 0 }]);
    expect(s.params('appointment.agenda.lanes')).toEqual([{ date_from: day, date_to: day }]);
    expect(s.params('appointment.blocked_time.list')).toEqual([{ date_from: day, date_to: day, limit: 100 }]);
    expect(s.params('appointment.appointment.count_to_confirm')).toEqual([{}]);
    await s.result(LIST, { ...page([row('a1')], 1, 100), timezone: 'Europe/Madrid' });
    expect(s.wrapper.findComponent(AppointmentList).props('rows')).toEqual([row('a1')]);
  });

  it('asks every window when a day has more than a hundred appointments', async () => {
    const s = await setup();
    await s.result(LIST, { ...page([row('a1')], 230, 100), timezone: 'Europe/Madrid' });
    await s.reopen();
    expect(s.params(LIST).map((params) => params.offset)).toEqual([0, 100, 200]);
  });

  it('filters by status and steps the day', async () => {
    const s = await setup();
    s.toolbar().vm.$emit('update:status', 'pending');
    s.toolbar().vm.$emit('update:day', '2026-12-01');
    await s.reopen();
    expect(s.params(LIST)).toEqual([{ date_from: '2026-12-01', date_to: '2026-12-01', sort: 'start', status: 'pending', limit: 100, offset: 0 }]);
  });

  it('«By professional» paints the day grid with the calendar window, and a week the week board', async () => {
    const s = await setup();
    s.toolbar().vm.$emit('update:view', 'staff');
    await settle();
    await s.result('appointment.agenda.lanes', LANES);
    const grid = s.wrapper.findComponent(DayGrid);
    expect(grid.props()).toMatchObject({ startHour: 9, endHour: 19, slotInterval: 15, lanes: LANES.rows, canBook: true, canMove: true });
    s.toolbar().vm.$emit('update:span', 'week');
    s.toolbar().vm.$emit('update:day', '2026-10-21');
    await s.reopen();
    expect(s.params(LIST)[0]).toMatchObject({ date_from: '2026-10-19', date_to: '2026-10-25' });
    await s.result('appointment.agenda.lanes', LANES);
    expect(s.wrapper.findComponent(WeekBoard).props('days')).toHaveLength(7);
  });

  it('the day grid shades the hours the business is closed, read from Schedules for that day', async () => {
    const s = await setup();
    s.toolbar().vm.$emit('update:view', 'staff');
    await s.reopen();
    const day = s.today();
    expect(s.params('schedule.hours.for_range')).toEqual([{ date_from: day, date_to: day }]);
    const hours = { date: day, source: 'weekly', rule_id: null, name: '', is_closed: true, intervals: [], spans: [] };
    await s.result('appointment.agenda.lanes', LANES);
    await s.result('schedule.hours.for_range', { timezone: 'Europe/Madrid', days: [hours] });
    expect(s.wrapper.findComponent(DayGrid).props('hours')).toEqual(hours);
  });

  it('a tapped slot opens «New appointment» there; «Repeating» shows the series', async () => {
    const s = await setup();
    s.toolbar().vm.$emit('update:view', 'staff');
    await settle();
    await s.result('appointment.agenda.lanes', LANES);
    s.wrapper.findComponent(DayGrid).vm.$emit('slot', { staffId: 's1', staffName: 'Ana López', time: '16:30' });
    await settle();
    const form = s.wrapper.findComponent(AppointmentFormModal);
    expect(form.props()).toMatchObject({ open: true, appointment: null, preset: { day: s.today(), time: '16:30', staffId: 's1', staffName: 'Ana López' } });
    s.toolbar().vm.$emit('update:view', 'series');
    await settle();
    expect(s.wrapper.findComponent(SeriesList).exists()).toBe(true);
  });

  it('a drag moves the appointment to the time and row it was dropped on', async () => {
    const s = await setup();
    s.toolbar().vm.$emit('update:view', 'staff');
    await settle();
    await s.result('appointment.agenda.lanes', LANES);
    s.answer(200, row('a1'));
    s.wrapper.findComponent(DayGrid).vm.$emit('move', { row: row('a1'), staffId: 's1', time: '11:00' });
    await settle();
    expect(s.sent().at(-1)).toMatchObject({
      path: '/api/appointment/appointments/reschedule',
      body: { id: 'a1', start: `${s.today()}T11:00`, staff_id: 's1', confirm_overlap: false },
    });
  });

  it('an employee whose account has no staff record is told so', async () => {
    const s = await setup(EMPLOYEE);
    await s.result('appointment.agenda.lanes', { ...LANES, rows: [], own_staff_id: null, sees_everyone: false });
    expect(s.find('appointment-agenda-not-linked').text()).toBe(
      'Your account is not linked to any Staff record: there is no agenda of yours to show.',
    );
    expect(s.wrapper.findComponent(AppointmentList).props('canDelete')).toBe(false);
  });

  it('appointments left without a professional are pointed out', async () => {
    const s = await setup();
    await s.result('appointment.agenda.lanes', { ...LANES, unassigned: 2 });
    expect(s.find('appointment-agenda-unassigned').text()).toContain('2 appointments have no professional');
  });

  it('the Settings tab is only for who may change them', async () => {
    const tabs = async (session: typeof OWNER) =>
      ((await setup(session)).wrapper.findComponent(AppPage).props('tabs') as Array<{ id: string }>).map((tab) => tab.id);
    expect(await tabs(OWNER)).toEqual(['agenda', 'settings']);
    expect(await tabs(EMPLOYEE)).toEqual(['agenda']);
  });
});
