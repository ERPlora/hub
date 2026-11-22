// APPOINTMENT-F14: editing a series from a date says what the change reaches: its booked appointments
// from that date on, and the charged ones it leaves alone. Live: it follows the date picked.
import { describe, expect, it } from 'vitest';

import { mountAppointment } from '../__tests__/mount-appointment';
import SeriesScopeHint from './SeriesScopeHint.vue';

describe('SeriesScopeHint', () => {
  it('asks the series from the date and says what the change reaches', async () => {
    const m = await mountAppointment(SeriesScopeHint, { props: { seriesId: 'r1', fromDate: '2026-11-02' }, locale: 'es' });
    await m.live();
    expect(m.params('appointment.recurring.get')).toEqual([{ id: 'r1', from_date: '2026-11-02' }]);
    expect(m.find('series-form-scope').exists()).toBe(false);
    await m.result('appointment.recurring.get', { id: 'r1', upcoming: 5, charged: 1 });
    expect(m.find('series-form-scope').text()).toContain('El cambio se aplica desde el lunes, 2 de noviembre de 2026: alcanza 5 citas reservadas; 1 ya cobrada no se tocará.');
  });

  it('says only what happens: without charged appointments there is no «0 already charged»', async () => {
    const m = await mountAppointment(SeriesScopeHint, { props: { seriesId: 'r1', fromDate: '2026-11-02' } });
    await m.live();
    await m.result('appointment.recurring.get', { id: 'r1', upcoming: 3, charged: 0 });
    const said = m.find('series-form-scope').text();
    expect(said).toContain('The change applies from Monday, November 2, 2026: it reaches 3 booked appointments.');
    expect(said).not.toContain('charged');
  });

  // hub#2063: each count with its own singular or plural, «1 cita reservada», never «1 citas reservadas».
  it('says one appointment in the singular', async () => {
    const m = await mountAppointment(SeriesScopeHint, { props: { seriesId: 'r1', fromDate: '2026-11-02' }, locale: 'es' });
    await m.live();
    await m.result('appointment.recurring.get', { id: 'r1', upcoming: 1, charged: 0 });
    expect(m.find('series-form-scope').text()).toContain('alcanza 1 cita reservada. Lo que ya ha pasado');
    await m.result('appointment.recurring.get', { id: 'r1', upcoming: 3, charged: 2 });
    expect(m.find('series-form-scope').text()).toContain('alcanza 3 citas reservadas; 2 ya cobradas no se tocarán.');
    const english = await mountAppointment(SeriesScopeHint, { props: { seriesId: 'r1', fromDate: '2026-11-02' } });
    await english.live();
    await english.result('appointment.recurring.get', { id: 'r1', upcoming: 1, charged: 1 });
    expect(english.find('series-form-scope').text()).toContain('it reaches 1 booked appointment; 1 already charged will not be touched.');
  });
});
