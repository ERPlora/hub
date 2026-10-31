// The record form of a staff member (STAFF-F01, F02, F03, F21): one form for «New» and for
// «Edit · {name}», and the operation input each one sends. New sends the whole typed record; Edit sends
// only what changed (`null` clears the role, the Hub user or the hire date). The pay (hourly rate in the
// business's currency → its whole minor units, commission in %, HR notes) only travels for whoever may see
// it: the server refuses it otherwise. Nothing here judges a value: the server does, and says it under its field.
import type { CompensationOut, MemberDetailOut, MemberIn, MemberPatchIn, MemberStatus } from '../operations';
import { centsFromText, type Money, moneyText } from './format';

/** What the form holds while it is typed: every field as its control holds it. */
export interface MemberForm {
  first_name: string;
  last_name: string;
  email: string;
  phone: string;
  employee_number: string;
  /** `''` = «No role». */
  role_id: string;
  /** `''` = «No Hub access»; else the account's id as the select holds it. */
  user_id: string;
  status: MemberStatus;
  is_bookable: boolean;
  booking_buffer: string;
  /** `YYYY-MM-DD`, or `''`. */
  hire_date: string;
  color: string;
  specialties: string;
  bio: string;
  /** The business's currency as typed. */
  hourly_rate: string;
  commission_rate: string;
  notes: string;
}

/** Who sends the form: whether they may see (and so send) the pay, and the business's currency it is typed in
 *  (`useBusinessMoney`; unknown while it has not answered: two decimals). */
export interface SendOptions {
  pay: boolean;
  money?: Money;
}

const TEXTS = ['first_name', 'last_name', 'email', 'phone', 'employee_number', 'color', 'specialties', 'bio'] as const;

export function blankMemberForm(): MemberForm {
  return {
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
  };
}

/** The commission as a number the server reads («7,5» → «7.5»); empty is 0. */
function commission(text: string): string {
  const trimmed = text.trim().replace(',', '.');
  return trimmed === '' ? '0' : trimmed;
}

/** Whole minor units of `money`, or the text as typed when it is not a figure (the server refuses it under its field). */
function rate(text: string, money?: Money): number {
  const cents = centsFromText(text, money);
  return (cents ?? text.trim()) as number;
}

/** A whole number field; what is not one goes as typed for the server to refuse. */
function whole(text: string): number {
  const trimmed = text.trim();
  if (trimmed === '') return 0;
  return (/^-?\d+$/.test(trimmed) ? Number(trimmed) : trimmed) as number;
}

/** «New»: the record as typed. Born active (no status); role, Hub user and hire date only when set. */
export function createPayload(form: MemberForm, options: SendOptions): MemberIn {
  const payload: MemberIn = {
    first_name: form.first_name.trim(),
    last_name: form.last_name.trim(),
    email: form.email.trim(),
    phone: form.phone.trim(),
    employee_number: form.employee_number.trim(),
    is_bookable: form.is_bookable,
    booking_buffer: whole(form.booking_buffer),
    color: form.color.trim(),
    specialties: form.specialties.trim(),
    bio: form.bio.trim(),
  };
  if (form.role_id) payload.role_id = form.role_id;
  if (form.user_id) payload.user_id = form.user_id;
  if (form.hire_date) payload.hire_date = form.hire_date;
  if (options.pay) {
    payload.hourly_rate = rate(form.hourly_rate, options.money);
    payload.commission_rate = commission(form.commission_rate);
    payload.notes = form.notes.trim();
  }
  return payload;
}

/** «Edit · {name}»: the record (and, when given, its pay, in the decimals of `money`) in the form's fields. */
export function formFromRecord(record: MemberDetailOut, pay: CompensationOut | null, locale: string, money?: Money): MemberForm {
  return {
    first_name: record.first_name,
    last_name: record.last_name,
    email: record.email,
    phone: record.phone,
    employee_number: record.employee_number,
    role_id: record.role_id ?? '',
    user_id: record.user_id ?? '',
    status: record.status,
    is_bookable: record.is_bookable,
    booking_buffer: String(record.booking_buffer),
    hire_date: record.hire_date ?? '',
    color: record.color,
    specialties: record.specialties,
    bio: record.bio,
    hourly_rate: pay ? moneyText(pay.hourly_rate, locale, money) : '',
    commission_rate: pay ? String(Number(pay.commission_rate)) : '',
    notes: pay?.notes ?? '',
  };
}

/** «Edit»: only what changed from `original`; `null` clears the role, the Hub user or the hire date. */
export function patchPayload(id: string, original: MemberForm, form: MemberForm, options: SendOptions): MemberPatchIn {
  const patch: MemberPatchIn = { id };
  for (const field of TEXTS) {
    if (form[field].trim() !== original[field].trim()) patch[field] = form[field].trim();
  }
  if (form.status !== original.status) patch.status = form.status;
  if (form.is_bookable !== original.is_bookable) patch.is_bookable = form.is_bookable;
  if (form.booking_buffer.trim() !== original.booking_buffer.trim()) patch.booking_buffer = whole(form.booking_buffer);
  if (form.role_id !== original.role_id) patch.role_id = form.role_id || null;
  if (form.user_id !== original.user_id) patch.user_id = form.user_id || null;
  if (form.hire_date !== original.hire_date) patch.hire_date = form.hire_date || null;
  if (options.pay) {
    const typed = centsFromText(form.hourly_rate, options.money);
    if (typed === null || typed !== centsFromText(original.hourly_rate, options.money)) {
      patch.hourly_rate = rate(form.hourly_rate, options.money);
    }
    if (Number(commission(form.commission_rate)) !== Number(commission(original.commission_rate)) || Number.isNaN(Number(commission(form.commission_rate)))) {
      patch.commission_rate = commission(form.commission_rate);
    }
    if (form.notes.trim() !== original.notes.trim()) patch.notes = form.notes.trim();
  }
  return patch;
}
