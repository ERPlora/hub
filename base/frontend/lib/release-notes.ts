import type { StatusPillTone } from '@erplora/ui/components';

import type { ReleaseNote } from '../operations/system';

export const KIND_TONE: Record<ReleaseNote['kind'], StatusPillTone> = {
  new: 'success',
  improved: 'info',
  fixed: 'neutral',
};

/** A note's day (`YYYY-MM-DD`) in `locale`. It is a calendar day, not an instant: read in UTC, so a device west of
 *  Greenwich does not show the day before. */
export function releaseDay(day: string, locale: string): string {
  return new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeZone: 'UTC' }).format(new Date(`${day}T00:00:00Z`));
}
