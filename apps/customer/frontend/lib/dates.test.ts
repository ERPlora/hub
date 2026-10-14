// A day of the card (birthday, anniversary: `YYYY-MM-DD`) in the page language. `formatDateTime` of
// @erplora/ui paints a moment (date and time); a day has no time nor time zone, so it never shifts.
import { describe, expect, it } from 'vitest';

import { formatDay } from './dates';

describe('formatDay', () => {
  it('paints a day in the page language, the same day in any time zone', () => {
    expect(formatDay('1990-02-03', 'en')).toBe('Feb 3, 1990');
    expect(formatDay('1990-02-03', 'es')).toBe('3 feb 1990');
  });

  it('nothing to show is «—»; a text that is not a day is shown as it came', () => {
    expect(formatDay(null, 'en')).toBe('—');
    expect(formatDay('', 'en')).toBe('—');
    expect(formatDay('soon', 'en')).toBe('soon');
  });
});
