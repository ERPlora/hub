// «Cash count · S-…» (CASH_REGISTER-F06): «Count type» («Closing» first, or «Opening»), «Notes», one box
// per note under «Bills» and per coin under «Coins» of the business's currency (labelled as money), and
// «Total counted» adding up as it is typed; without a table for the currency, the total typed by hand.
// «Register count» sends only the boxes counted (the server adds them up) and says «Count recorded ·
// total counted …»; a closing count tells the page, which opens the close with it.
import { toastSuccess } from '@erplora/ui/shell';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { click, ionValue, mountCash } from '../__tests__/mount-cash-register';
import { plain } from '../lib/money';
import CountModal from './CountModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});
vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...((await importOriginal()) as object),
  toastSuccess: vi.fn(() => Promise.resolve()),
}));
beforeEach(() => vi.mocked(toastSuccess).mockClear());

const prop = (el: Element | null, name: string): unknown => (el as unknown as Record<string, unknown>)[name];
const SESSION = { id: 's1', number: 'S-261014-0001' };
const CURRENCY = 'cash_register.currency.get';
const EUR = {
  currency: 'EUR',
  decimals: 2,
  bills: ['500', '200', '100', '50', '20', '10', '5'],
  coins: ['2', '1', '0.50', '0.20', '0.10', '0.05', '0.02', '0.01'],
};

async function setup(locale: 'en' | 'es' = 'en') {
  const m = await mountCash(CountModal, { props: { open: true, session: SESSION }, locale });
  await m.live();
  const submit = () => click(m.inDoc('cash-register-count-submit'));
  const box = (face: string) => m.inDoc(`cash-register-count-denom-${face}`);
  return { ...m, submit, box };
}

describe('CountModal', () => {
  it('waits for the currency, then paints a box per note and coin, labelled as money', async () => {
    const s = await setup('es');
    expect(s.inDoc('cash-register-count')?.getAttribute('aria-label')).toBe('Arqueo de caja · S-261014-0001');
    expect(s.inDoc('cash-register-count-loading')).not.toBeNull();
    await s.result(CURRENCY, EUR);
    expect(prop(s.inDoc('cash-register-count-type'), 'value')).toBe('closing');
    // A whole note or coin without decimals, as the old count printed it («500 €», not «500,00 €»).
    expect(plain(String(prop(s.box('50'), 'label')))).toBe('50 €');
    expect(plain(String(prop(s.box('0.05'), 'label')))).toBe('0,05 €');
    expect(s.inDoc('cash-register-count-bills')?.querySelectorAll('ion-input')).toHaveLength(7);
    expect(s.inDoc('cash-register-count-coins')?.querySelectorAll('ion-input')).toHaveLength(8);
  });

  it('adds the total up as it is typed and sends only the boxes counted', async () => {
    const s = await setup();
    await s.result(CURRENCY, EUR);
    await ionValue(s.box('50'), '2', 'ionInput');
    await ionValue(s.box('0.05'), '3', 'ionInput');
    await ionValue(s.box('10'), '', 'ionInput');
    expect(plain(s.inDoc('cash-register-count-total')?.textContent ?? '')).toContain('€100.15');
    await ionValue(s.inDoc('cash-register-count-notes'), ' evening ', 'ionInput');
    s.answer(201, { id: 'c1', type: 'closing', total: 10015 });
    await s.submit();
    expect(s.sent()).toEqual([
      {
        method: 'POST',
        path: '/api/cash_register/counts',
        query: {},
        body: { session_id: 's1', type: 'closing', denominations: { bills: { '50': 2 }, coins: { '0.05': 3 } }, notes: 'evening' },
      },
    ]);
    expect(plain(vi.mocked(toastSuccess).mock.calls[0][0])).toBe('Count recorded · total counted €100.15');
    expect(s.wrapper.emitted('counted')).toEqual([[{ type: 'closing', total: 10015 }]]);
    expect(s.wrapper.emitted('update:open')).toEqual([[false]]);
  });

  it('an opening count is sent as such', async () => {
    const s = await setup();
    await s.result(CURRENCY, EUR);
    await ionValue(s.inDoc('cash-register-count-type'), 'opening');
    await ionValue(s.box('100'), '1', 'ionInput');
    s.answer(201, { id: 'c1', type: 'opening', total: 10000 });
    await s.submit();
    expect((s.sent()[0].body as { type: string }).type).toBe('opening');
    expect(s.wrapper.emitted('counted')).toEqual([[{ type: 'opening', total: 10000 }]]);
  });

  it('without a table for the currency it asks the total, and only a readable one is sent', async () => {
    const s = await setup();
    await s.result(CURRENCY, { currency: 'ARS', decimals: 2, bills: [], coins: [] });
    expect(s.inDoc('cash-register-count-no-breakdown')?.textContent).toContain('There is no breakdown of notes and coins for ARS');
    expect(prop(s.inDoc('cash-register-count-submit'), 'disabled')).toBe(true);
    await ionValue(s.inDoc('cash-register-count-total-input'), '1.250', 'ionInput');
    expect(prop(s.inDoc('cash-register-count-total-input'), 'errorText')).toContain('can be read two ways');
    await ionValue(s.inDoc('cash-register-count-total-input'), '1250,40', 'ionInput');
    s.answer(201, { id: 'c1', type: 'closing', total: 125040 });
    await s.submit();
    expect(s.sent()[0].body).toEqual({ session_id: 's1', type: 'closing', total: 125040, notes: '' });
  });

  it('a currency without cents counts and labels in whole yen', async () => {
    const s = await setup();
    await s.result(CURRENCY, { currency: 'JPY', decimals: 0, bills: ['10000', '5000', '2000', '1000'], coins: ['500', '100', '50', '10', '5', '1'] });
    expect(plain(String(prop(s.box('1000'), 'label')))).toBe('¥1,000');
    await ionValue(s.box('1000'), '5', 'ionInput');
    await ionValue(s.box('1'), '3', 'ionInput');
    expect(plain(s.inDoc('cash-register-count-total')?.textContent ?? '')).toContain('¥5,003');
  });

  it('the server’s refusal is read in the window', async () => {
    const s = await setup();
    await s.result(CURRENCY, EUR);
    s.answer(409, { error: { code: 'cash_register.session_not_open', message: 'That cash session is closed: a closed session takes no new movements.' } });
    await s.submit();
    expect(s.inDoc('cash-register-count-error')?.textContent).toContain('That cash session is closed');
    expect(s.wrapper.emitted('counted')).toBeUndefined();
  });
});
