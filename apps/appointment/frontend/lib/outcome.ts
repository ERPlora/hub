// What booking a series' dates tells the person (APPOINTMENT-F12, F13): only what happened — «{booked}
// appointments booked», «{skipped} could not be booked», or that the window was already booked —, each
// skipped date with the server's reason (in the reader's language), and either the dates still to book (from
// `next_from`: «Book appointments» again) or, when nothing was in the window yet, the series' next date beyond it. Editing a
// series «from this occurrence on» (APPOINTMENT-F14) says only what happened (appointments#293), to whom
// and for which services the appointments now go (#256, #294), and what kept its time.
import type { MaterializeOut, RecurringUpdatedOut, RecurringUpdateIn } from '../operations';
import { formatDay } from './clock';

type Translate = (key: string, named?: Record<string, unknown>) => string;

export interface OutcomeText {
  summary: string;
  skipped: string[];
  more: string;
}

export function describeOutcome(outcome: MaterializeOut, t: Translate, locale: string): OutcomeText {
  const skipped = outcome.skipped.map((skip) => `${formatDay(skip.occurrence_date, locale)}: ${skip.message}`);
  let more = '';
  if (outcome.next_from) more = t('appointment.series.outcome.pendingFrom', { date: formatDay(outcome.next_from, locale) });
  else if (outcome.upcoming_date) more = t('appointment.series.outcome.upcoming', { date: formatDay(outcome.upcoming_date, locale) });
  const parts: string[] = [];
  if (outcome.booked) parts.push(t('appointment.series.outcome.booked', { booked: outcome.booked }));
  if (skipped.length) parts.push(t('appointment.series.outcome.notBooked', { skipped: skipped.length }));
  let summary = parts.join(' · ');
  if (!summary && outcome.already_booked) summary = t('appointment.series.outcome.alreadyBooked', { already: outcome.already_booked });
  else if (!summary) summary = t('appointment.series.outcome.none', {});
  return { summary, skipped, more };
}

/** What a series edit changed besides the time: who does it and which services (as sent). */
export type SeriesChange = Pick<RecurringUpdateIn, 'staff_id' | 'services'>;

export function describeUpdate(
  outcome: RecurringUpdatedOut,
  change: SeriesChange,
  t: Translate,
  locale: string,
): OutcomeText {
  const handed = Boolean(change.staff_id);
  const serviced = Boolean(change.services?.length);
  const named = { moved: outcome.moved, staff: outcome.recurring.staff_name, services: outcome.recurring.service_names };
  const parts: string[] = [];
  if (outcome.moved) {
    if (handed && serviced) parts.push(t('appointment.series.outcome.handedWithServices', named));
    else if (handed) parts.push(t('appointment.series.outcome.handed', { moved: named.moved, staff: named.staff }));
    else if (serviced) {
      parts.push(t('appointment.series.outcome.servicesChanged', { moved: named.moved, services: named.services }));
    } else parts.push(t('appointment.series.outcome.moved', { moved: outcome.moved }));
  }
  if (outcome.booked) parts.push(t('appointment.series.outcome.newDates', { booked: outcome.booked }));
  if (outcome.cancelled) parts.push(t('appointment.series.outcome.cancelled', { cancelled: outcome.cancelled }));
  if (outcome.locked) parts.push(t('appointment.series.outcome.locked', { locked: outcome.locked }));
  if (outcome.skipped.length) parts.push(t('appointment.series.outcome.notMoved', { skipped: outcome.skipped.length }));
  return {
    summary: parts.length ? parts.join(' · ') : t('appointment.series.outcome.unchanged'),
    skipped: outcome.skipped.map((skip) => `${formatDay(skip.occurrence_date, locale)}: ${skip.message}`),
    more: '',
  };
}
