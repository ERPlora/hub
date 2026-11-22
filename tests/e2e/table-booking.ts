import { expect, test } from '@playwright/test';

import { bookingTimes, type BookingTimes, untilMidnight } from './table-clock';

/** The times of a test's reservations (table-clock.ts). In the last minutes of the day none of today is left: the
 *  test waits for midnight first (less than ten minutes), its timeout stretched by exactly that wait. */
export async function reservationTimes(): Promise<BookingTimes> {
  const now = new Date();
  const times = bookingTimes(now);
  if (times) return times;
  const wait = untilMidnight(now) + 1_000;
  test.setTimeout(test.info().timeout + wait);
  await new Promise((done) => setTimeout(done, wait));
  const after = bookingTimes(new Date());
  expect(after, 'a time of the new day after midnight').not.toBeNull();
  return after!;
}
