// STAFF-G02, G03, G04 (the old Home panels «Active staff», «On leave today» and «Pending time off»,
// STAFF-F20, F23): three figures above the staff list while the Hub's Home has no panels, followed
// live from `staff.member.stats`; a write anywhere re-runs it on the server.
import { describe, expect, it } from 'vitest';

import { errorFrame, flush, mountStaff } from '../__tests__/mount-staff';
import StaffFigures from './StaffFigures.vue';

const OP = 'staff.member.stats';
const STATS = { total: 7, active: 5, on_leave: 1, inactive: 1, absent_today: 2, pending_time_off: 3 };

async function setup(locale: 'en' | 'es' = 'en') {
  const m = await mountStaff(StaffFigures, { locale });
  await m.live();
  const figure = (id: string) => m.find(`staff-figures-${id}`);
  const labels = () => ['active', 'away', 'pending'].map((id) => figure(id).find('.staff-figure__label').text());
  const values = () => ['active', 'away', 'pending'].map((id) => figure(id).find('.staff-figure__value').text());
  return { ...m, figure, labels, values };
}

describe('StaffFigures', () => {
  it('follows staff.member.stats and shows «…» in each figure until the first result', async () => {
    const s = await setup();
    expect(s.params(OP)).toEqual([{}]);
    expect(s.find('staff-figures').attributes('aria-busy')).toBe('true');
    expect(s.values()).toEqual(['…', '…', '…']);
  });

  it('paints the active staff, who is away today and the requests waiting, as the old panels', async () => {
    const s = await setup();
    await s.result(OP, STATS);
    const group = s.find('staff-figures');
    expect([group.attributes('role'), group.attributes('aria-label'), group.attributes('aria-busy')]).toEqual(['group', 'Figures', 'false']);
    expect(s.labels()).toEqual(['Active staff', 'On leave today', 'Pending time off']);
    expect(s.values()).toEqual(['5', '2', '3']);
  });

  it('follows a new result without reloading', async () => {
    const s = await setup();
    await s.result(OP, STATS);
    await s.result(OP, { ...STATS, active: 6, pending_time_off: 0 }, {}, 2);
    expect(s.values()).toEqual(['6', '2', '0']);
  });

  it('a read that fails says so in its place (the list below keeps working)', async () => {
    const s = await setup();
    s.net.lastStream().push(errorFrame(s.subId(OP), 'boom'));
    await flush();
    expect(s.find('staff-figures-error').text()).toBe('The figures could not be loaded');
    expect(s.find('staff-figures-active').exists()).toBe(false);
  });

  it('speaks Spanish with the old panels’ words', async () => {
    const s = await setup('es');
    await s.result(OP, STATS);
    expect(s.labels()).toEqual(['Plantilla activa', 'Ausentes hoy', 'Ausencias pendientes']);
    expect(s.find('staff-figures').attributes('aria-label')).toBe('Cifras');
  });
});
