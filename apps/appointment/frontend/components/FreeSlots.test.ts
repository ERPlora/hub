// APPOINTMENT-F02 «See which times are free»: with services, a professional and a day, the free times as big buttons
// (a tap fills the time), in one tab per span the professional works that day with how many are free in each, under a
// sentence that says the shift. The ones inside the minimum notice are marked. Asking the length: the services, or the
// minutes typed. «Looking for free times…», none left, a day off, and down with Retry.
import { describe, expect, it } from 'vitest';

import { click, errorFrame, ionValue, mountAppointment, settle } from '../__tests__/mount-appointment';
import FreeSlots from './FreeSlots.vue';

const OP = 'appointment.availability.slots';
const at = (time: string) => `2026-10-19T${time}:00+02:00`;
const slot = (time: string, withinNotice = false) => ({ start: at(time), end: at(time), within_notice: withinNotice, staff_ids: ['s1'] });
const MORNING = { start: at('10:00'), end: at('14:00') };
const AFTERNOON = { start: at('16:00'), end: at('20:00') };
const answer = (windows: unknown[], slots: unknown[]) => ({ date: '2026-10-19', timezone: 'Europe/Madrid', duration_minutes: 30, windows, slots });
const SPLIT = answer([MORNING, AFTERNOON], [slot('10:00', true), slot('13:30'), slot('16:00'), slot('16:30'), slot('19:15')]);

async function setup(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountAppointment(FreeSlots, {
    props: { date: '2026-10-19', serviceIds: ['c1', 'c2'], staffId: 's1', staffName: 'Ana López', selected: '', today: '2026-10-19', ...props },
    locale,
  });
  await m.live();
  const buttons = () => m.wrapper.findAll('[data-testid="appointment-slots-time"]');
  const times = () => buttons().map((b) => b.text());
  const tabs = () => m.wrapper.findAll('.free-slots__window').map((tab) => tab.findAll('span, small').map((part) => part.text()).join(' '));
  return { ...m, buttons, times, tabs };
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

  it('a split shift: the sentence, one tab per span with its free times, the first with a free time open', async () => {
    const s = await setup();
    await s.result(OP, SPLIT);
    expect(s.find('appointment-slots-shift').text()).toBe('Ana López works today from 10:00 AM to 2:00 PM and from 4:00 PM to 8:00 PM.');
    expect(s.tabs()).toEqual(['10:00 AM – 2:00 PM 2 free', '4:00 PM – 8:00 PM 3 free']);
    expect(s.times()).toEqual(['10:00 AM', '1:30 PM']);
    await ionValue(s.find('appointment-slots-windows').element, '1');
    expect(s.times()).toEqual(['4:00 PM', '4:30 PM', '7:15 PM']);
    expect(s.wrapper.emitted('off')).toEqual([[false]]);
  });

  it('opens the span of the chosen time, presses it, and a tap fills the time', async () => {
    const s = await setup({ selected: '16:30' });
    await s.result(OP, SPLIT);
    expect(s.times()).toEqual(['4:00 PM', '4:30 PM', '7:15 PM']);
    expect(s.buttons().map((b) => b.attributes('aria-pressed'))).toEqual(['false', 'true', 'false']);
    await click(s.buttons()[2].element);
    expect(s.wrapper.emitted('pick')).toEqual([['19:15']]);
  });

  it('marks the times inside the minimum notice, by name and in a legend, not by colour alone', async () => {
    const s = await setup();
    await s.result(OP, SPLIT);
    const notice = s.buttons()[0];
    expect([notice.attributes('title'), notice.attributes('aria-label')]).toEqual(['inside the minimum notice', '10:00 AM, inside the minimum notice']);
    expect(notice.classes()).toContain('choice-button--marked');
    expect(s.buttons()[1].attributes('aria-label')).toBeUndefined();
    expect(s.find('appointment-slots-notice').text()).toBe('Inside the minimum notice');
    await ionValue(s.find('appointment-slots-windows').element, '1');
    expect(s.find('appointment-slots-notice').exists()).toBe(false);
  });

  it('a shift in one go has no tabs; another day says its date', async () => {
    const s = await setup({ today: '2026-10-18' });
    await s.result(OP, answer([{ start: at('12:00'), end: at('20:00') }], [slot('12:00'), slot('12:30')]));
    expect(s.find('appointment-slots-shift').text()).toBe('Ana López works on Monday, October 19 from 12:00 PM to 8:00 PM.');
    expect(s.find('appointment-slots-windows').exists()).toBe(false);
    expect(s.times()).toEqual(['12:00 PM', '12:30 PM']);
  });

  it('a day off says so, without times, and tells the panel', async () => {
    const s = await setup();
    await s.result(OP, answer([], []));
    expect(s.find('appointment-slots-off').text()).toContain('Ana López does not work today.');
    expect(s.find('appointment-slots-off').text()).toContain('Pick another day or another professional.');
    expect([s.find('appointment-slots-shift').exists(), s.buttons().length]).toEqual([false, 0]);
    expect(s.wrapper.emitted('off')?.at(-1)).toEqual([true]);
  });

  // A time is still picked in the time field when none is free or the free ones cannot load.
  it.each([
    ['en', 'No free times that day for this professional. You can still pick a time.', 'The free times could not be loaded. You can still pick a time.'],
    ['es', 'No quedan horas libres ese día para este profesional. Puedes elegir una hora igualmente.', 'No se han podido cargar las horas libres. Puedes elegir una hora igualmente.'],
  ] as const)('says when nothing is left under the shift, and offers Retry when it cannot load (%s)', async (locale, empty, failed) => {
    const s = await setup({}, locale);
    await s.result(OP, answer([MORNING], []));
    expect(s.find('appointment-slots-shift').exists()).toBe(true);
    expect(s.find('appointment-slots-empty').text()).toContain(empty);
    s.net.lastStream().push(errorFrame(s.subId(OP), 'appointment.boom'));
    await settle();
    expect(s.find('appointment-slots-error').text()).toContain(failed);
    expect(s.wrapper.emitted('off')?.at(-1)).toEqual([false]);
  });

  it('speaks Spanish: the shift, the free ones of each span and a day off on another date', async () => {
    const s = await setup({}, 'es');
    await s.result(OP, SPLIT);
    expect(s.find('appointment-slots-shift').text()).toBe('Ana López trabaja hoy de 10:00 a 14:00 y de 16:00 a 20:00.');
    expect(s.tabs()).toEqual(['10:00 – 14:00 2 libres', '16:00 – 20:00 3 libres']);
    const off = await setup({ today: '2026-10-18' }, 'es');
    await off.result(OP, answer([], []));
    expect(off.find('appointment-slots-off').text()).toContain('Ana López no trabaja el lunes, 19 de octubre.');
  });
});
