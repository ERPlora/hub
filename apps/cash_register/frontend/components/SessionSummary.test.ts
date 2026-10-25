// The summary of a session's detail (CASH_REGISTER-F11): its figures in two columns, label over value, in
// the reader's language.
import { describe, expect, it } from 'vitest';

import { business, mountCash, POLISH, words } from '../__tests__/mount-cash-register';
import { SESSION } from './__tests__/session';
import SessionSummary from './SessionSummary.vue';

describe('SessionSummary', () => {
  it('paints every figure, label over value', async () => {
    const m = await mountCash(SessionSummary, { props: { session: SESSION } });
    await m.live();
    const item = (key: string) => words(m.find(`cash-register-summary-${key}`).element);
    expect(item('register')).toBe('Drawer Bar');
    expect(item('cashSales')).toBe('Cash sales €3.00');
    expect(item('difference')).toBe('Difference -€0.50');
  });

  it('speaks Spanish', async () => {
    const m = await mountCash(SessionSummary, { props: { session: SESSION }, locale: 'es' });
    await m.live();
    expect(words(m.find('cash-register-summary-expected').element)).toBe('Esperado 100,00 €');
  });

  it('a business in Poland reads its drawer in zlotys (flow business-currency)', async () => {
    const m = await mountCash(SessionSummary, { props: { session: SESSION }, business: business(POLISH) });
    await m.live();
    expect(words(m.find('cash-register-summary-expected').element)).toBe('Expected zł 100.00');
  });

  it('while the business is not read, a figure has no symbol, never the euro', async () => {
    const m = await mountCash(SessionSummary, { props: { session: SESSION }, business: null });
    await m.live();
    expect(words(m.find('cash-register-summary-expected').element)).toBe('Expected 100.00');
  });
});
