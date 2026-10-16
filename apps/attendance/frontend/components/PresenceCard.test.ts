// ATTENDANCE-F11 (who is clocked in now), the old «Clocked in now» panel, above the team's records: how
// many people have their day open and who — since when, and whether they are on a break. Live
// (`attendance.presence.list`): it changes as soon as anyone clocks or a day is corrected.
import { describe, expect, it } from 'vitest';

import { errorFrame, flush, mountAttendance } from '../__tests__/mount-attendance';
import type { PresenceOut } from '../operations';
import PresenceCard from './PresenceCard.vue';

const ANA: PresenceOut = {
  record_id: 'r1',
  member_id: 'm1',
  member_name: 'Ana López',
  clock_in_at: '2026-10-06T07:00:00Z',
  break_started_at: null,
  source: 'shared',
};
const BEA: PresenceOut = { ...ANA, record_id: 'r2', member_id: 'm2', member_name: 'Bea Ruiz', break_started_at: '2026-10-06T08:00:00Z' };

const page = (rows: PresenceOut[]) => ({ rows, total: rows.length, limit: 100, offset: 0 });

async function setup(locale: 'en' | 'es' = 'en') {
  const m = await mountAttendance(PresenceCard, { locale, path: '/attendance/records' });
  await m.live();
  return m;
}

describe('PresenceCard (ATTENDANCE-F11)', () => {
  it('follows who is in, live', async () => {
    const s = await setup();
    expect(s.params('attendance.presence.list')).toEqual([{ limit: 100 }]);
    await s.result('attendance.presence.list', page([ANA, BEA]));
    expect(s.find('attendance-presence-count').text()).toBe('2 clocked in');
    const rows = s.wrapper.findAll('[data-testid="attendance-presence-row"]').map((r) => r.text().replace(/\s+/g, ' '));
    expect(rows).toEqual(['Ana López since 09:00', 'Bea Ruiz since 09:00 On break']);
    await s.result('attendance.presence.list', page([ANA]), {}, 2);
    expect(s.find('attendance-presence-count').text()).toBe('1 clocked in');
  });

  it('says when nobody is in', async () => {
    const s = await setup();
    await s.result('attendance.presence.list', page([]));
    expect(s.find('attendance-presence-empty').text()).toBe('Nobody is clocked in right now.');
  });

  it('a failure is told in its place', async () => {
    const s = await setup();
    s.net.lastStream().push(errorFrame(s.subId('attendance.presence.list'), 'boom'));
    await flush();
    expect(s.find('attendance-presence-error').text()).toContain('Who is clocked in could not be loaded.');
  });

  it('speaks Spanish', async () => {
    const s = await setup('es');
    await s.result('attendance.presence.list', page([BEA]));
    expect(s.find('attendance-presence').text()).toContain('Fichados ahora');
    expect(s.find('attendance-presence-row').text().replace(/\s+/g, ' ')).toBe('Bea Ruiz desde las 09:00 En pausa');
  });
});
