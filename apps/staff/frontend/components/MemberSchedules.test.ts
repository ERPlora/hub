// The schedules of one member (WORKBOOK «Pantallas · Horarios»; STAFF-F13–F15): the live
// `staff.schedule.list` of that member — Schedule, Default, From, To, Active and Hours (the week at a
// glance) —, «This member has no schedules yet.» when there is none. For whoever manages schedules: «+»
// («New»), a row or «Edit» («Edit · {name}»), «Activate / deactivate» at once, and «Delete» after
// «Delete the schedule "{name}"? …». A refused action is said above the table.
import { ConfirmDialog, DataTable, EmptyState } from '@erplora/ui/components';
import { describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import type { ScheduleOut } from '../operations';
import { EMPLOYEE, errorFrame, flush, type MountOptions, mountStaff, page, settle } from '../__tests__/mount-staff';
import MemberSchedules from './MemberSchedules.vue';
import ScheduleFormModal from './ScheduleFormModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const OP = 'staff.schedule.list';
const schedule = (id: string, over: Partial<ScheduleOut> = {}): ScheduleOut => ({
  id,
  member_id: 'm1',
  name: 'Regular schedule',
  is_default: true,
  effective_from: null,
  effective_until: null,
  is_active: true,
  days: [
    { weekday: 0, start_time: '09:00:00', end_time: '18:00:00', break_start: '13:00:00', break_end: '14:00:00' },
    { weekday: 2, start_time: '10:00:00', end_time: '16:00:00', break_start: null, break_end: null },
  ],
  ...over,
});
const ROWS = [schedule('s1'), schedule('s2', { name: 'Summer', is_default: false, effective_from: '2026-06-01', effective_until: '2026-09-15', is_active: false, days: [] })];

async function setup(options: MountOptions = {}) {
  const m = await mountStaff(MemberSchedules, { props: { memberId: 'm1' }, path: '/staff/schedules', ...options });
  await m.live();
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const rows = () => m.wrapper.findAll('[data-testid="staff-schedules-row"]');
  const cells = (i: number) => rows()[i].findAll('[role="cell"]').map((c) => c.text().trim());
  async function action(id: string, actionId: string) {
    await m.find(`staff-schedules-row-${id}-${actionId}`).trigger('click');
    await settle();
  }
  return { ...m, table, prop, rows, cells, action, show: (data: unknown) => m.result(OP, data) };
}

describe('MemberSchedules', () => {
  it('follows that member’s schedules (the server’s cap, 100), the default first', async () => {
    const s = await setup();
    expect(s.params(OP)).toEqual([{ member_id: 'm1', limit: 100 }]);
    expect(s.find('staff-schedules-loading').exists()).toBe(true);
    await s.show(page(ROWS, 2, 100));
    expect(s.table().props()).toMatchObject({ testid: 'staff-schedules', views: ['table', 'cards'] });
  });

  it('paints Schedule, Default, From, To, Active and Hours', async () => {
    const s = await setup();
    await s.show(page(ROWS, 2, 100));
    expect(s.prop<Array<{ key: string; label: string }>>('columns').map((c) => [c.key, c.label])).toEqual([
      ['name', 'Schedule'],
      ['is_default', 'Default'],
      ['effective_from', 'From'],
      ['effective_until', 'To'],
      ['is_active', 'Active'],
      ['hours', 'Hours'],
    ]);
    expect(s.cells(0).slice(0, 6)).toEqual(['Regular schedule', 'Yes', '—', '—', 'Yes', 'Mon 09:00–18:00 (13:00–14:00) · Wed 10:00–16:00']);
    expect(s.cells(1).slice(0, 6)).toEqual(['Summer', '—', '06/01/2026', '09/15/2026', 'No', '—']);
  });

  it('says «This member has no schedules yet.» when there is none', async () => {
    const s = await setup();
    await s.show(page([], 0, 100));
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('This member has no schedules yet.');
  });

  it('who manages schedules adds, edits, toggles and deletes', async () => {
    const s = await setup();
    await s.show(page(ROWS, 2, 100));
    expect([s.prop('addable'), s.prop('rowClickable')]).toEqual([true, true]);
    expect(s.prop<Array<{ id: string; icon: string }>>('actions').map((a) => [a.id, a.icon])).toEqual([
      ['edit', 'create-outline'],
      ['toggle', 'sync-outline'],
      ['delete', 'trash-outline'],
    ]);
    const modal = () => s.wrapper.findComponent(ScheduleFormModal);
    s.table().vm.$emit('add');
    await flush();
    expect([modal().props('open'), modal().props('schedule'), modal().props('memberId')]).toEqual([true, null, 'm1']);
    modal().vm.$emit('update:open', false);
    s.table().vm.$emit('rowClick', ROWS[1]);
    await flush();
    expect([modal().props('open'), modal().props('schedule')]).toEqual([true, ROWS[1]]);
  });

  it('«+» proposes «Default» only when the member has no default schedule yet', async () => {
    const s = await setup();
    await s.show(page(ROWS, 2, 100));
    s.table().vm.$emit('add');
    await settle();
    expect((s.inDoc('staff-schedule-form-is_default') as HTMLElement & { checked?: boolean }).checked).toBe(false);
    const without = await setup();
    await without.show(page([ROWS[1]], 1, 100));
    without.table().vm.$emit('add');
    await settle();
    expect((without.inDoc('staff-schedule-form-is_default') as HTMLElement & { checked?: boolean }).checked).toBe(true);
  });

  it('«Activate / deactivate» flips it at once with staff.schedule.set_active', async () => {
    const s = await setup();
    await s.show(page(ROWS, 2, 100));
    s.answer(200, {});
    await s.action('s2', 'toggle');
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/staff/schedules/set_active', query: {}, body: { id: 's2', is_active: true } }]);
  });

  it('«Delete» asks first with the name, then sends staff.schedule.delete; a refusal goes above the table', async () => {
    const s = await setup();
    await s.show(page(ROWS, 2, 100));
    s.answer(404, { error: { code: 'not_found', message: 'That schedule does not exist in this business.' } });
    await s.action('s2', 'delete');
    const dialog = s.wrapper.findComponent(ConfirmDialog);
    expect([dialog.props('open'), dialog.props('title'), dialog.props('message'), dialog.props('confirmLabel')]).toEqual([
      true,
      'Delete schedule',
      'Delete the schedule "Summer"? Its hours stop counting for availability.',
      'Delete',
    ]);
    dialog.vm.$emit('confirm');
    await settle();
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/staff/schedules/delete', query: {}, body: { id: 's2' } }]);
    expect(s.find('staff-schedules-error').text()).toContain('That schedule does not exist in this business.');
  });

  it('an employee only reads', async () => {
    const s = await setup({ session: EMPLOYEE });
    await s.show(page(ROWS, 2, 100));
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
    await s.show(page(ROWS, 2, 100));
    expect(s.cells(0).slice(1, 6)).toEqual(['Sí', '—', '—', 'Sí', 'Lun 09:00–18:00 (13:00–14:00) · Mié 10:00–16:00']);
  });
});
