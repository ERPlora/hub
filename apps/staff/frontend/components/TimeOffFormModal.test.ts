// STAFF-F17 «Registrar una ausencia» and STAFF-F24 «Pedir mi propia ausencia»: «+» in Time Off opens the
// old form — Member (only for whoever manages time off: they register anyone's, searched on the server
// in a Combo; an employee asks for their own and is not asked who), Type (Vacation to begin with), From, To, Full day (on) and, when it
// is off, From (time) and To (time), and Reason. Registering sends `staff.time_off.create`; asking,
// `staff.time_off.request`. The server judges: an overlap (409) is said on top, a 422 under its field,
// and the dialog keeps what was typed.
import { Combo, type ComboOption } from '@erplora/ui/components';
import { describe, expect, it, vi } from 'vitest';

import { click, EMPLOYEE, ionChecked, ionValue, mountStaff, type MountOptions, page, settle } from '../__tests__/mount-staff';
import TimeOffFormModal from './TimeOffFormModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

type Control = HTMLElement & { label?: string; value?: unknown; checked?: boolean; type?: string; errorText?: string; disabled?: boolean };

const MEMBERS = page([
  { id: 'm1', full_name: 'Ana López' },
  { id: 'm2', full_name: 'Bea Ruiz' },
]);

async function setup(mode: 'create' | 'request', options: MountOptions = {}) {
  const m = await mountStaff(TimeOffFormModal, {
    props: { open: false, mode },
    path: '/staff/time-off',
    answers: { '/api/staff/members': [200, MEMBERS], '/api/staff/time_off': [201, {}], '/api/staff/time_off/request': [201, {}] },
    ...options,
  });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await m.wrapper.setProps({ open: true });
  await settle();
  const field = (name: string) => m.inDoc(`staff-time-off-form-${name}`) as Control;
  const save = () => m.inDoc('staff-time-off-form-submit') as Control;
  const member = () => m.wrapper.findAllComponents(Combo).find((c) => c.props('testid') === 'staff-time-off-form-member_id');
  /** What the Member Combo offers for `query`, as [id, label]. */
  async function members(query = '') {
    const search = member()?.props('search') as ((q: string) => Promise<ComboOption[]>) | undefined;
    if (!search) throw new Error('Member is not a Combo with a server search');
    return (await search(query)).map((o) => [o.id, o.label]);
  }
  async function chooseMember(id: string) {
    const search = member()?.props('search') as ((q: string) => Promise<ComboOption[]>) | undefined;
    if (!search) throw new Error('Member is not a Combo with a server search');
    const option = (await search('')).find((o) => o.id === id);
    if (!option) throw new Error(`Member offers no ${id}`);
    member()!.vm.$emit('update:modelValue', option);
    await settle();
  }
  async function dates(from: string, to: string) {
    await ionValue(field('start_date'), from, 'ionInput');
    await ionValue(field('end_date'), to, 'ionInput');
  }
  const posts = () => m.sent().filter((c) => c.method === 'POST');
  return { ...m, field, save, member, members, chooseMember, dates, posts };
}

describe('TimeOffFormModal: register anyone’s (STAFF-F17)', () => {
  it('is «New» with Member, Type (Vacation), From, To and Full day on; no hours while full day', async () => {
    const s = await setup('create');
    expect(s.inDoc('staff-time-off-form')?.getAttribute('aria-label')).toBe('New');
    expect([s.field('member_id').label, s.field('leave_type').label, s.field('leave_type').value, s.field('start_date').type, s.field('end_date').label]).toEqual([
      'Member',
      'Type',
      'vacation',
      'date',
      'To',
    ]);
    expect([...s.field('leave_type').querySelectorAll('ion-select-option')].map((o) => o.textContent?.trim())).toEqual([
      'Vacation',
      'Sick leave',
      'Personal',
      'Training',
      'Other',
    ]);
    expect(s.field('is_full_day').checked).toBe(true);
    expect(s.field('start_time')).toBeNull();
    expect(s.save().disabled).toBe(true);
  });

  it('Member searches the members by name on the server, with no «none» choice and no Clear button', async () => {
    const s = await setup('create');
    expect(s.field('member_id').value).toBe('');
    expect(await s.members()).toEqual([
      ['m1', 'Ana López'],
      ['m2', 'Bea Ruiz'],
    ]);
    expect(s.sent()).toContainEqual({ method: 'GET', path: '/api/staff/members', query: { sort: 'name', limit: '100' }, body: undefined });
    await s.members('bea');
    expect(s.sent()).toContainEqual({ method: 'GET', path: '/api/staff/members', query: { sort: 'name', limit: '100', search: 'bea' }, body: undefined });
    expect([s.member()?.props('clearable'), s.member()?.props('emptyLabel')]).toEqual([false, 'No results']);
  });

  it('sends staff.time_off.create for the member chosen, then closes', async () => {
    const s = await setup('create');
    await s.chooseMember('m2');
    expect(s.field('member_id').value).toBe('Bea Ruiz');
    await s.dates('2026-11-02', '2026-11-06');
    await ionValue(s.field('reason'), 'Family trip', 'ionInput');
    await click(s.save());
    expect(s.posts()).toEqual([
      {
        method: 'POST',
        path: '/api/staff/time_off',
        query: {},
        body: { member_id: 'm2', leave_type: 'vacation', start_date: '2026-11-02', end_date: '2026-11-06', is_full_day: true, reason: 'Family trip' },
      },
    ]);
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it('part of a day asks for the hours and sends them', async () => {
    const s = await setup('create');
    await s.chooseMember('m1');
    await s.dates('2026-11-02', '2026-11-02');
    await ionChecked(s.field('is_full_day'), false);
    expect([s.field('start_time').label, s.field('start_time').type, s.field('end_time').label]).toEqual(['From (time)', 'time', 'To (time)']);
    await ionValue(s.field('start_time'), '09:00', 'ionInput');
    await ionValue(s.field('end_time'), '13:00', 'ionInput');
    await ionValue(s.field('leave_type'), 'personal');
    await click(s.save());
    expect(s.posts()[0].body).toEqual({
      member_id: 'm1',
      leave_type: 'personal',
      start_date: '2026-11-02',
      end_date: '2026-11-02',
      is_full_day: false,
      start_time: '09:00',
      end_time: '13:00',
      reason: '',
    });
  });

  it('an overlap (409) is said on top; a 422 under its field; what was typed stays', async () => {
    const message = 'That member already has pending or approved time off on those dates.';
    const s = await setup('create', { answers: { '/api/staff/members': [200, MEMBERS], '/api/staff/time_off': [409, { error: { code: 'staff.overlapping_time_off', message } }] } });
    await s.chooseMember('m1');
    await s.dates('2026-11-02', '2026-11-03');
    await click(s.save());
    expect(s.inDoc('staff-time-off-form-error')?.textContent).toContain(message);
    expect(s.field('start_date').value).toBe('2026-11-02');
    s.answerBy({ '/api/staff/time_off': [422, { error: { code: 'invalid_payload', message: 'Check the fields.', fields: { end_date: 'The end date cannot be before the start date.' } } }] });
    await click(s.save());
    expect(s.field('end_date').errorText).toBe('The end date cannot be before the start date.');
    s.answerBy({ '/api/staff/time_off': [422, { error: { code: 'invalid_payload', message: 'Check the fields.', fields: { member_id: 'That member is not active.' } } }] });
    await click(s.save());
    expect(s.member()?.props('errorText')).toBe('That member is not active.');
    expect(s.field('member_id').value).toBe('Ana López');
  });
});

describe('TimeOffFormModal: ask for one’s own (STAFF-F24)', () => {
  it('is «Request time off», does not ask who, and sends staff.time_off.request', async () => {
    const s = await setup('request', { session: EMPLOYEE });
    expect(s.inDoc('staff-time-off-form')?.getAttribute('aria-label')).toBe('Request time off');
    expect(s.field('member_id')).toBeNull();
    await s.dates('2026-12-21', '2026-12-24');
    await click(s.save());
    expect(s.posts()).toEqual([
      {
        method: 'POST',
        path: '/api/staff/time_off/request',
        query: {},
        body: { leave_type: 'vacation', start_date: '2026-12-21', end_date: '2026-12-24', is_full_day: true, reason: '' },
      },
    ]);
  });

  it('without a linked record the server’s words say why (409)', async () => {
    const message = 'Your user is not linked to any staff member: ask a manager to link it.';
    const s = await setup('request', {
      session: EMPLOYEE,
      answers: { '/api/staff/time_off/request': [409, { error: { code: 'staff.no_member_record', message } }] },
    });
    await s.dates('2026-12-21', '2026-12-24');
    await click(s.save());
    expect(s.inDoc('staff-time-off-form-error')?.textContent).toContain(message);
  });

  it('speaks Spanish', async () => {
    const s = await setup('request', { session: EMPLOYEE, locale: 'es' });
    expect(s.inDoc('staff-time-off-form')?.getAttribute('aria-label')).toBe('Pedir ausencia');
    expect([s.field('start_date').label, s.field('is_full_day').textContent?.trim(), s.field('reason').label]).toEqual(['Desde', 'Día completo', 'Motivo']);
  });
});
