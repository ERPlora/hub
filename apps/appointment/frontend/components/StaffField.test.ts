// The «Professional» field of the booking and series panels: a search of the active, bookable professionals who do
// every service chosen (Staff and Services), or the person's own record, fixed. It hands its name to its field, so
// the window tells that a professional chosen corrects a refusal of the professional (hub#888).
import { Combo } from '@erplora/ui/components';
import { describe, expect, it } from 'vitest';

import { mountAppointment, page, settle } from '../__tests__/mount-appointment';
import StaffField from './StaffField.vue';

type Field = HTMLElement & { name?: string; disabled?: boolean };

async function setup(props: Record<string, unknown> = {}) {
  const m = await mountAppointment(StaffField, { props: { modelValue: null, serviceIds: ['cut'], testid: 'appointment-form', ...props } });
  m.answerBy({
    '/api/staff/members': [200, page([{ id: 's1', full_name: 'Ana López' }, { id: 's2', full_name: 'Bea Ruiz' }])],
    '/api/service/assignments/eligible': [200, page([{ member_id: 's2' }])],
  });
  const combo = () => m.wrapper.findComponent(Combo);
  const field = () => m.wrapper.get('ion-input[data-testid="appointment-form-staff"]').element as Field;
  return { ...m, combo, field };
}

describe('StaffField', () => {
  it('is «Professional» and offers the active, bookable professionals who do the services chosen', async () => {
    const s = await setup();
    expect(s.combo().props('label')).toBe('Professional');
    const offered = await (s.combo().props('search') as (q: string) => Promise<{ id: string; label: string }[]>)('');
    expect(offered).toEqual([{ id: 's2', label: 'Bea Ruiz' }]);
    expect(s.sent().find((call) => call.path === '/api/staff/members')?.query).toMatchObject({ status: 'active', is_bookable: 'true' });
    expect(s.sent().find((call) => call.path === '/api/service/assignments/eligible')?.query).toMatchObject({ service_id: 'cut' });
  });

  it('a choice is its model; it can be cleared', async () => {
    const s = await setup();
    s.combo().vm.$emit('update:modelValue', { id: 's2', label: 'Bea Ruiz' });
    await settle();
    expect(s.wrapper.emitted('update:modelValue')?.at(-1)).toEqual([{ id: 's2', label: 'Bea Ruiz' }]);
    expect(s.combo().props('clearable')).toBe(true);
  });

  it('hands its name and its refusal to its field', async () => {
    const s = await setup({ name: 'staff', errorText: 'Check this field.' });
    await settle();
    expect(s.field().name).toBe('staff');
    expect(s.combo().props('errorText')).toBe('Check this field.');
  });

  it('the own record is fixed: neither cleared nor changed; `disabled` stops it too', async () => {
    const own = await setup({ modelValue: { id: 's1', label: 'Ana López' }, own: true });
    expect([own.combo().props('disabled'), own.combo().props('clearable')]).toEqual([true, false]);
    const charged = await setup({ disabled: true });
    expect([charged.combo().props('disabled'), charged.combo().props('clearable')]).toEqual([true, true]);
  });
});
