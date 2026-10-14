// The record form of a staff member (STAFF-F01, F02, F03, F21): one form for «New» and «Edit · {name}».
// What the person types becomes the operation's input here, so the pages hold no rule:
//   - New sends every field (empty optional texts as ''), none for role/user/hire date when unset,
//     and the pay only when the person may see it (otherwise the server refuses it);
//   - Edit sends ONLY what changed (STAFF-F02 «solo cambia lo enviado»), `null` to clear the role,
//     the Hub user or the hire date, and the pay only when it may see it and it changed;
//   - money is typed in euros and travels in whole cents; the commission travels as typed.
import { describe, expect, it } from 'vitest';

import type { CompensationOut, MemberDetailOut } from '../operations';
import { blankMemberForm, createPayload, formFromRecord, patchPayload } from './memberForm';

const DETAIL: MemberDetailOut = {
  id: 'm1',
  first_name: 'Ana',
  last_name: 'López',
  full_name: 'Ana López',
  email: 'ana@example.com',
  phone: '600 000 000',
  employee_number: 'E-7',
  role_id: 'r1',
  role_name: 'Stylist',
  user_id: 4,
  status: 'active',
  is_bookable: true,
  hire_date: '2024-02-01',
  color: '#AA3300',
  booking_buffer: 10,
  specialties: 'Colour',
  bio: 'Ten years.',
  created_at: '2026-01-01T10:00:00Z',
  updated_at: '2026-01-01T10:00:00Z',
};

const PAY: CompensationOut = {
  id: 'm1',
  user_id: 4,
  full_name: 'Ana López',
  role_id: 'r1',
  role_name: 'Stylist',
  status: 'active',
  hourly_rate: 1250,
  commission_rate: '12.50',
  notes: 'Prefers mornings.',
};

describe('blankMemberForm', () => {
  it('is a new person: nothing typed, bookable, active, no role nor Hub user', () => {
    expect(blankMemberForm()).toEqual({
      first_name: '',
      last_name: '',
      email: '',
      phone: '',
      employee_number: '',
      role_id: '',
      user_id: '',
      status: 'active',
      is_bookable: true,
      booking_buffer: '0',
      hire_date: '',
      color: '',
      specialties: '',
      bio: '',
      hourly_rate: '',
      commission_rate: '',
      notes: '',
    });
  });
});

describe('createPayload (New)', () => {
  it('sends the typed record, trimmed, with role and Hub user when chosen', () => {
    const form = { ...blankMemberForm(), first_name: ' Ana ', last_name: 'López', email: 'ana@example.com ', role_id: 'r1', user_id: '4', hire_date: '2024-02-01', booking_buffer: '15', color: '#aa3300' };
    expect(createPayload(form, { pay: false })).toEqual({
      first_name: 'Ana',
      last_name: 'López',
      email: 'ana@example.com',
      phone: '',
      employee_number: '',
      role_id: 'r1',
      user_id: 4,
      hire_date: '2024-02-01',
      is_bookable: true,
      booking_buffer: 15,
      color: '#aa3300',
      specialties: '',
      bio: '',
    });
  });

  it('leaves out role, Hub user and hire date when not chosen', () => {
    const payload = createPayload({ ...blankMemberForm(), first_name: 'A', last_name: 'B' }, { pay: false });
    expect(payload).not.toHaveProperty('role_id');
    expect(payload).not.toHaveProperty('user_id');
    expect(payload).not.toHaveProperty('hire_date');
  });

  it('sends the pay in cents only to whoever may see it', () => {
    const form = { ...blankMemberForm(), first_name: 'A', last_name: 'B', hourly_rate: '12,50', commission_rate: '7.5', notes: 'x' };
    expect(createPayload(form, { pay: true })).toMatchObject({ hourly_rate: 1250, commission_rate: '7.5', notes: 'x' });
    const without = createPayload(form, { pay: false });
    for (const key of ['hourly_rate', 'commission_rate', 'notes']) expect(without).not.toHaveProperty(key);
  });

  it('an empty commission is 0; a rate that is not a figure goes as typed for the server to refuse under it', () => {
    const form = { ...blankMemberForm(), first_name: 'A', last_name: 'B', hourly_rate: 'doce' };
    expect(createPayload(form, { pay: true })).toMatchObject({ hourly_rate: 'doce', commission_rate: '0' });
  });
});

describe('formFromRecord (Edit · {name})', () => {
  it('fills the form with the record and, when given, its pay in the reader’s decimal mark', () => {
    expect(formFromRecord(DETAIL, PAY, 'es')).toEqual({
      first_name: 'Ana',
      last_name: 'López',
      email: 'ana@example.com',
      phone: '600 000 000',
      employee_number: 'E-7',
      role_id: 'r1',
      user_id: '4',
      status: 'active',
      is_bookable: true,
      booking_buffer: '10',
      hire_date: '2024-02-01',
      color: '#AA3300',
      specialties: 'Colour',
      bio: 'Ten years.',
      hourly_rate: '12,50',
      commission_rate: '12.5',
      notes: 'Prefers mornings.',
    });
  });

  it('without the pay, its fields stay empty', () => {
    expect(formFromRecord({ ...DETAIL, role_id: null, user_id: null, hire_date: null }, null, 'en')).toMatchObject({
      role_id: '',
      user_id: '',
      hire_date: '',
      hourly_rate: '',
      commission_rate: '',
      notes: '',
    });
  });
});

describe('patchPayload (Edit sends only what changed)', () => {
  const original = formFromRecord(DETAIL, PAY, 'en');

  it('nothing changed: only the id', () => {
    expect(patchPayload('m1', original, original, { pay: true })).toEqual({ id: 'm1' });
  });

  it('a changed text, status or toggle goes alone, trimmed', () => {
    const form = { ...original, phone: ' 611 ', status: 'on_leave' as const, is_bookable: false };
    expect(patchPayload('m1', original, form, { pay: true })).toEqual({ id: 'm1', phone: '611', status: 'on_leave', is_bookable: false });
  });

  it('«No role», «No Hub access» and an emptied hire date clear them with null', () => {
    const form = { ...original, role_id: '', user_id: '', hire_date: '' };
    expect(patchPayload('m1', original, form, { pay: false })).toEqual({ id: 'm1', role_id: null, user_id: null, hire_date: null });
  });

  it('a new Hub user goes as a number', () => {
    expect(patchPayload('m1', original, { ...original, user_id: '9' }, { pay: false })).toEqual({ id: 'm1', user_id: 9 });
  });

  it('the pay goes only when it may be seen and it changed; the same figure written another way is no change', () => {
    const form = { ...original, hourly_rate: '12.5', commission_rate: '15', notes: 'Afternoons now.' };
    expect(patchPayload('m1', original, form, { pay: true })).toEqual({ id: 'm1', commission_rate: '15', notes: 'Afternoons now.' });
    expect(patchPayload('m1', original, form, { pay: false })).toEqual({ id: 'm1' });
    expect(patchPayload('m1', original, { ...original, hourly_rate: '13' }, { pay: true })).toEqual({ id: 'm1', hourly_rate: 1300 });
  });
});
