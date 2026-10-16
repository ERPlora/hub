// What a reservation row offers by its status — the server's steps (services.py STEPS): confirm a pending
// one; seat a pending or confirmed one; complete a seated one; cancel or mark a no-show a pending or
// confirmed one; edit always (once finished, only its notes: the server says so); delete always (the
// admin). The colour of each status; the next slot of the day the bar shows; the opening hours in a line.
import type { StatusPillTone } from '@erplora/ui/components';

import type { DayOut, ReservationStatus, SlotLoadOut, SpanOut } from '../operations';

export type RowAction = 'confirm' | 'seat' | 'complete' | 'cancel' | 'no_show' | 'edit' | 'delete';

const FROM: Record<RowAction, readonly string[] | null> = {
  confirm: ['pending'],
  seat: ['pending', 'confirmed'],
  complete: ['seated'],
  cancel: ['pending', 'confirmed'],
  no_show: ['pending', 'confirmed'],
  edit: null,
  delete: null,
};

/** Whether `action` applies to a reservation in `status`. */
export function allows(action: RowAction, status: string): boolean {
  const from = FROM[action];
  return from === null || from.includes(status);
}

const TONES: Record<ReservationStatus, StatusPillTone> = {
  pending: 'warning',
  confirmed: 'info',
  seated: 'success',
  completed: 'neutral',
  cancelled: 'danger',
  no_show: 'danger',
};

export function statusTone(status: string): StatusPillTone {
  return TONES[status as ReservationStatus] ?? 'neutral';
}

/** What the day bar says about the next slot. `open`/`full` carry the slot. */
export type NextSlot = { state: 'open' | 'full'; slot: SlotLoadOut } | { state: 'over' | 'no-service' | 'closed' };

/**
 * The slot to watch: on today, the first one that has not ended yet (one in progress still takes late
 * bookings); on any other day, its first one. A day blocked whole, or shut in Schedules, is closed.
 */
export function nextSlot(day: DayOut, isToday: boolean, now: string): NextSlot {
  if (day.closed || (day.hours_restricted && day.spans.length === 0)) return { state: 'closed' };
  if (day.slots.length === 0) return { state: 'no-service' };
  const ordered = [...day.slots].sort((a, b) => a.start_time.localeCompare(b.start_time));
  const slot = isToday ? ordered.find((s) => s.end_time.slice(0, 5) > now) : ordered[0];
  if (!slot) return { state: 'over' };
  return { state: slot.full ? 'full' : 'open', slot };
}

/** The day's opening spans as one line («13:00–16:00 · 20:00–02:00»), each time painted by `time`. */
export function spansLine(spans: readonly SpanOut[], time: (hhmm: string) => string): string {
  return [...spans]
    .sort((a, b) => a.start.localeCompare(b.start))
    .map((span) => `${time(span.start.slice(11, 16))}–${time(span.end.slice(11, 16))}`)
    .join(' · ');
}
