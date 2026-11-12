// «Cash movement · S-…» (CASH_REGISTER-F05): «Type» (Cash in or Cash out), «Amount» always positive (the
// type gives the sign, the server keeps it), «Concept», «Register» / «Cancel». An amount that is zero or
// cannot be read is said under the field and nothing is sent; the server's refusal (a cash-out below
// zero, the session closed elsewhere) is read in the window; success says «Cash-out recorded (…)».
import { toastSuccess } from '@erplora/ui/shell';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { click, expectWaitsForTheYen, ionValue, mountCash } from '../__tests__/mount-cash-register';
import { itReadsAmountsAsTheHub, itReadsWhatWasLeftOnceTheMoneyArrives } from '../__tests__/money-field';
import { expectWindowSaysMoneyUnreadable } from '../../../../base/frontend/__tests__/save-waits-for-money';
import { plain } from '../lib/money';
import type { Business } from '../../../../base/frontend/operations';
import MovementModal from './MovementModal.vue';

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

async function setup(locale: 'en' | 'es' = 'en') {
  const m = await mountCash(MovementModal, { props: { open: true, session: SESSION }, locale });
  await m.live();
  const submit = () => click(m.inDoc('cash-register-movement-submit'));
  return { ...m, submit };
}

describe('MovementModal', () => {
  it('is «Cash movement · <number>» with the type (cash in first), the amount and the concept', async () => {
    const s = await setup();
    expect(s.inDoc('cash-register-movement')?.getAttribute('aria-label')).toBe('Cash movement · S-261014-0001');
    expect(prop(s.inDoc('cash-register-movement-type'), 'value')).toBe('in');
    expect([prop(s.inDoc('cash-register-movement-amount'), 'label'), prop(s.inDoc('cash-register-movement-concept'), 'label')]).toEqual([
      'Amount',
      'Concept',
    ]);
    expect(s.inDoc('cash-register-movement-submit')?.textContent?.trim()).toBe('Register');
  });

  it('records a cash-out of the session with its positive amount and says so', async () => {
    const s = await setup();
    await ionValue(s.inDoc('cash-register-movement-type'), 'out');
    await ionValue(s.inDoc('cash-register-movement-amount'), '20', 'ionInput');
    await ionValue(s.inDoc('cash-register-movement-concept'), ' Bread supplier ', 'ionInput');
    s.answer(201, { key: 'm1', type: 'out', amount: 2000 });
    await s.submit();
    expect(s.sent()).toEqual([
      {
        method: 'POST',
        path: '/api/cash_register/movements',
        query: {},
        body: { session_id: 's1', type: 'out', amount: 2000, description: 'Bread supplier' },
      },
    ]);
    expect(plain(vi.mocked(toastSuccess).mock.calls[0][0])).toBe('Cash-out recorded (€20.00)');
    expect(s.wrapper.emitted('update:open')).toEqual([[false]]);
  });

  it('a zero, empty or unreadable amount is said under the field and nothing is sent', async () => {
    const s = await setup();
    await s.submit();
    expect(prop(s.inDoc('cash-register-movement-amount'), 'errorText')).toBe('Invalid amount');
    await ionValue(s.inDoc('cash-register-movement-amount'), '-5', 'ionInput');
    await s.submit();
    expect(prop(s.inDoc('cash-register-movement-amount'), 'errorText')).toContain('cannot be negative');
    expect(s.sent()).toEqual([]);
  });

  it('the server’s refusal is read in the window, which stays open', async () => {
    const s = await setup();
    await ionValue(s.inDoc('cash-register-movement-type'), 'out');
    await ionValue(s.inDoc('cash-register-movement-amount'), '999', 'ionInput');
    s.answer(409, {
      error: { code: 'cash_register.negative_balance_not_allowed', message: 'This cash-out would leave the drawer below zero and a negative balance is not allowed.' },
    });
    await s.submit();
    expect(s.inDoc('cash-register-movement-error')?.textContent).toContain('below zero');
    expect(s.wrapper.emitted('update:open')).toBeUndefined();
  });

  it('speaks Spanish', async () => {
    const s = await setup('es');
    expect(s.inDoc('cash-register-movement')?.getAttribute('aria-label')).toBe('Movimiento de caja · S-261014-0001');
    expect(s.inDoc('cash-register-movement-submit')?.textContent?.trim()).toBe('Registrar');
    await ionValue(s.inDoc('cash-register-movement-amount'), '12,5', 'ionInput');
    s.answer(201, { key: 'm1' });
    await s.submit();
    expect(plain(vi.mocked(toastSuccess).mock.calls[0][0])).toBe('Movimiento de entrada registrado (12,50 €)');
  });
});

describe('MovementModal: before the business answers its money (hub#921)', () => {
  it('«Register» waits in grey and reads no amount; once the yen arrives «1500» is 1500', async () => {
    const m = await mountCash(MovementModal, { props: { open: true, session: SESSION }, business: null });
    await m.live();
    await ionValue(m.inDoc('cash-register-movement-amount'), '1500', 'ionInput');
    await ionValue(m.inDoc('cash-register-movement-concept'), 'Change', 'ionInput');
    m.answer(201, { key: 'm1', type: 'in', amount: 1500 });
    await expectWaitsForTheYen(m, 'cash-register-movement-submit', 'cash-register-movement-amount');
    await click(m.inDoc('cash-register-movement-submit'));
    expect(m.sent().map((call) => call.body)).toEqual([{ session_id: 's1', type: 'in', amount: 1500, description: 'Change' }]);
    expect(plain(vi.mocked(toastSuccess).mock.calls[0][0])).toBe('Cash-in recorded (¥1,500)');
  });
});

describe('MovementModal: a business whose money cannot be read (hub#938)', () => {
  it('says so with «Retry» instead of waiting in grey without a word; once the yen arrives «Register» lights up', async () => {
    const m = await mountCash(MovementModal, { props: { open: true, session: SESSION }, business: null });
    await m.live();
    await ionValue(m.inDoc('cash-register-movement-amount'), '1500', 'ionInput');
    await ionValue(m.inDoc('cash-register-movement-concept'), 'Bread', 'ionInput');
    await expectWindowSaysMoneyUnreadable(m, 'cash-register-movement-submit', m.sent);
  });
});

describe('MovementModal: unsaved changes ask before closing (hub#1031, hub#1234, BASE-F05)', () => {
  it('a typed concept: Back, «Cancel», the «×», Escape and a tap outside ask «Discard changes?»; restored, Back closes', async () => {
    const s = await setup();
    const { expectUnsavedFormAsksBeforeClosing } = await import('../../../../base/frontend/__tests__/unsaved-form');
    await expectUnsavedFormAsksBeforeClosing({
      overlay: () => s.inDoc('cash-register-movement'),
      change: () => ionValue(s.inDoc('cash-register-movement-concept'), 'Change for the till', 'ionInput'),
      restore: () => ionValue(s.inDoc('cash-register-movement-concept'), '', 'ionInput'),
    });
  });
  it('as opened, «Cancel», the «×», Escape and a tap outside close it without asking', async () => {
    const { expectUntouchedWindowClosesAtOnce } = await import('../../../../base/frontend/__tests__/unsaved-form');
    await expectUntouchedWindowClosesAtOnce(await setup(), 'cash-register-movement');
  });
});

describe('MovementModal: the amount, read as every amount of the Hub', () => {
  const window = {
    open: async (business?: Business | null) => {
      const m = await mountCash(MovementModal, { props: { open: true, session: SESSION }, business });
      await m.live();
      return m;
    },
    field: 'cash-register-movement-amount',
    submit: 'cash-register-movement-submit',
    amount: (body: Record<string, unknown>) => body.amount,
  };
  itReadsAmountsAsTheHub(window);
  itReadsWhatWasLeftOnceTheMoneyArrives(window);
});
