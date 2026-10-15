// APPOINTMENT-F12, F14: «New repeating appointment» asks for Customer, Services, Professional, Repeats,
// Day of the week (weekly and fortnightly only), Starts on, Time, Min., «Ends on (optional)» and «Number of
// appointments (optional)», and «Create repeating appointment» creates it and books its window. «Edit
// repeating appointment» applies from a date on, says how many booked appointments it reaches and how
// many charged ones it leaves alone, and «Save from this occurrence on» sends only what changed.
import { Combo } from '@erplora/ui/components';
import { describe, expect, it, vi } from 'vitest';

import CustomerSearch from '../../../customer/frontend/components/CustomerSearch.vue';
import type { RecurringOut } from '../operations';
import { click, ionValue, mountAppointment, page, settle } from '../__tests__/mount-appointment';
import SeriesFormModal from './SeriesFormModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

type Control = HTMLElement & { label?: string; value?: unknown; disabled?: boolean };

const SERIES: RecurringOut = {
  id: 'r1',
  customer_id: 'c1',
  customer_name: 'Lucía Pérez',
  staff_id: 's1',
  staff_name: 'Ana López',
  services: [{ service_id: 'cut', name: 'Haircut' }],
  service_names: 'Haircut',
  frequency: 'weekly',
  day_of_week: 0,
  time: '10:00:00',
  duration_minutes: 30,
  start_date: '2026-10-19',
  end_date: null,
  max_occurrences: null,
  is_active: true,
  split_from_id: null,
  created_at: '2026-10-14T10:00:00+02:00',
};
const OUTCOME = { recurring: SERIES, booked: 13, already_booked: 0, skipped: [], next_from: null, to: '2027-01-12', upcoming_date: null };

async function setup(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountAppointment(SeriesFormModal, {
    props: { open: false, series: null, businessToday: '2026-10-14', ...props },
    locale,
  });
  m.answerBy({
    '/api/service/services/for_sale': [200, page([{ id: 'cut', name: 'Haircut', price: 2000, duration_minutes: 30, is_bookable: true }])],
    '/api/staff/members': [200, page([{ id: 's1', full_name: 'Ana López' }])],
    '/api/service/assignments/eligible': [200, page([])],
  });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await m.wrapper.setProps({ open: true });
  await settle();
  const field = (name: string) => m.inDoc(`series-form-${name}`) as Control;
  const submit = () => m.inDoc('series-form-submit') as Control;
  const combo = (testid: string) => m.wrapper.findAllComponents(Combo).find((c) => c.props('testid') === testid)!;
  return { ...m, field, submit, combo };
}

describe('SeriesFormModal: New repeating appointment', () => {
  it('proposes the professional’s own minutes for the services (Services · «Who does it»)', async () => {
    const s = await setup();
    s.answerBy({
      '/api/service/services/for_sale': [200, page([{ id: 'cut', name: 'Haircut', price: 2000, duration_minutes: 30, is_bookable: true }])],
      '/api/staff/members': [200, page([{ id: 's1', full_name: 'Ana López' }])],
      '/api/service/assignments/eligible': [200, page([{ member_id: 's1', full_name: 'Ana López', color: '', booking_buffer: 0, custom_duration: 45, custom_price: null, is_primary: true, duration: 45, price: 2000 }])],
    });
    await (s.combo('series-form-service-add').props('search') as (q: string) => Promise<unknown>)('');
    s.combo('series-form-service-add').vm.$emit('update:modelValue', { id: 'cut', label: 'Haircut' });
    s.combo('series-form-staff').vm.$emit('update:modelValue', { id: 's1', label: 'Ana López' });
    await settle();
    expect(s.field('minutes').value).toBe('45');
  });

  it('asks the old fields and creates the series, which books its window', async () => {
    const s = await setup();
    expect(s.inDoc('series-form')?.getAttribute('aria-label')).toBe('New repeating appointment');
    expect([s.field('frequency').label, s.field('weekday').label, s.field('start_date').label]).toEqual([
      'Repeats',
      'Day of the week',
      'Starts on',
    ]);
    expect([s.field('end_date').label, s.field('max_occurrences').label]).toEqual([
      'Ends on (optional)',
      'Number of appointments (optional)',
    ]);
    s.wrapper.findComponent(CustomerSearch).vm.$emit('update:modelValue', { customer_id: 'c1', customer_name: 'Lucía Pérez', customer_tax_id: '', customer_address: '', customer_country: '' });
    await (s.combo('series-form-service-add').props('search') as (q: string) => Promise<unknown>)('');
    s.combo('series-form-service-add').vm.$emit('update:modelValue', { id: 'cut', label: 'Haircut' });
    s.combo('series-form-staff').vm.$emit('update:modelValue', { id: 's1', label: 'Ana López' });
    await settle();
    await ionValue(s.field('weekday'), 2);
    await ionValue(s.field('start_date'), '2026-10-19', 'ionInput');
    await ionValue(s.field('time'), '11:00', 'ionInput');
    await ionValue(s.field('max_occurrences'), '6', 'ionInput');
    expect(s.field('minutes').value).toBe('30');
    s.answer(201, OUTCOME);
    await click(s.submit());
    expect(s.sent().filter((call) => call.method === 'POST')).toEqual([
      {
        method: 'POST',
        path: '/api/appointment/recurring',
        query: {},
        body: {
          customer_id: 'c1',
          services: [{ service_id: 'cut' }],
          staff_id: 's1',
          frequency: 'weekly',
          day_of_week: 2,
          start_date: '2026-10-19',
          time: '11:00',
          max_occurrences: 6,
        },
      },
    ]);
    expect(s.wrapper.emitted('outcome')?.[0]).toEqual([OUTCOME]);
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it('has no day of the week for a daily or monthly series', async () => {
    const s = await setup();
    await ionValue(s.field('frequency'), 'monthly');
    expect(s.field('weekday')).toBeNull();
  });
});

describe('SeriesFormModal: Edit repeating appointment', () => {
  it('applies from a date, says what it reaches, and sends only what changed', async () => {
    const s = await setup({ series: SERIES, fromDate: '2026-11-02' });
    expect(s.inDoc('series-form')?.getAttribute('aria-label')).toBe('Edit repeating appointment');
    expect(s.field('from_date').value).toBe('2026-11-02');
    expect(s.params('appointment.recurring.get')).toEqual([{ id: 'r1', from_date: '2026-11-02' }]);
    await s.live();
    await s.result('appointment.recurring.get', { ...SERIES, next_date: '2026-10-19', upcoming: 5, charged: 1 });
    expect(s.find('series-form-scope').text()).toContain('it reaches 5 booked appointments; 1 already charged will not be touched');
    expect(s.submit().textContent).toContain('Save from this occurrence on');
    await ionValue(s.field('time'), '12:30', 'ionInput');
    s.answer(200, { recurring: SERIES, moved: 4, cancelled: 0, locked: 1, skipped: [], booked: 0 });
    await click(s.submit());
    expect(s.sent().filter((call) => call.method === 'POST')).toEqual([
      { method: 'POST', path: '/api/appointment/recurring/update', query: {}, body: { id: 'r1', from_date: '2026-11-02', time: '12:30' } },
    ]);
    expect(s.wrapper.emitted('updated')?.[0]?.[0]).toMatchObject({ moved: 4, locked: 1 });
  });

  it('speaks Spanish', async () => {
    const s = await setup({ series: SERIES }, 'es');
    expect(s.inDoc('series-form')?.getAttribute('aria-label')).toBe('Editar cita periódica');
    expect(s.field('from_date').label).toBe('Desde');
  });
});
