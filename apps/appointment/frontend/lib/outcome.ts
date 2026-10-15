// What booking a series' dates tells the person (APPOINTMENT-F12, F13), as the old series view said it:
// «{booked} appointments booked · {skipped} could not be booked», each skipped date with the server's
// reason (in the reader's language), and either the dates still to book (from `next_from`: «Book
// appointments» again) or, when nothing was in the window yet, the series' next date beyond it.
import type { MaterializeOut } from '../operations';
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
  return {
    summary: t('appointment.series.outcome.booked', { booked: outcome.booked, skipped: outcome.skipped.length }),
    skipped,
    more,
  };
}
