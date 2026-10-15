// «Special days» of Schedules → Special days (SCHEDULE-F04, F06, F13; WORKBOOK «Pantallas»): the live
// `schedule.special_day.list` in a server-side DataTable — Date, Name, Status (closed or its hours) and
// Yearly —, «Search special day…», filters by date (from–to), name, status and yearly, sort by column,
// 50 a page by date. «+» opens «New special day» for whoever can add; a row or «Edit» opens «Edit ·
// {name}» for whoever can change; «Delete» asks ««{name}» will be deleted…» first. An employee only
// reads.
import { ConfirmDialog, DataTable, EmptyState } from '@erplora/ui/components';
import { describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import type { SpecialDayOut } from '../operations';
import { EMPLOYEE, errorFrame, flush, type MountOptions, mountSchedule, page, settle } from '../__tests__/mount-schedule';
import FilterPanel from './FilterPanel.vue';
import SpecialDayFormModal from './SpecialDayFormModal.vue';
import SpecialDaysList from './SpecialDaysList.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const OP = 'schedule.special_day.list';
const day = (id: string, over: Partial<SpecialDayOut> = {}): SpecialDayOut => ({
  id,
  date: '2026-12-25',
  name: 'Christmas',
  is_closed: true,
  recurring_yearly: true,
  notes: '',
  intervals: [],
  ...over,
});
const ROWS = [
  day('sd1', { date: '2026-12-24', name: 'Christmas Eve', is_closed: false, recurring_yearly: false, intervals: [
    { open_time: '10:00:00', close_time: '13:00:00' },
    { open_time: '17:00:00', close_time: '19:00:00' },
  ] }),
  day('sd2'),
];

async function setup(options: MountOptions = {}) {
  const m = await mountSchedule(SpecialDaysList, { path: '/schedule/special-days', ...options });
  await m.live();
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const rows = () => m.wrapper.findAll('[data-testid="schedule-special-days-row"]');
  const cells = (i: number) => rows()[i].findAll('[role="cell"]').map((c) => c.text().trim());
  async function action(id: string, actionId: string) {
    await m.find(`schedule-special-days-row-${id}-${actionId}`).trigger('click');
    await settle();
  }
  async function filter(values: Record<string, string>) {
    m.wrapper.findComponent(FilterPanel).vm.$emit('update:modelValue', values);
    await flush();
  }
  return { ...m, table, prop, rows, cells, action, filter, show: (data: unknown) => m.result(OP, data) };
}

describe('SpecialDaysList', () => {
  it('follows schedule.special_day.list, 50 by date from the first, under «Special days»', async () => {
    const s = await setup();
    expect(s.params(OP)).toEqual([{ sort: 'date', dir: 'asc', limit: 50, offset: 0 }]);
    expect(s.find('schedule-special-days-heading').text()).toBe('Special days');
    await s.show(page(ROWS));
    expect(s.table().props()).toMatchObject({ serverSide: true, searchable: true, testid: 'schedule-special-days', pageSize: 50, total: 2 });
    expect(s.prop('searchPlaceholder')).toBe('Search special day…');
  });

  it('paints Date, Name, Status and Yearly; an open day says its hours', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    expect(s.prop<Array<{ key: string; label: string; sortable?: boolean }>>('columns').map((c) => [c.key, c.label, !!c.sortable])).toEqual([
      ['date', 'Date', true],
      ['name', 'Name', true],
      ['is_closed', 'Status', true],
      ['recurring_yearly', 'Yearly', true],
    ]);
    expect(s.cells(0).slice(0, 4)).toEqual(['12/24/2026', 'Christmas Eve', '10:00 AM–01:00 PM · 05:00 PM–07:00 PM', 'No']);
    expect(s.cells(1).slice(0, 4)).toEqual(['12/25/2026', 'Christmas', 'Closed', 'Yes']);
  });

  it('the filters and the search ask the server again from the first page', async () => {
    const s = await setup();
    await s.filter({ date_from: '2026-12-01', date_to: '2026-12-31', is_closed: 'false', recurring_yearly: 'true', name: 'eve' });
    await s.reopen();
    expect(s.params(OP)).toEqual([
      { date_from: '2026-12-01', date_to: '2026-12-31', is_closed: false, recurring_yearly: true, name: 'eve', sort: 'date', dir: 'asc', limit: 50, offset: 0 },
    ]);
    s.table().vm.$emit('sortChange', { sort: 'name', dir: 'desc' });
    await flush();
    await s.reopen();
    expect(s.params(OP)[0]).toMatchObject({ sort: 'name', dir: 'desc' });
  });

  it('«Sin días especiales.» when there is none; «No results» when a filter finds nothing', async () => {
    const s = await setup();
    await s.show(page([]));
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No special days.');
    await s.filter({ name: 'x' });
    await s.reopen();
    await s.show(page([]));
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No results');
  });

  it('who can add opens «New special day»; a row or «Edit» opens it with the day', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    expect([s.prop('addable'), s.prop('rowClickable')]).toEqual([true, true]);
    expect(s.prop<Array<{ id: string; icon: string }>>('actions').map((a) => [a.id, a.icon])).toEqual([
      ['edit', 'create-outline'],
      ['delete', 'trash-outline'],
    ]);
    const modal = () => s.wrapper.findComponent(SpecialDayFormModal);
    s.table().vm.$emit('add');
    await flush();
    expect([modal().props('open'), modal().props('specialDay')]).toEqual([true, null]);
    modal().vm.$emit('update:open', false);
    s.table().vm.$emit('rowClick', ROWS[1]);
    await flush();
    expect([modal().props('open'), modal().props('specialDay')]).toEqual([true, ROWS[1]]);
  });

  it('«Delete» asks first with the name, then sends schedule.special_day.delete; a refusal goes above the table', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    s.answer(404, { error: { code: 'not_found', message: 'That special day does not exist in this business.' } });
    await s.action('sd2', 'delete');
    const dialog = s.wrapper.findComponent(ConfirmDialog);
    expect([dialog.props('open'), dialog.props('title'), dialog.props('message'), dialog.props('confirmLabel')]).toEqual([
      true,
      'Delete',
      '«Christmas» will be deleted. This cannot be undone.',
      'Delete',
    ]);
    dialog.vm.$emit('confirm');
    await settle();
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/schedule/special_days/delete', query: {}, body: { id: 'sd2' } }]);
    expect(s.find('schedule-special-days-error').text()).toContain('That special day does not exist in this business.');
  });

  it('an employee only reads', async () => {
    const s = await setup({ session: EMPLOYEE });
    await s.show(page(ROWS));
    expect([s.prop('addable'), s.prop('rowClickable'), s.prop('actions')]).toEqual([false, false, []]);
  });

  it('a failure that is not a block is the table’s, with «Retry»', async () => {
    const s = await setup();
    s.net.lastStream().push(errorFrame(s.subId(OP), 'boom'));
    await flush();
    expect(s.prop('error')).toBe('msg boom');
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.show(page(ROWS));
    expect(s.find('schedule-special-days-heading').text()).toBe('Días especiales');
    expect(s.cells(0).slice(0, 4)).toEqual(['24/12/2026', 'Christmas Eve', '10:00–13:00 · 17:00–19:00', 'No']);
    expect(s.cells(1)[2]).toBe('Cerrado');
    expect(s.prop('searchPlaceholder')).toBe('Buscar día especial…');
  });
});
