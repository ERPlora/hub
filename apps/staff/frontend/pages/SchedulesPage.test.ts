// Staff → Schedules (WORKBOOK «Pantallas · Horarios»): the Member picker (searched on the server: a
// business may have more than 100) above the schedules of the chosen member — the first one by name to
// begin with. With no member at all there is nobody to schedule: only «No staff members yet» and «Add
// staff member», which opens Staff (the old staff#98).
import { AppPage } from '@erplora/ui/shell';
import { describe, expect, it, vi } from 'vitest';

import { click, flush, type MountOptions, mountStaff, page, settle } from '../__tests__/mount-staff';
import MemberSchedules from '../components/MemberSchedules.vue';
import SchedulesPage from './SchedulesPage.vue';
import { listFillProblems } from '../../../../frontend/testing/list-fill';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const FIRST = { rows: [{ id: 'm1', full_name: 'Ana López' }], total: 2, limit: 1, offset: 0 };

async function setup(options: MountOptions = {}) {
  const m = await mountStaff(SchedulesPage, {
    path: '/staff/schedules',
    answers: { '/api/staff/members': [200, page([{ id: 'm1', full_name: 'Ana López' }, { id: 'm2', full_name: 'Bea Ruiz' }])] },
    ...options,
  });
  await m.live();
  return m;
}

describe('SchedulesPage', () => {
  it('follows the first member by name, to know whether there is anyone and whom to show first', async () => {
    const s = await setup();
    expect(s.params('staff.member.list')).toEqual([{ sort: 'name', limit: 1 }]);
    expect(s.find('staff-schedules-loading-members').exists()).toBe(true);
    await s.result('staff.member.list', FIRST);
    const picker = s.find('staff-schedules-member').element as HTMLElement & { value?: unknown; label?: string };
    expect([picker.label, picker.value]).toEqual(['Member', 'Ana López']);
    expect(s.wrapper.findComponent(MemberSchedules).props('memberId')).toBe('m1');
    expect(s.wrapper.findComponent(AppPage).props('title')).toBe('Staff');
  });

  it('picking another member shows theirs', async () => {
    const s = await setup();
    await s.result('staff.member.list', FIRST);
    await click(s.find('staff-schedules-member').element);
    await settle();
    const root = (s.wrapper.element.parentElement ?? s.wrapper.element) as Element;
    await click(root.querySelector('[data-testid="staff-schedules-member-option"][data-value="m2"]'));
    expect(s.wrapper.findComponent(MemberSchedules).props('memberId')).toBe('m2');
    expect((s.find('staff-schedules-member').element as HTMLElement & { value?: unknown }).value).toBe('Bea Ruiz');
  });

  it('with no member at all: «No staff members yet» and «Add staff member», which opens Staff', async () => {
    const s = await setup();
    await s.result('staff.member.list', { rows: [], total: 0, limit: 1, offset: 0 });
    expect(s.find('staff-schedules-no-members').text()).toContain('No staff members yet');
    expect(s.find('staff-schedules-member').exists()).toBe(false);
    expect(s.wrapper.findComponent(MemberSchedules).exists()).toBe(false);
    await click(s.find('staff-schedules-add-member').element);
    await flush();
    expect(s.router.currentRoute.value.path).toBe('/staff/members');
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.result('staff.member.list', { rows: [], total: 0, limit: 1, offset: 0 });
    expect(s.find('staff-schedules-no-members').text()).toContain('Aún no hay miembros del staff');
    expect(s.find('staff-schedules-add-member').text()).toContain('Dar de alta un miembro');
  });
});

describe('SchedulesPage: the list fills the page (FIX-DATATABLE-HUB)', () => {
  it('the chosen member\'s schedules: AppPage `fill` and its DataTable `fill`, only stacks between them', async () => {
    const s = await setup();
    await s.result('staff.member.list', FIRST);
    expect(s.wrapper.findComponent(MemberSchedules).exists()).toBe(true);
    expect(listFillProblems(s.wrapper)).toEqual([]);
  });
});
