// Schedules → Hours (SCHEDULE-F01, F02, F03; WORKBOOK «Pantallas · Horario»): the live
// `schedule.week.get` as seven fixed rows — Day, Hours and Status, in the order of «Week starts» —, no
// «+» (a day is edited, never added); «Edit» or the row opens «Edit hours — {day}». While the week is
// the default one, the yellow notice with «Yes, these are my hours» (`schedule.week.confirm`). Every state
// of the screen: loading, error with Retry, reconnecting, app inactive, read-only for an employee.
import { DataTable, InlineFeedback } from '@erplora/ui/components';
import { AppPage } from '@erplora/ui/shell';
import { describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import type { WeekDayOut, WeekOut } from '../operations';
import { EMPLOYEE, errorFrame, flush, type MountOptions, mountSchedule, settle } from '../__tests__/mount-schedule';
import DayHoursModal from '../components/DayHoursModal.vue';
import HoursPage from './HoursPage.vue';
import { listFillProblems } from '../../../../frontend/testing/list-fill';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const OP = 'schedule.week.get';
const NINE_TO_SIX = [{ open_time: '09:00:00', close_time: '18:00:00' }];
const day = (weekday: number, over: Partial<WeekDayOut> = {}): WeekDayOut => ({
  weekday,
  name: '',
  id: `d${weekday}`,
  is_set: true,
  is_closed: false,
  intervals: NINE_TO_SIX,
  ...over,
});
const WEEK: WeekOut = {
  week_starts_on: 1,
  confirmed: false,
  timezone: 'Europe/Madrid',
  days: [
    day(0, { intervals: [
      { open_time: '10:00:00', close_time: '14:00:00' },
      { open_time: '17:00:00', close_time: '20:00:00' },
    ] }),
    day(1),
    day(2, { intervals: [{ open_time: '00:00:00', close_time: '00:00:00' }] }),
    day(3, { id: null, is_set: false, intervals: [] }),
    day(4),
    day(5, { is_closed: true, intervals: [] }),
    day(6, { is_closed: true, intervals: [] }),
  ],
};

async function setup(options: MountOptions = {}) {
  const m = await mountSchedule(HoursPage, { path: '/schedule/hours', ...options });
  await m.live();
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const rows = () => m.wrapper.findAll('[data-testid="schedule-hours-row"]');
  const cells = (i: number) => rows()[i].findAll('[role="cell"]').map((c) => c.text().trim());
  return { ...m, table, prop, rows, cells, show: (data: unknown) => m.result(OP, data) };
}

describe('HoursPage', () => {
  it('follows schedule.week.get and sits under «Schedules» with the three tabs', async () => {
    const s = await setup();
    expect(s.params(OP)).toEqual([{}]);
    const page = s.wrapper.findComponent(AppPage);
    expect(page.props('title')).toBe('Schedules');
    expect((page.props('tabs') as Array<{ id: string; to: string }>).map((t) => [t.id, t.to])).toEqual([
      ['hours', '/schedule/hours'],
      ['special_days', '/schedule/special-days'],
      ['settings', '/schedule/settings'],
    ]);
    expect(s.find('schedule-hours-loading').exists()).toBe(true);
  });

  it('paints the seven days: Day, Hours and Status; no «+»', async () => {
    const s = await setup();
    await s.show(WEEK);
    expect(s.prop<Array<{ key: string; label: string }>>('columns').map((c) => [c.key, c.label])).toEqual([
      ['weekday', 'Day'],
      ['hours', 'Hours'],
      ['status', 'Status'],
    ]);
    expect(s.rows()).toHaveLength(7);
    expect(s.cells(0).slice(0, 3)).toEqual(['Monday', '10:00 AM–02:00 PM · 05:00 PM–08:00 PM', 'Open']);
    expect(s.cells(2).slice(0, 3)).toEqual(['Wednesday', 'Open 24 hours', 'Open']);
    expect(s.cells(3).slice(0, 3)).toEqual(['Thursday', 'Not set', '—']);
    expect(s.cells(5).slice(0, 3)).toEqual(['Saturday', 'Closed', 'Closed']);
    expect(s.prop('addable')).toBe(false);
  });

  it('keeps the old toolbar: «Columns» beside the table/cards switch (SCHEDULE-F01, reference shot)', async () => {
    const s = await setup();
    await s.show(WEEK);
    expect(s.prop('columnPicker')).toBe(true);
    expect(s.prop('views')).toEqual(['table', 'cards']);
  });

  it('the rows come in the order the server gives (the week starts on Sunday)', async () => {
    const s = await setup();
    await s.show({ ...WEEK, week_starts_on: 7, days: [WEEK.days[6], ...WEEK.days.slice(0, 6)] });
    expect(s.cells(0)[0]).toBe('Sunday');
  });

  it('«Edit» or the row opens «Edit hours — {day}» with that day', async () => {
    const s = await setup();
    await s.show(WEEK);
    expect(s.prop<Array<{ id: string }>>('actions').map((a) => a.id)).toEqual(['edit']);
    expect(s.prop('rowClickable')).toBe(true);
    const modal = () => s.wrapper.findComponent(DayHoursModal);
    s.table().vm.$emit('rowClick', WEEK.days[1]);
    await flush();
    expect([modal().props('open'), modal().props('day')]).toEqual([true, WEEK.days[1]]);
    modal().vm.$emit('update:open', false);
    s.table().vm.$emit('action', { actionId: 'edit', row: WEEK.days[5] });
    await flush();
    expect(modal().props('day')).toEqual(WEEK.days[5]);
  });

  it('the default week says so, and «Yes, these are my hours» confirms it', async () => {
    const s = await setup();
    await s.show(WEEK);
    expect(s.find('schedule-hours-default-week').text()).toContain(
      'These are default opening hours we set up for you. Check they match your business — bookings outside them are refused.',
    );
    s.answer(200, { ...WEEK, confirmed: true });
    await s.find('schedule-hours-confirm-week').trigger('click');
    await settle();
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/schedule/week/confirm', query: {}, body: {} }]);
    await s.show({ ...WEEK, confirmed: true });
    expect(s.find('schedule-hours-default-week').exists()).toBe(false);
  });

  it('a refused confirmation is said above the table', async () => {
    const s = await setup();
    await s.show(WEEK);
    s.answer(409, { error: { code: 'schedule.no_week', message: 'There are no weekly opening hours to confirm.' } });
    await s.find('schedule-hours-confirm-week').trigger('click');
    await settle();
    expect(s.find('schedule-hours-error').text()).toContain('There are no weekly opening hours to confirm.');
  });

  it('an employee reads the week and the notice, with no button nor edit', async () => {
    const s = await setup({ session: EMPLOYEE });
    await s.show(WEEK);
    expect([s.prop('actions'), s.prop('rowClickable')]).toEqual([[], false]);
    expect(s.find('schedule-hours-default-week').exists()).toBe(true);
    expect(s.find('schedule-hours-confirm-week').exists()).toBe(false);
    expect(s.wrapper.findComponent(DayHoursModal).exists()).toBe(false);
  });

  it('a failure is the table’s, with «Retry»; the app off replaces the table', async () => {
    const s = await setup();
    s.net.lastStream().push(errorFrame(s.subId(OP), 'boom'));
    await flush();
    expect(s.prop('error')).toBe('msg boom');
    const off = await setup();
    off.net.lastStream().push(errorFrame(off.subId(OP), 'app_inactive'));
    await flush();
    expect(off.wrapper.findComponent(DataTable as unknown as Component).exists()).toBe(false);
    expect(off.wrapper.findAllComponents(InlineFeedback).map((b) => b.attributes('data-testid'))).toContain('schedule-hours-inactive');
  });

  it('a table that does not load names what failed, then the cause, never the generic text (pm#610)', async () => {
    const s = await setup({ locale: 'es' });
    s.net.lastStream().push(errorFrame(s.subId(OP), 'boom'));
    await flush();
    const box = s.wrapper.find('.data-table__error');
    expect(box.find('.data-table__error-title').text()).toBe('No se ha podido cargar el horario.');
    expect(box.find('.data-table__error-reason').text()).toBe('msg boom');
    expect(box.text()).not.toContain('No se han podido cargar los datos');
  });

  it('speaks Spanish with the old words', async () => {
    const s = await setup({ locale: 'es' });
    await s.show(WEEK);
    expect(s.wrapper.findComponent(AppPage).props('title')).toBe('Horarios');
    expect(s.cells(0).slice(0, 3)).toEqual(['Lunes', '10:00–14:00 · 17:00–20:00', 'Abierto']);
    expect(s.cells(3).slice(1, 3)).toEqual(['Sin definir', '—']);
    expect(s.find('schedule-hours-confirm-week').text()).toBe('Sí, este es mi horario');
  });
});

describe('HoursPage: the list fills the page (FIX-DATATABLE-HUB)', () => {
  it('AppPage `fill` and its DataTable `fill`, only stacks between them: from the topbar to the tabbar', async () => {
    const s = await setup();
    expect(listFillProblems(s.wrapper)).toEqual([]);
  });
});
