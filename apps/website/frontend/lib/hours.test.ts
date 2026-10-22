// The opening hours the editor starts from when the owner turns them on, and how a day's row changes.
import { describe, expect, it } from 'vitest';

import { addInterval, DAYS, defaultHours, removeInterval, setOpen, setTime } from './hours';

describe('opening hours', () => {
  it('start as a usual week: weekdays 09:00–18:00, the weekend closed, Monday first', () => {
    const week = defaultHours();
    expect(week.map((row) => row.day)).toEqual([...DAYS]);
    expect(week[0]).toEqual({ day: 'mon', intervals: [{ opens: '09:00', closes: '18:00' }] });
    expect(week[5]).toEqual({ day: 'sat', intervals: [] });
    expect(week[6]).toEqual({ day: 'sun', intervals: [] });
  });

  it('opening a closed day gives it the usual hours; closing one empties it', () => {
    const week = defaultHours();
    const saturday = setOpen(week, 'sat', true);
    expect(saturday.find((row) => row.day === 'sat')?.intervals).toEqual([{ opens: '09:00', closes: '18:00' }]);
    expect(setOpen(saturday, 'sat', false).find((row) => row.day === 'sat')?.intervals).toEqual([]);
    expect(week[5].intervals).toEqual([]); // never in place
  });

  it('a day takes up to three intervals, added after the last and removed one by one', () => {
    let week = defaultHours();
    week = addInterval(week, 'mon');
    expect(week[0].intervals).toEqual([
      { opens: '09:00', closes: '18:00' },
      { opens: '18:00', closes: '20:00' },
    ]);
    week = addInterval(addInterval(week, 'mon'), 'mon');
    expect(week[0].intervals).toHaveLength(3);
    week = removeInterval(week, 'mon', 0);
    expect(week[0].intervals[0]).toEqual({ opens: '18:00', closes: '20:00' });
  });

  it('changes one time of one interval', () => {
    const week = setTime(defaultHours(), 'tue', 0, 'closes', '14:00');
    expect(week[1].intervals).toEqual([{ opens: '09:00', closes: '14:00' }]);
  });
});
