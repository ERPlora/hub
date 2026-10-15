// The body of «Close session · S-…» (CASH_REGISTER-F07, F08, F09): the shift review, «Expected in the
// drawer» and «Difference» while typing (only when the server shows the expected to this person), «Counted
// cash» (from the session's last closing count, never an opening one), «Closing notes», «Close session».
// Empty counted cash is asked for; with open checks the first press warns and the second closes («Close
// anyway»). Success says «Session S-… closed · expected … · counted … · difference …».
import { toastSuccess } from '@erplora/ui/shell';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { click, errorFrame, flush, ionValue, mountCash } from '../__tests__/mount-cash-register';
import { plain } from '../lib/money';
import CloseSessionForm from './CloseSessionForm.vue';

vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...((await importOriginal()) as object),
  toastSuccess: vi.fn(() => Promise.resolve()),
}));
beforeEach(() => vi.mocked(toastSuccess).mockClear());

const prop = (el: Element | null, name: string): unknown => (el as unknown as Record<string, unknown>)[name];
const SESSION = { id: 's1', number: 'S-261014-0001' };
const DETAIL = 'cash_register.session.get';
const COUNTS = 'cash_register.count.list';
const CHECKS = 'sale.order.list';

const detail = (expected: number | null) => ({ id: 's1', number: 'S-261014-0001', status: 'open', summary: { expected_cash: expected } });
const counts = (rows: unknown[]) => ({ rows, total: rows.length, limit: 20, offset: 0 });
const checks = (rows: unknown[]) => ({ rows, total: rows.length, limit: 20, offset: 0 });

async function setup(locale: 'en' | 'es' = 'en') {
  const m = await mountCash(CloseSessionForm, { props: { session: SESSION }, locale });
  await m.live();
  const counted = () => m.inDoc('cash-register-close-counted');
  const submit = () => click(m.inDoc('cash-register-close-submit'));
  const ready = async (expected: number | null = 10150, countRows: unknown[] = [], checkRows: unknown[] = []) => {
    await m.result(DETAIL, detail(expected));
    await m.result(COUNTS, counts(countRows));
    await m.result(CHECKS, checks(checkRows));
  };
  return { ...m, counted, submit, ready };
}

describe('CloseSessionForm', () => {
  it('reads the session, its counts and the open checks of Sales', async () => {
    const s = await setup();
    expect(s.params(DETAIL)).toEqual([{ session_id: 's1' }]);
    expect(s.params(COUNTS)).toEqual([{ session_id: 's1', limit: 20 }]);
    expect(s.params(CHECKS)).toEqual([{ status: 'open', limit: 20 }]);
    expect(s.find('cash-register-review-checking').exists()).toBe(true);
  });

  it('starts from the last closing count, never an opening one, and shows expected and difference live', async () => {
    const s = await setup();
    await s.ready(10150, [
      { id: 'c2', type: 'opening', total: 99999 },
      { id: 'c1', type: 'closing', total: 10100 },
    ]);
    expect(prop(s.counted(), 'value')).toBe('101.00');
    const figures = () => plain(s.find('cash-register-close-expected').text());
    expect(figures()).toContain('Expected in the drawer');
    expect(figures()).toContain('€101.50');
    expect(figures()).toContain('-€0.50');
    await ionValue(s.counted(), '102', 'ionInput');
    expect(figures()).toContain('+€0.50');
  });

  it('a blind count shows neither the expected nor the difference', async () => {
    const s = await setup();
    await s.ready(null);
    expect(s.find('cash-register-close-expected').exists()).toBe(false);
  });

  it('asks for the counted cash and sends nothing without it', async () => {
    const s = await setup();
    await s.ready();
    await s.submit();
    expect(prop(s.counted(), 'errorText')).toBe('Type the counted cash to close the session.');
    expect(s.sent()).toEqual([]);
  });

  it('closes with the counted cash in cents and the notes, and says the three figures', async () => {
    const s = await setup();
    await s.ready();
    await ionValue(s.counted(), '101', 'ionInput');
    await ionValue(s.inDoc('cash-register-close-notes'), ' short ', 'ionInput');
    s.answer(200, { id: 's1', number: 'S-261014-0001', status: 'closed', expected_balance: 10150, closing_balance: 10100, difference: -50 });
    await s.submit();
    expect(s.sent()).toEqual([
      {
        method: 'POST',
        path: '/api/cash_register/sessions/close',
        query: {},
        body: { session_id: 's1', closing_balance: 10100, closing_notes: 'short' },
      },
    ]);
    expect(plain(vi.mocked(toastSuccess).mock.calls[0][0])).toBe('Session S-261014-0001 closed · expected €101.50 · counted €101.00 · difference -€0.50');
    expect(s.wrapper.emitted('closed')).toHaveLength(1);
  });

  it('with open checks the first press warns and the second closes anyway', async () => {
    const s = await setup();
    await s.ready(10150, [], [{ id: 'o1', label: 'Table 4' }]);
    expect(s.find('cash-register-review').text()).toContain('Table 4');
    await ionValue(s.counted(), '101,50', 'ionInput');
    await s.submit();
    expect(s.sent()).toEqual([]);
    expect(s.find('cash-register-review-confirm').exists()).toBe(true);
    expect(s.inDoc('cash-register-close-submit')?.textContent?.trim()).toBe('Close anyway');
    s.answer(200, { id: 's1', number: 'S-261014-0001', status: 'closed', expected_balance: 10150, closing_balance: 10150, difference: 0 });
    await s.submit();
    expect(s.sent()).toHaveLength(1);
  });

  it('a review that could not be read is said and does not ask for a second press', async () => {
    const s = await setup();
    await s.result(DETAIL, detail(10150));
    s.net.lastStream().push(errorFrame(s.subId(CHECKS), 'permission_denied'));
    await flush();
    expect(s.find('cash-register-review-unavailable').exists()).toBe(true);
    await ionValue(s.counted(), '101,50', 'ionInput');
    s.answer(200, { id: 's1', number: 'S-261014-0001', status: 'closed', expected_balance: 10150, closing_balance: 10150, difference: 0 });
    await s.submit();
    expect(s.sent()).toHaveLength(1);
  });

  it('the server’s refusal is read above the buttons', async () => {
    const s = await setup();
    await s.ready();
    await ionValue(s.counted(), '1', 'ionInput');
    s.answer(409, { error: { code: 'cash_register.session_not_open', message: 'That cash session is closed: a closed session takes no new movements.' } });
    await s.submit();
    expect(s.find('cash-register-close-error').text()).toContain('That cash session is closed');
    expect(s.wrapper.emitted('closed')).toBeUndefined();
  });

  it('speaks Spanish', async () => {
    const s = await setup('es');
    await s.ready();
    expect(prop(s.counted(), 'label')).toBe('Efectivo contado');
    expect(s.inDoc('cash-register-close-submit')?.textContent?.trim()).toBe('Cerrar sesión');
    expect(plain(s.find('cash-register-close-expected').text())).toContain('101,50 €');
  });
});
