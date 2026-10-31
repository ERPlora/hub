// STAFF-F08 «Ver mi propia ficha»: whoever has a record linked to their account opens «My record»
// from Staff and reads it — name, role, email, phone, employee ID, status, bookable, hire date and,
// theirs only, their hourly rate and commission (never the HR notes). Read only: «Close».
import { describe, expect, it, vi } from 'vitest';

import type { MemberMineOut } from '../operations';
import { BUSINESS, business, click, JAPANESE, mountStaff, POLISH, settle } from '../__tests__/mount-staff';
import MyRecordModal from './MyRecordModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const MINE: MemberMineOut = {
  id: 'm2',
  first_name: 'Bea',
  last_name: 'Ruiz',
  full_name: 'Bea Ruiz',
  email: 'bea@example.com',
  phone: '',
  employee_number: 'E-9',
  role_id: 'r1',
  role_name: 'Stylist',
  user_id: '01a16000-0000-7000-8000-0000000000b2',
  status: 'active',
  is_bookable: true,
  hire_date: '2025-03-04',
  color: '',
  booking_buffer: 0,
  specialties: '',
  bio: '',
  created_at: '2026-01-01T10:00:00Z',
  updated_at: '2026-01-01T10:00:00Z',
  hourly_rate: 1250,
  commission_rate: '10.00',
};

/** The modal open on `MINE`; the business answers (in Spain unless `where` says another; `null`: not yet). */
async function setup(locale: 'en' | 'es' = 'en', where: Parameters<typeof business>[0] | null = {}, record: MemberMineOut = MINE) {
  const m = await mountStaff(MyRecordModal, { props: { open: false, record }, locale });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await m.wrapper.setProps({ open: true });
  await settle();
  await m.live();
  if (where) await m.result(BUSINESS, business(where));
  await settle();
  const fields = () =>
    [...(m.inDoc('staff-my-record-fields') as HTMLElement).querySelectorAll('[data-testid="staff-my-record-field"]')].map((el) => [
      el.querySelector('dt')?.textContent?.trim(),
      el.querySelector('dd')?.textContent?.trim(),
    ]);
  return { ...m, fields };
}

describe('MyRecordModal (STAFF-F08)', () => {
  it('reads the person’s own record, with their own pay', async () => {
    const s = await setup();
    expect(s.inDoc('staff-my-record')?.getAttribute('aria-label')).toBe('My record');
    expect(s.fields()).toEqual([
      ['Name', 'Bea Ruiz'],
      ['Role', 'Stylist'],
      ['Email', 'bea@example.com'],
      ['Phone', '—'],
      ['Employee ID', 'E-9'],
      ['Status', 'Active'],
      ['Bookable', 'Yes'],
      ['Hire date', '03/04/2025'],
      ['Hourly rate', '€12.50'],
      ['Commission (%)', '10 %'],
    ]);
  });

  it('is read only: one «Close», no Save', async () => {
    const s = await setup();
    expect(s.inDoc('staff-my-record-submit')).toBeNull();
    await click(s.inDoc('staff-my-record-done'));
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it('speaks Spanish', async () => {
    const s = await setup('es');
    expect(s.inDoc('staff-my-record')?.getAttribute('aria-label')).toBe('Mi ficha');
    expect(s.fields().at(-2)).toEqual(['Tarifa por hora', '12,50 €']);
    expect(s.inDoc('staff-my-record-done')?.textContent?.trim()).toBe('Cerrar');
  });
});

describe('MyRecordModal: the business\'s currency (staff-business-currency)', () => {
  const rate = (s: Awaited<ReturnType<typeof setup>>) => (s.fields().at(-2)?.[1] ?? '').replace(/\s/g, ' ');

  it('a business in Poland reads its own rate in złoty', async () => {
    expect(rate(await setup('es', POLISH))).toBe('12,50 zł');
  });

  it('a business in Japan reads whole yen', async () => {
    expect(rate(await setup('en', JAPANESE, { ...MINE, hourly_rate: 1500 }))).toBe('¥1,500');
  });

  it('until the business answers, a figure without a symbol, never euros', async () => {
    expect(rate(await setup('en', null))).toBe('12.50');
  });
});
