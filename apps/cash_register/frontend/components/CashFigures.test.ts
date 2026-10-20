// The figures of the drawer on Cash register's own screen (CASH_REGISTER-F12; the old Home's «Cash register
// (current session)» and «Recent discrepancies» panels, inside the app as Sales' figures are): the expected
// cash of the open session (empty when a blind count hides it), and the difference of the last eight closed
// sessions, newest close first, with a bar as long as the difference and coloured by its sign. Money in the
// business's currency with its cents; loading, empty and error said.
import { describe, expect, it } from 'vitest';

import { click, errorFrame, flush, mountCash, words } from '../__tests__/mount-cash-register';
import { plain } from '../lib/money';
import CashFigures from './CashFigures.vue';

const CURRENT = 'cash_register.session.current';
const LIST = 'cash_register.session.list';
const CURRENCY = 'cash_register.currency.get';

const open = (expected: number | null, hidden = false) => ({
  required: true,
  session: { id: 's9', number: 'S-261020-0003', status: 'open', expected_balance: expected, expected_hidden: hidden, auto_close_due: false },
  auto_close_at: null,
  unassigned_count: 0,
  unassigned_cash: 0,
});
const none = { required: true, session: null, auto_close_at: null, unassigned_count: 0, unassigned_cash: 0 };
const closed = (number: string, difference: number | null) => ({ id: number, number, status: 'closed', difference });
const page = (rows: unknown[]) => ({ rows, total: rows.length, limit: 8, offset: 0 });
const currency = (code = 'EUR', decimals = 2) => ({ currency: code, decimals, bills: [], coins: [] });

async function setup(locale: 'en' | 'es' = 'en') {
  const m = await mountCash(CashFigures, { locale });
  await m.live();
  const text = (testid: string) => plain(words(m.find(testid).element));
  return { ...m, text };
}

describe('CashFigures', () => {
  it('reads the open session, the last eight closed by their close and the currency of the business (cash_register#119)', async () => {
    const m = await setup();
    expect(m.params(CURRENT)).toEqual([{}]);
    expect(m.params(LIST)).toEqual([{ status: 'closed', sort: 'closed_at', dir: 'desc', limit: 8 }]);
    expect(m.params(CURRENCY)).toEqual([{}]);
    expect(m.find('cash-register-figures-loading').exists()).toBe(true);
  });

  it('shows the expected cash of the open session with its cents', async () => {
    const m = await setup();
    await m.result(CURRENCY, currency());
    await m.result(CURRENT, open(18405));
    await m.result(LIST, page([]));
    expect(m.text('cash-register-figures-current')).toContain('Current session');
    expect(m.text('cash-register-figures-current')).toContain('S-261020-0003');
    expect(m.text('cash-register-figures-expected')).toBe('€184.05');
  });

  it('a blind count leaves the expected empty, and no open session is said', async () => {
    const m = await setup();
    await m.result(CURRENCY, currency());
    await m.result(CURRENT, open(null, true));
    await m.result(LIST, page([]));
    expect(m.text('cash-register-figures-expected')).toBe('—');
    await m.result(CURRENT, none, {}, 2);
    expect(m.text('cash-register-figures-current')).toContain('No open session');
    expect(m.find('cash-register-figures-expected').exists()).toBe(false);
  });

  it('lists the recent discrepancies with their cents and a bar for each sign (outfitkit#243, #244)', async () => {
    const m = await setup();
    await m.result(CURRENCY, currency());
    await m.result(CURRENT, none);
    await m.result(LIST, page([closed('S-261020-0002', -40), closed('S-261019-0001', 500), closed('S-261018-0001', 0), closed('S-261017-0001', null)]));
    const rows = m.wrapper.findAll('[data-testid="cash-register-figures-recent-row"]');
    expect(rows.map((row) => plain(words(row.element)))).toEqual([
      'S-261020-0002 -€0.40',
      'S-261019-0001 +€5.00',
      'S-261018-0001 €0.00',
      'S-261017-0001 —',
    ]);
    const bars = m.wrapper.findAll('[data-testid="cash-register-figures-bar"]');
    expect(bars.map((bar) => [bar.classes('is-short'), bar.classes('is-over'), (bar.element as HTMLElement).style.width])).toEqual([
      [true, false, '8%'],
      [false, true, '100%'],
      [false, false, '0%'],
      [false, false, '0%'],
    ]);
  });

  it('a short drawer alone still shows its bar', async () => {
    const m = await setup();
    await m.result(CURRENCY, currency());
    await m.result(CURRENT, none);
    await m.result(LIST, page([closed('S-261020-0002', -40)]));
    expect((m.find('cash-register-figures-bar').element as HTMLElement).style.width).toBe('100%');
  });

  it('money goes in the currency of the business (cash_register#121, hub#2387)', async () => {
    const m = await setup();
    await m.result(CURRENCY, currency('USD'));
    await m.result(CURRENT, open(12550));
    await m.result(LIST, page([closed('S-261020-0002', -125)]));
    expect(m.text('cash-register-figures-expected')).toBe('$125.50');
    expect(m.text('cash-register-figures-recent')).toContain('-$1.25');
  });

  it('without closed sessions it says so', async () => {
    const m = await setup();
    await m.result(CURRENCY, currency());
    await m.result(CURRENT, none);
    await m.result(LIST, page([]));
    expect(m.text('cash-register-figures-recent')).toContain('No closed sessions yet.');
  });

  it('a failed reading is said with a retry', async () => {
    const m = await setup();
    await m.result(CURRENCY, currency());
    await m.result(CURRENT, none);
    m.net.lastStream().push(errorFrame(m.subId(LIST), 'internal_error'));
    await flush();
    expect(m.text('cash-register-figures-error')).toContain('The cash figures could not be loaded.');
    await click(m.inDoc('cash-register-figures-retry'));
    expect(m.find('cash-register-figures-error').exists()).toBe(true);
  });

  it('speaks Spanish (cash_register#123)', async () => {
    const m = await setup('es');
    await m.result(CURRENCY, currency());
    await m.result(CURRENT, open(18405));
    await m.result(LIST, page([closed('S-261020-0002', -40)]));
    expect(m.text('cash-register-figures-current')).toContain('Sesión actual');
    expect(m.text('cash-register-figures-current')).toContain('Esperado en el cajón');
    expect(m.text('cash-register-figures-expected')).toBe('184,05 €');
    expect(m.text('cash-register-figures-recent')).toContain('Descuadres recientes');
    expect(m.text('cash-register-figures-recent')).toContain('-0,40 €');
  });
});
