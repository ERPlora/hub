// What the booking panel sends to the server, and where the server's refusals go back in it.
import type { ApiError } from '@erplora/ui/sdk';

import type { AppointmentCreateIn, AppointmentOut, RecurringUpdateIn, UpdateIn } from '../operations';
import { dayOf, wallInput } from './clock';

/** What the panel holds. */
export interface Chosen {
  day: string;
  /** `HH:MM`. */
  time: string;
  /** The minutes the person set; `null` while the services decide the length. */
  minutes: number | null;
  staffId: string | null;
  serviceIds: string[];
  notes: string;
  internalNotes: string;
}

const refs = (ids: readonly string[]) => ids.map((id) => ({ service_id: id }));

export function newBooking(chosen: Chosen, customerId: string | null, confirmOverlap: boolean): AppointmentCreateIn {
  return {
    customer_id: customerId,
    services: refs(chosen.serviceIds),
    staff_id: chosen.staffId,
    start: wallInput(chosen.day, chosen.time),
    ...(chosen.minutes ? { duration_minutes: chosen.minutes } : {}),
    notes: chosen.notes,
    internal_notes: chosen.internalNotes,
    confirm_overlap: confirmOverlap,
  };
}

/** What an edit changes of the appointment's slot (time, length, professional, services). */
export function slotChanges(booked: AppointmentOut, chosen: Chosen): Partial<UpdateIn> {
  const out: Partial<UpdateIn> = {};
  const start = wallInput(chosen.day, chosen.time);
  if (start !== booked.start.slice(0, 16)) out.start = start;
  if (chosen.minutes && chosen.minutes !== booked.duration_minutes) out.duration_minutes = chosen.minutes;
  if (chosen.staffId && chosen.staffId !== booked.staff_id) out.staff_id = chosen.staffId;
  if (chosen.serviceIds.join() !== booked.services.map((line) => line.service_id).join()) out.services = refs(chosen.serviceIds);
  return out;
}

export function noteChanges(booked: AppointmentOut, chosen: Chosen): Partial<UpdateIn> {
  const out: Partial<UpdateIn> = {};
  if (chosen.notes !== booked.notes) out.notes = chosen.notes;
  if (chosen.internalNotes !== booked.internal_notes) out.internal_notes = chosen.internalNotes;
  return out;
}

/** «This and all following»: the slot changes, for the series of `booked` from its date. */
export function seriesChange(booked: AppointmentOut, chosen: Chosen): RecurringUpdateIn {
  const slot = slotChanges(booked, chosen);
  const change: RecurringUpdateIn = { id: booked.recurring_id ?? '', from_date: booked.occurrence_date ?? '' };
  if (slot.start) {
    change.time = wallInput(chosen.day, chosen.time).slice(11);
    if (chosen.day !== dayOf(booked.start)) change.day_of_week = (new Date(`${chosen.day}T00:00:00Z`).getUTCDay() + 6) % 7;
  }
  if (slot.duration_minutes) change.duration_minutes = slot.duration_minutes;
  if (slot.staff_id) change.staff_id = slot.staff_id;
  if (slot.services) change.services = slot.services;
  return change;
}

const FIELD_OF: Record<string, string> = { duration_minutes: 'minutes', staff_id: 'staff', customer_id: 'customer' };

/** The refusal with each reason under the panel's own field (`services.0` under the services). */
export function refusedFields(error: ApiError | null): ApiError | null {
  if (!error?.fields) return error;
  const fields = Object.fromEntries(Object.entries(error.fields).map(([key, message]) => [FIELD_OF[key] ?? key.split('.')[0], message]));
  return { ...error, fields } as ApiError;
}
