// The weekdays as the slots count them (0 = Monday … 6 = Sunday), with the key of their name.
import { describe, expect, it } from 'vitest';

import { WEEKDAYS, weekdayKey } from './weekdays';

describe('weekdays', () => {
  it('go from Monday to Sunday, the slots’ order', () => {
    expect(WEEKDAYS).toEqual(['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']);
    expect([weekdayKey(0), weekdayKey(6), weekdayKey(9)]).toEqual(['reservation.weekday.monday', 'reservation.weekday.sunday', '']);
  });
});
