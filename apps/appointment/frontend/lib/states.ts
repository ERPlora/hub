// What each appointment allows in its state: the same rules the server applies (services.py), so the
// agenda greys out what does not apply instead of hiding it (WORKBOOK «Agenda»), and the server still
// has the last word. Charged is final (the market: Fresha, Phorest): only its history. A check open in
// the till holds it: no no-show, cancel nor delete until that check is charged or voided.
import type { StatusPillTone } from '@erplora/ui/components';

import type { AppointmentRow, AppointmentStatus } from '../operations';

/** The row actions of the agenda, in the old list's order. */
export const ACTIONS = ['charge', 'edit', 'confirm', 'start', 'complete', 'no_show', 'cancel', 'history', 'delete'] as const;
export type AgendaAction = (typeof ACTIONS)[number];

const LIVE: readonly AppointmentStatus[] = ['pending', 'confirmed'];

/** «Charge» opened a check in the till that is not charged yet: charging again goes back to it. */
export function hasOpenCheck(item: Pick<AppointmentRow, 'order_id' | 'sale_id'>): boolean {
  return item.order_id !== null && item.sale_id === null;
}

/** Whether `item` allows `action` now (`now` decides a no-show: only once its time has passed). */
export function allows(action: AgendaAction, item: AppointmentRow, now: Date = new Date()): boolean {
  const charged = item.sale_id !== null;
  const held = hasOpenCheck(item);
  switch (action) {
    case 'charge':
      return !charged && item.status !== 'cancelled' && item.status !== 'no_show';
    case 'edit':
      return !charged && LIVE.includes(item.status);
    case 'confirm':
      return item.status === 'pending';
    case 'start':
      return !charged && LIVE.includes(item.status);
    case 'complete':
      return item.status === 'confirmed' || item.status === 'in_progress';
    case 'no_show':
      return !charged && !held && LIVE.includes(item.status) && new Date(item.start).getTime() <= now.getTime();
    case 'cancel':
      return !charged && !held && (LIVE.includes(item.status) || item.status === 'no_show');
    case 'history':
      return true;
    case 'delete':
      return !charged && !held && item.status !== 'in_progress' && item.status !== 'completed';
  }
}

/** The colour of each state (StatusPill). */
export const STATUS_TONE: Record<AppointmentStatus, StatusPillTone> = {
  pending: 'warning',
  confirmed: 'info',
  in_progress: 'info',
  completed: 'success',
  cancelled: 'neutral',
  no_show: 'danger',
};

/** The customer's name, or «Deleted customer» once her data was erased. */
export function customerLabel(item: Pick<AppointmentRow, 'customer_name'>, t: (key: string) => string): string {
  return item.customer_name || t('appointment.list.erasedCustomer');
}
