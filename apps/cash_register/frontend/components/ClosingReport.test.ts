// The shift report on paper (CASH_REGISTER-F16): «Cash closing (Z)» for a closed session, «Partial report
// (X)» for an open one, with the session's number and the same figures as the screen.
import { describe, expect, it } from 'vitest';

import { mountCash, words } from '../__tests__/mount-cash-register';
import { SESSION } from './__tests__/session';
import ClosingReport from './ClosingReport.vue';

describe('ClosingReport', () => {
  it('a closed session prints its Z, with its number and figures', async () => {
    const m = await mountCash(ClosingReport, { props: { session: SESSION } });
    await m.live();
    const paper = words(m.find('cash-register-report').element);
    expect(m.find('cash-register-report-title').text()).toBe('Cash closing (Z)');
    expect(paper).toContain('S-261014-0001');
    expect(paper).toContain('Expected €100.00');
    expect(paper).toContain('Closing notes Short by 50 cents');
  });

  it('says the time it is printed at', async () => {
    const m = await mountCash(ClosingReport, { props: { session: SESSION, printedAt: new Date(2026, 9, 14, 21, 45) } });
    await m.live();
    expect(words(m.find('cash-register-report').element)).toMatch(/Printed Oct 14, 2026, 9:45\sPM/);
  });

  it('an open session prints a partial X report, in Spanish too', async () => {
    const m = await mountCash(ClosingReport, { props: { session: { ...SESSION, status: 'open' } }, locale: 'es' });
    await m.live();
    expect(m.find('cash-register-report-title').text()).toBe('Informe parcial (X)');
  });
});
