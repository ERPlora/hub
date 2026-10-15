// APPOINTMENT-F02 «Ver qué horas quedan libres»: with services, a professional and a day, the free times
// as buttons (a tap fills the time); the ones inside the minimum notice are marked. Asking the length:
// the services, or the minutes typed. «Looking for free times…», none left, and down with Retry.
import { describe, expect, it } from 'vitest';

import { click, errorFrame, mountAppointment, settle } from '../__tests__/mount-appointment';
import FreeSlots from './FreeSlots.vue';

const OP = 'appointment.availability.slots';
const slot = (time: string, withinNotice = false) => ({
  start: `2026-10-19T${time}:00+02:00`,
  end: `2026-10-19T${time}:00+02:00`,
  within_notice: withinNotice,
  staff_ids: ['s1'],
});

async function setup(props: Record<string, unknown> = {}) {
  const m = await mountAppointment(FreeSlots, {
    props: { date: '2026-10-19', serviceIds: ['c1', 'c2'], staffId: 's1', selected: '', ...props },
  });
  await m.live();
  const buttons = () => m.wrapper.findAll('[data-testid="appointment-slots-time"]');
  return { ...m, buttons };
}

describe('FreeSlots', () => {
  it('asks the free times of the day for the services and the professional', async () => {
    const s = await setup({ excludeId: 'a1' });
    expect(s.params(OP)).toEqual([{ date: '2026-10-19', service_ids: ['c1', 'c2'], staff_id: 's1', exclude_id: 'a1' }]);
    expect(s.find('appointment-slots-loading').text()).toBe('Looking for free times…');
  });

  it('asks by the minutes typed when they replace the services’ length', async () => {
    const s = await setup({ durationMinutes: 50 });
    expect(s.params(OP)).toEqual([{ date: '2026-10-19', duration_minutes: 50, staff_id: 's1' }]);
  });

  it('paints each free time as a button that fills the time, the chosen one pressed', async () => {
    const s = await setup({ selected: '10:30' });
    await s.result(OP, { date: '2026-10-19', timezone: 'Europe/Madrid', duration_minutes: 30, slots: [slot('10:00', true), slot('10:30')] });
    expect(s.buttons().map((b) => b.text())).toEqual(['10:00 AM', '10:30 AM']);
    expect(s.buttons()[0].attributes('title')).toBe('inside the minimum notice');
    expect(s.buttons()[1].attributes('aria-pressed')).toBe('true');
    await click(s.buttons()[0].element);
    expect(s.wrapper.emitted('pick')).toEqual([['10:00']]);
  });

  it('says when nothing is left, and offers Retry when it cannot load', async () => {
    const s = await setup();
    await s.result(OP, { date: '2026-10-19', timezone: 'Europe/Madrid', duration_minutes: 30, slots: [] });
    expect(s.find('appointment-slots-empty').text()).toContain('No free times that day');
    s.net.lastStream().push(errorFrame(s.subId(OP), 'appointment.boom'));
    await settle();
    expect(s.find('appointment-slots-error').text()).toContain('The free times could not be loaded.');
  });
});
