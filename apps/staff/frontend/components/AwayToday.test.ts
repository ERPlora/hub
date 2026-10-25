// STAFF-G05 (the old Home panel «Today's time off», STAFF-F20): above the time-off list while the Hub's
// Home has no panels — who has an approved absence covering today (the business's day), whole days first
// and then by name, with its type and, for part of the day, its hours; never the reason. Followed live
// from `staff.time_off.today`.
import { describe, expect, it } from 'vitest';

import type { TimeOffOut } from '../operations';
import { errorFrame, flush, mountStaff, page } from '../__tests__/mount-staff';
import AwayToday from './AwayToday.vue';

const OP = 'staff.time_off.today';

const away = (id: string, over: Partial<TimeOffOut> = {}): TimeOffOut => ({
  id,
  member_id: `m-${id}`,
  member_name: 'Ana López',
  leave_type: 'vacation',
  leave_type_label: 'Vacation',
  start_date: '2026-10-19',
  end_date: '2026-10-21',
  is_full_day: true,
  start_time: null,
  end_time: null,
  status: 'approved',
  approved_by_id: 1,
  approved_at: '2026-10-10T09:00:00Z',
  ...over,
});
const ROWS = [
  away('t1'),
  away('t2', { member_name: 'Bea Ruiz', leave_type: 'personal', is_full_day: false, start_time: '10:00:00', end_time: '13:30:00' }),
];

async function setup(locale: 'en' | 'es' = 'en') {
  const m = await mountStaff(AwayToday, { locale });
  await m.live();
  const rows = () => m.wrapper.findAll('[data-testid="staff-away-today-row"]').map((row) => row.text().replace(/\s+/g, ' ').trim());
  return { ...m, rows };
}

describe('AwayToday', () => {
  it('follows staff.time_off.today, its first hundred', async () => {
    const s = await setup();
    expect(s.params(OP)).toEqual([{ limit: 100 }]);
    expect(s.find('staff-away-today').find('h2').text()).toBe('Today’s time off');
  });

  it('lists who is away in the server’s order, with the type and, for part of the day, the hours', async () => {
    const s = await setup();
    await s.result(OP, page(ROWS, 2, 100));
    expect(s.find('staff-away-today-count').text()).toBe('2 away');
    expect(s.rows()).toEqual(['Ana López Vacation · All day', 'Bea Ruiz Personal · 10:00–13:30']);
  });

  it('nobody away says so', async () => {
    const s = await setup();
    await s.result(OP, page([], 0, 100));
    expect(s.find('staff-away-today-empty').text()).toBe('Nobody is away today.');
    expect(s.rows()).toEqual([]);
  });

  it('a read that fails says so in its place (the list below keeps working)', async () => {
    const s = await setup();
    s.net.lastStream().push(errorFrame(s.subId(OP), 'boom'));
    await flush();
    expect(s.find('staff-away-today-error').text()).toBe('Who is away today could not be loaded');
  });

  it('speaks Spanish with the old panel’s title', async () => {
    const s = await setup('es');
    await s.result(OP, page(ROWS, 2, 100));
    expect(s.find('staff-away-today').find('h2').text()).toBe('Ausencias de hoy');
    expect(s.find('staff-away-today-count').text()).toBe('2 ausentes');
    expect(s.rows()).toEqual(['Ana López Vacaciones · Todo el día', 'Bea Ruiz Asuntos propios · 10:00–13:30']);
    await s.result(OP, page(ROWS.slice(0, 1), 1, 100), {}, 2);
    expect(s.find('staff-away-today-count').text()).toBe('1 ausente');
  });
});
