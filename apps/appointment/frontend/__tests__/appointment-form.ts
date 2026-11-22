import { Combo, DateField, TimeField } from '@erplora/ui/components';

import CustomerSearch from '../../../customer/frontend/components/CustomerSearch.vue';
import type { AppointmentOut } from '../operations';
import { business, mountAppointment, page, settle } from './mount-appointment';
import AppointmentFormModal from '../components/AppointmentFormModal.vue';

export type Control = HTMLElement & { label?: string; value?: unknown; errorText?: string; disabled?: boolean; readonly?: boolean };

export const BOOKED: AppointmentOut = {
  id: 'a1',
  number: 'APT-20261019-0001',
  customer_id: 'c9',
  customer_name: 'Lucía Pérez',
  staff_id: 's1',
  staff_name: 'Ana López',
  start: '2026-10-19T10:00:00+02:00',
  end: '2026-10-19T10:30:00+02:00',
  duration_minutes: 30,
  status: 'confirmed',
  source: 'counter',
  services: [{ service_id: 'cut', name: 'Haircut', price: 2000, duration_minutes: 30 }],
  service_names: 'Haircut',
  total: 2000,
  booked_by_customer: false,
  sale_id: null,
  order_id: null,
  recurring_id: null,
  occurrence_date: null,
  customer_phone: '+34600111222',
  customer_email: '',
  notes: '',
  internal_notes: '',
  cancelled_at: null,
  cancellation_reason: '',
  cancelled_by_customer: false,
  charged_at: null,
  created_at: '2026-10-14T10:00:00+02:00',
  updated_at: '2026-10-14T10:00:00+02:00',
  start_date_label: 'Monday, October 19, 2026',
  start_time_label: '10:00',
  label: 'Lucía · Monday · 10:00 · Ana',
};

export const SERVICES = page([
  { id: 'cut', name: 'Haircut', price: 2000, duration_minutes: 30, is_bookable: true },
  { id: 'colour', name: 'Colour', price: 4500, duration_minutes: 60, is_bookable: true },
]);

/** What the panel reads when it opens: the services for sale, the professionals and who does what. */
export const READS: Record<string, [number, unknown]> = {
  '/api/service/services/for_sale': [200, SERVICES],
  '/api/staff/members': [200, page([{ id: 's1', full_name: 'Ana López' }, { id: 's2', full_name: 'Bea Ruiz' }])],
  '/api/service/assignments/eligible': [200, page([])],
};

export async function setup(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountAppointment(AppointmentFormModal, {
    props: { open: false, appointment: null, businessNow: '2026-10-14T12:00', ...props },
    locale,
  });
  m.answerBy(READS);
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await m.wrapper.setProps({ open: true });
  await settle();
  const field = (name: string) => m.inDoc(`appointment-form-${name}`) as Control;
  const submit = () => m.inDoc('appointment-form-submit') as Control;
  const combos = () => m.wrapper.findAllComponents(Combo);
  const servicePicker = () => combos().find((c) => c.props('testid') === 'appointment-form-service-add')!;
  const staffPicker = () => combos().find((c) => c.props('testid') === 'appointment-form-staff')!;
  async function addService(id: string, label: string) {
    await (servicePicker().props('search') as (q: string) => Promise<unknown>)('');
    servicePicker().vm.$emit('update:modelValue', { id, label });
    await settle();
  }
  async function pickStaff(id: string, label: string) {
    staffPicker().vm.$emit('update:modelValue', { id, label });
    await settle();
  }
  const when = (name: 'day' | 'time') => (name === 'day' ? m.wrapper.getComponent(DateField) : m.wrapper.getComponent(TimeField)).vm;
  const kept = (name: 'day' | 'time') => when(name).$props.modelValue;
  const pick = async (name: 'day' | 'time', value: string) => { when(name).$emit('update:modelValue', value); await settle(); };
  async function pickCustomer() {
    m.wrapper.findComponent(CustomerSearch).vm.$emit('update:modelValue', {
      customer_id: 'c1',
      customer_name: 'Lucía Pérez',
      customer_tax_id: '',
      customer_address: '',
      customer_country: '',
    });
    await settle();
  }
  /** The business answers (`base.business.get`): the panel's money is its currency (BASE-F50). */
  async function businessIn(fields = {}) {
    await m.live();
    await m.result('base.business.get', business(fields));
  }
  return { ...m, field, submit, servicePicker, staffPicker, addService, pickStaff, kept, pick, pickCustomer, businessIn };
}

/** The services, the professional, the day and the time of a new appointment; the customer is chosen apart. */
export async function fillChoices(s: Awaited<ReturnType<typeof setup>>) {
  await s.addService('cut', 'Haircut');
  await s.addService('colour', 'Colour');
  await s.pickStaff('s1', 'Ana López');
  await s.pick('day', '2026-10-19');
  await s.pick('time', '10:00');
}

export async function fillNew(s: Awaited<ReturnType<typeof setup>>) {
  await s.pickCustomer();
  await fillChoices(s);
}
