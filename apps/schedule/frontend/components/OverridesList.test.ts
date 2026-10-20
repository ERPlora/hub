// «Overrides» of Schedules → Special days (SCHEDULE-F05, F06, F13; WORKBOOK «Pantallas»): the live
// `schedule.override.list` in a server-side DataTable — From, To, Reason and Status —, «Search
// override…», filters behind the table's funnel by its dates, reason and status, 50 a page by start. «+» opens «New override»; a
// row or «Edit» opens «Edit · {reason}»; «Delete» asks first. An employee only reads.
import { ConfirmDialog, DataTable, EmptyState } from '@erplora/ui/components';
import { describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import type { OverrideOut } from '../operations';
import { EMPLOYEE, errorFrame, flush, type MountOptions, mountSchedule, page, settle } from '../__tests__/mount-schedule';
import OverrideFormModal from './OverrideFormModal.vue';
import OverridesList from './OverridesList.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const OP = 'schedule.override.list';
const ROWS: OverrideOut[] = [
  { id: 'o1', start_date: '2026-04-01', end_date: '2026-04-05', reason: 'Easter', is_closed: true, intervals: [] },
  {
    id: 'o2',
    start_date: '2026-07-01',
    end_date: '2026-08-31',
    reason: 'Summer hours',
    is_closed: false,
    intervals: [{ open_time: '08:00:00', close_time: '15:00:00' }],
  },
];

async function setup(options: MountOptions = {}) {
  const m = await mountSchedule(OverridesList, { path: '/schedule/special-days', ...options });
  await m.live();
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const rows = () => m.wrapper.findAll('[data-testid="schedule-overrides-row"]');
  const cells = (i: number) => rows()[i].findAll('[role="cell"]').map((c) => c.text().trim());
  async function action(id: string, actionId: string) {
    await m.find(`schedule-overrides-row-${id}-${actionId}`).trigger('click');
    await settle();
  }
  async function filter(values: Record<string, string>) {
    table().vm.$emit('update:filters', values);
    await flush();
  }
  return { ...m, table, prop, rows, cells, action, filter, show: (data: unknown) => m.result(OP, data) };
}

describe('OverridesList', () => {
  it('follows schedule.override.list, 50 by start from the first, under «Overrides»', async () => {
    const s = await setup();
    expect(s.params(OP)).toEqual([{ sort: 'start_date', dir: 'asc', limit: 50, offset: 0 }]);
    expect(s.find('schedule-overrides-heading').text()).toBe('Overrides');
    await s.show(page(ROWS));
    expect(s.prop('searchPlaceholder')).toBe('Search override…');
  });

  it('paints From, To, Reason and Status', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    expect(s.prop<Array<{ key: string; label: string }>>('columns').map((c) => [c.key, c.label])).toEqual([
      ['start_date', 'From'],
      ['end_date', 'To'],
      ['reason', 'Reason'],
      ['is_closed', 'Status'],
    ]);
    expect(s.cells(0).slice(0, 4)).toEqual(['04/01/2026', '04/05/2026', 'Easter', 'Closed']);
    expect(s.cells(1).slice(0, 4)).toEqual(['07/01/2026', '08/31/2026', 'Summer hours', '08:00 AM–03:00 PM']);
  });

  it('filters behind the table funnel: from and to (each a range of days), reason and status on their columns', async () => {
    // flow: ninguno — FIX DataTable parte 2b-1 (PLAN-MIGRATIONS §13: filtros como en la vieja)
    const s = await setup();
    await s.show(page(ROWS));
    expect(s.prop('filterable')).toBe(true);
    type Filter = { type: string; key?: string; keys?: string[]; options?: Array<{ value: string; label: string }> };
    const columns = s.prop<Array<{ key: string; label: string; filter?: Filter }>>('columns');
    expect(columns.map((c) => [c.label, c.filter?.key ?? c.key, c.filter?.type, c.filter?.keys])).toEqual([
      ['From', 'start_date', 'daterange', ['start_from', 'start_to']],
      ['To', 'end_date', 'daterange', ['end_from', 'end_to']],
      ['Reason', 'reason', 'text', undefined],
      ['Status', 'is_closed', 'select', undefined],
    ]);
    expect(columns[3].filter?.options).toEqual([
      { value: 'true', label: 'Closed' },
      { value: 'false', label: 'Open' },
    ]);
  });

  it('the funnel panel applies on «Apply» and counts the filters in use', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    await s.find('schedule-overrides-filters-toggle').trigger('click');
    await flush();
    const panel = s.find('schedule-overrides-filters-panel');
    const set = (name: string, event: string, value: string) =>
      panel.get(`[data-testid="schedule-overrides-filter-${name}"]`).element.dispatchEvent(new CustomEvent(event, { detail: { value } }));
    set('end_to', 'ionChange', '2026-09-30');
    set('reason', 'ionInput', 'sum');
    set('is_closed', 'ionChange', 'true');
    await flush();
    await panel.get('[data-testid="schedule-overrides-filters-apply"]').trigger('click');
    await flush();
    await s.reopen();
    expect(s.params(OP)).toEqual([{ end_to: '2026-09-30', reason: 'sum', is_closed: true, sort: 'start_date', dir: 'asc', limit: 50, offset: 0 }]);
    expect(s.find('schedule-overrides-filters-count').text()).toBe('3');
  });

  it('its funnel and view buttons say they are the overrides’ (the screen has two lists; schedules#58)', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    const name = (hook: string) => s.find(`schedule-overrides-${hook}`).attributes('aria-label');
    expect([name('filters-toggle'), name('view-table'), name('view-cards')]).toEqual([
      'Override filters',
      'View overrides as list',
      'View overrides as cards',
    ]);
    await s.filter({ reason: 'sum', is_closed: 'false' });
    expect(name('filters-toggle')).toBe('Override filters (2 active)');
  });

  it('the filters ask the server again', async () => {
    const s = await setup();
    await s.filter({ start_from: '2026-06-01', end_to: '2026-09-30', reason: 'sum', is_closed: 'false' });
    await s.reopen();
    expect(s.params(OP)).toEqual([
      { start_from: '2026-06-01', end_to: '2026-09-30', reason: 'sum', is_closed: false, sort: 'start_date', dir: 'asc', limit: 50, offset: 0 },
    ]);
  });

  it('«No overrides.» when there is none', async () => {
    const s = await setup();
    await s.show(page([]));
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No overrides.');
  });

  it('adds, edits and deletes after asking', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    const modal = () => s.wrapper.findComponent(OverrideFormModal);
    s.table().vm.$emit('add');
    await flush();
    expect([modal().props('open'), modal().props('override')]).toEqual([true, null]);
    modal().vm.$emit('update:open', false);
    await s.action('o2', 'edit');
    expect([modal().props('open'), modal().props('override')]).toEqual([true, ROWS[1]]);
    s.answer(200, { id: 'o1' });
    await s.action('o1', 'delete');
    const dialog = s.wrapper.findComponent(ConfirmDialog);
    expect(dialog.props('message')).toBe('«Easter» will be deleted. This cannot be undone.');
    dialog.vm.$emit('confirm');
    await settle();
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/schedule/overrides/delete', query: {}, body: { id: 'o1' } }]);
  });

  it('an employee only reads', async () => {
    const s = await setup({ session: EMPLOYEE });
    await s.show(page(ROWS));
    expect([s.prop('addable'), s.prop('rowClickable'), s.prop('actions')]).toEqual([false, false, []]);
  });

  it('a list that does not load names itself, then the cause, never the generic text (pm#610)', async () => {
    const s = await setup({ locale: 'es' });
    s.net.lastStream().push(errorFrame(s.subId(OP), 'boom'));
    await flush();
    const box = s.wrapper.find('.data-table__error');
    expect(box.find('.data-table__error-title').text()).toBe('No se han podido cargar los cambios temporales.');
    expect(box.find('.data-table__error-reason').text()).toBe('msg boom');
    expect(box.text()).not.toContain('No se han podido cargar los datos');
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.show(page(ROWS));
    expect(s.find('schedule-overrides-heading').text()).toBe('Cambios temporales');
    expect(s.cells(1).slice(0, 4)).toEqual(['01/07/2026', '31/08/2026', 'Summer hours', '08:00–15:00']);
    const name = (hook: string) => s.find(`schedule-overrides-${hook}`).attributes('aria-label');
    expect([name('filters-toggle'), name('view-table'), name('view-cards')]).toEqual([
      'Filtros de cambios temporales',
      'Ver cambios temporales como lista',
      'Ver cambios temporales como tarjetas',
    ]);
    await s.filter({ reason: 'sum' });
    expect(name('filters-toggle')).toBe('Filtros de cambios temporales (1 activo)');
  });
});
