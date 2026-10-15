// The inbox's row actions and what each one allows: the diary's own rules (Appointments' `lib/states.ts`, the
// server's), never copied, so the inbox greys out exactly what the agenda would; and who sees which action.
import { describe, expect, it } from 'vitest';

import type { BookingRow } from '../operations';
import { allowed, INBOX_ACTIONS, inboxActions } from './actions';

const row = (over: Partial<BookingRow> = {}) =>
  ({ status: 'pending', start: '2030-03-05T10:00:00+01:00', sale_id: null, order_id: null, ...over }) as BookingRow;
const BEFORE = new Date('2030-03-05T08:00:00Z');
const AFTER = new Date('2030-03-05T10:00:00Z');

describe('the inbox actions', () => {
  it('are the old module’s, in its order', () => {
    expect(INBOX_ACTIONS).toEqual(['confirm', 'complete', 'no_show', 'cancel', 'delete']);
  });

  it('follow the diary’s rules for each state', () => {
    expect(INBOX_ACTIONS.filter((id) => allowed(id, row(), AFTER))).toEqual(['confirm', 'no_show', 'cancel', 'delete']);
    expect(INBOX_ACTIONS.filter((id) => allowed(id, row({ status: 'confirmed' }), BEFORE))).toEqual(['complete', 'cancel', 'delete']);
    expect(INBOX_ACTIONS.filter((id) => allowed(id, row({ status: 'completed' }), AFTER))).toEqual([]);
    expect(INBOX_ACTIONS.filter((id) => allowed(id, row({ status: 'cancelled' }), AFTER))).toEqual(['delete']);
    expect(INBOX_ACTIONS.filter((id) => allowed(id, row({ status: 'confirmed', sale_id: 's1' }), AFTER))).toEqual(['complete']);
  });

  it('offer each person what their rights allow', () => {
    const can = (rights: string[]) => (permission: string) => rights.includes(permission);
    expect(inboxActions(can(['online_booking.view_booking']))).toEqual([]);
    expect(inboxActions(can(['online_booking.change_booking', 'online_booking.confirm_booking']))).toEqual([
      'confirm',
      'complete',
      'no_show',
      'cancel',
    ]);
    expect(
      inboxActions(can(['online_booking.change_booking', 'online_booking.confirm_booking', 'online_booking.delete_booking'])),
    ).toEqual(INBOX_ACTIONS);
  });
});
