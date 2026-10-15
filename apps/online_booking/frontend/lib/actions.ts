// The inbox's row actions (the old module's, in its order) and what each one allows: the diary's own rules,
// read from Appointments' `lib/states.ts` (the same the agenda and the server apply), never copied. A booking
// row carries the fields those rules read (status, start, sale and open check).
import { allows } from '../../../appointment/frontend/lib/states';
import type { AppointmentRow } from '../../../appointment/frontend/operations';
import type { BookingRow } from '../operations';

export const INBOX_ACTIONS = ['confirm', 'complete', 'no_show', 'cancel', 'delete'] as const;
export type InboxAction = (typeof INBOX_ACTIONS)[number];

/** The right each action needs in this app (the diary's is checked by the server). */
const NEEDS: Record<InboxAction, string> = {
  confirm: 'online_booking.confirm_booking',
  complete: 'online_booking.change_booking',
  no_show: 'online_booking.change_booking',
  cancel: 'online_booking.change_booking',
  delete: 'online_booking.delete_booking',
};

/** Whether `row` allows `action` now (`now` decides a no-show: only once its time has passed). */
export function allowed(action: InboxAction, row: BookingRow, now: Date = new Date()): boolean {
  return allows(action, row as unknown as AppointmentRow, now);
}

/** The actions the person's rights offer, in order. */
export function inboxActions(can: (permission: string) => boolean): InboxAction[] {
  return INBOX_ACTIONS.filter((action) => can(NEEDS[action]));
}
