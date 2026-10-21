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
    expect(m.find('series-form-scope').text()).toContain('El cambio se aplica desde el lunes, 2 de noviembre de 2026: alcanza 5 citas reservadas; 1 ya cobradas no se tocarán.');
  });

  it('says only what happens: without charged appointments there is no «0 already charged» (appointments#293)', async () => {
    const m = await mountAppointment(SeriesScopeHint, { props: { seriesId: 'r1', fromDate: '2026-11-02' } });
    await m.live();
    await m.result('appointment.recurring.get', { id: 'r1', upcoming: 3, charged: 0 });
    const said = m.find('series-form-scope').text();
    expect(said).toContain('The change applies from Monday, November 2, 2026: it reaches 3 booked appointments.');
    expect(said).not.toContain('charged');
  });
});
