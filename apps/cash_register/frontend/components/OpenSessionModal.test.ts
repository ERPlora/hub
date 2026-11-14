// «Open cash session» (CASH_REGISTER-F03): «Drawer» (only when the business has drawers; the only one is
// chosen alone), «Opening float» as it is read («150,50»; empty is 0), «Notes», «Open session» / «Cancel».
// An amount that cannot be read is said under the field and nothing is sent; the server's refusal (one
// already open, a float required) is read in the window, at its field; success says «Session opened».
import { toastSuccess } from '@erplora/ui/shell';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { itTellsTheCorrectedFieldApart } from '../../../../base/frontend/__tests__/same-words-refusal';
import { click, expectWaitsForTheYen, ionValue, mountCash, settle } from '../__tests__/mount-cash-register';
import { itReadsAmountsAsTheHub, itReadsWhatWasLeftOnceTheMoneyArrives } from '../__tests__/money-field';
import { expectWindowSaysMoneyUnreadable } from '../../../../base/frontend/__tests__/save-waits-for-money';
import type { Business } from '../../../../base/frontend/operations';
import OpenSessionModal from './OpenSessionModal.vue';

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
const REGISTERS = 'cash_register.register.list';
const page = (rows: unknown[]) => ({ rows, total: rows.length, limit: 100, offset: 0 });

async function setup(options: { locale?: 'en' | 'es'; unassignedCash?: number } = {}) {
  const m = await mountCash(OpenSessionModal, {
    props: { open: true, unassignedCash: options.unassignedCash ?? 0 },
    locale: options.locale,
  });
  await m.live();
  const submit = () => click(m.inDoc('cash-register-open-submit'));
  return { ...m, submit };
}

describe('OpenSessionModal', () => {
  it('asks the active drawers and, with only one, chooses it alone', async () => {
    const s = await setup();
    expect(s.inDoc('cash-register-open')?.getAttribute('aria-label')).toBe('Open cash session');
    expect(s.params(REGISTERS)).toEqual([{ is_active: true, limit: 100 }]);
    expect(s.inDoc('cash-register-open-register')).toBeNull();
    await s.result(REGISTERS, page([{ id: 'r1', name: 'Bar', is_active: true }]));
    expect(prop(s.inDoc('cash-register-open-register'), 'value')).toBe('r1');
    expect(prop(s.inDoc('cash-register-open-balance'), 'label')).toBe('Opening float');
    expect([s.inDoc('cash-register-open-submit')?.textContent?.trim(), s.inDoc('cash-register-open-cancel')?.textContent?.trim()]).toEqual([
      'Open session',
      'Cancel',
    ]);
  });

  it('opens with the float in cents, the drawer and the notes, says «Session opened» and closes', async () => {
    const s = await setup();
    await s.result(REGISTERS, page([{ id: 'r1', name: 'Bar', is_active: true }, { id: 'r2', name: 'Terrace', is_active: true }]));
    expect(prop(s.inDoc('cash-register-open-register'), 'value')).toBe('');
    await ionValue(s.inDoc('cash-register-open-register'), 'r2');
    await ionValue(s.inDoc('cash-register-open-balance'), '150,50', 'ionInput');
    await ionValue(s.inDoc('cash-register-open-notes'), '  Morning ', 'ionInput');
    s.answer(201, { id: 's1', number: 'S-261014-0001', status: 'open' });
    await s.submit();
    expect(s.sent()).toEqual([
      {
        method: 'POST',
        path: '/api/cash_register/sessions/open',
        query: {},
        body: { register_id: 'r2', opening_balance: 15050, opening_notes: 'Morning' },
      },
    ]);
    expect(toastSuccess).toHaveBeenCalledWith('Session opened');
    expect(s.wrapper.emitted('update:open')).toEqual([[false]]);
  });

  it('an empty float opens at 0 without a drawer', async () => {
    const s = await setup();
    await s.result(REGISTERS, page([]));
    s.answer(201, { id: 's1' });
    await s.submit();
    expect(s.sent()[0].body).toEqual({ opening_notes: '' });
  });

  it('an amount that cannot be read is said under the field and nothing is sent', async () => {
    const s = await setup();
    await ionValue(s.inDoc('cash-register-open-balance'), 'abc', 'ionInput');
    await s.submit();
    expect(s.sent()).toEqual([]);
    expect(prop(s.inDoc('cash-register-open-balance'), 'errorText')).toBe('This is not an amount. Type a figure, for example 12.50.');
  });

  it('the server’s refusal is read in the window and at its field', async () => {
    const s = await setup();
    s.answer(409, {
      error: {
        code: 'cash_register.opening_balance_required',
        message: 'This business requires an opening float: give the cash the drawer starts with.',
        fields: { opening_balance: 'This business requires an opening float: give the cash the drawer starts with.' },
      },
    });
    await s.submit();
    expect(s.inDoc('cash-register-open-error')?.textContent).toContain('This business requires an opening float');
    expect(prop(s.inDoc('cash-register-open-balance'), 'errorText')).toContain('This business requires an opening float');
    expect(s.wrapper.emitted('update:open')).toBeUndefined();
  });

  it('reminds the cash charged with the drawer closed, to count it in the float', async () => {
    const s = await setup({ unassignedCash: 300 });
    expect(s.inDoc('cash-register-open-unassigned')?.textContent?.replace(/\s/g, ' ')).toContain('€3.00 were charged in cash with the drawer closed');
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    expect(s.inDoc('cash-register-open')?.getAttribute('aria-label')).toBe('Abrir sesión de caja');
    expect(prop(s.inDoc('cash-register-open-balance'), 'label')).toBe('Fondo de apertura');
    expect(s.inDoc('cash-register-open-submit')?.textContent?.trim()).toBe('Abrir sesión');
  });
});

describe('OpenSessionModal: a refused field, corrected, loses its mark without saving again (hub#1470)', () => {
  const REQUIRED = 'This business requires an opening float: give the cash the drawer starts with.';

  it('the float the business requires: typing one takes its mark and the notice away, before «Open session» is pressed again', async () => {
    const s = await setup();
    s.answer(409, { error: { code: 'cash_register.opening_balance_required', message: REQUIRED, fields: { opening_balance: REQUIRED } } });
    await s.submit();
    const balance = () => s.inDoc('cash-register-open-balance');
    expect(prop(balance(), 'errorText')).toBe(REQUIRED);
    balance()?.dispatchEvent(new Event('input', { bubbles: true }));
    await ionValue(balance(), '100', 'ionInput');
    expect(prop(balance(), 'errorText') ?? '').toBe('');
    expect(s.inDoc('cash-register-open-error')).toBeNull();
    expect(s.sent()).toHaveLength(1);
  });

  const FIELD: Record<string, string> = { register_id: 'register', opening_balance: 'balance', opening_notes: 'notes' };

  it('the drawer and the notes the server refuses are marked as Ionic shows a refusal, and only they', async () => {
    const s = await setup();
    await s.result(REGISTERS, page([{ id: 'r1', name: 'Bar', is_active: true }, { id: 'r2', name: 'Terrace', is_active: true }]));
    const marked = (key: string) => {
      const field = s.inDoc(`cash-register-open-${FIELD[key]}`);
      return ['ion-invalid', 'ion-touched'].map((mark) => field?.classList.contains(mark));
    };
    s.answer(422, {
      error: { code: 'invalid_payload', message: 'Check the highlighted details.', fields: { register_id: 'Not this drawer.', opening_notes: 'Too long.' } },
    });
    await s.submit();
    expect(marked('register_id')).toEqual([true, true]);
    expect(marked('opening_notes')).toEqual([true, true]);
    s.inDoc('cash-register-open-notes')?.dispatchEvent(new Event('input', { bubbles: true }));
    await ionValue(s.inDoc('cash-register-open-notes'), 'Morning', 'ionInput');
    expect(marked('opening_notes')).toEqual([false, false]);
    expect(marked('register_id')).toEqual([true, true]);
  });

  itTellsTheCorrectedFieldApart(
    ['register_id', 'opening_balance', 'opening_notes'],
    async (locale, refusal) => {
      const s = await setup({ locale });
      await s.result(REGISTERS, page([{ id: 'r1', name: 'Bar', is_active: true }, { id: 'r2', name: 'Terrace', is_active: true }]));
      await ionValue(s.inDoc('cash-register-open-register'), 'r2');
      await ionValue(s.inDoc('cash-register-open-balance'), '10', 'ionInput');
      await ionValue(s.inDoc('cash-register-open-notes'), 'Morning', 'ionInput');
      s.answer(422, refusal);
      return { field: (key) => s.inDoc(`cash-register-open-${FIELD[key]}`), send: s.submit, settle };
    },
    'opening_balance',
  );
});

/** The window open with no drawer and «1500» typed as the float, `base.business.get` not answered (hub#921). */
async function floatTypedBeforeTheMoney() {
  const m = await mountCash(OpenSessionModal, { props: { open: true }, business: null });
  await m.live();
  await m.result(REGISTERS, page([]));
  await ionValue(m.inDoc('cash-register-open-balance'), '1500', 'ionInput');
  return m;
}

describe('OpenSessionModal: before the business answers its money (hub#921)', () => {
  it('«Open session» waits in grey and reads no float; once the yen arrives «1500» is 1500', async () => {
    const m = await floatTypedBeforeTheMoney();
    m.answer(201, { id: 's1', number: 'S-261014-0001', status: 'open' });
    await expectWaitsForTheYen(m, 'cash-register-open-submit', 'cash-register-open-balance');
    await click(m.inDoc('cash-register-open-submit'));
    expect(m.sent().map((call) => call.body)).toEqual([{ opening_balance: 1500, opening_notes: '' }]);
  });
});

describe('OpenSessionModal: a business whose money cannot be read (hub#938)', () => {
  it('says so with «Retry» instead of waiting in grey without a word; once the yen arrives «Open session» lights up', async () => {
    const m = await floatTypedBeforeTheMoney();
    await expectWindowSaysMoneyUnreadable(m, 'cash-register-open-submit', m.sent);
  });
});

describe('OpenSessionModal: unsaved changes ask before closing (hub#1031, hub#1234, BASE-F05)', () => {
  it('a typed float: Back, «Cancel», the «×», Escape and a tap outside ask «Discard changes?»; restored, Back closes', async () => {
    const s = await setup();
    await s.result(REGISTERS, page([{ id: 'r1', name: 'Bar', is_active: true }]));
    expect(prop(s.inDoc('cash-register-open-register'), 'value')).toBe('r1');
    const { expectUnsavedFormAsksBeforeClosing } = await import('../../../../base/frontend/__tests__/unsaved-form');
    await expectUnsavedFormAsksBeforeClosing({
      overlay: () => s.inDoc('cash-register-open'),
      change: () => ionValue(s.inDoc('cash-register-open-balance'), '150,50', 'ionInput'),
      restore: () => ionValue(s.inDoc('cash-register-open-balance'), '', 'ionInput'),
    });
  });

  it('as opened, with the only drawer chosen alone, «Cancel», the «×», Escape and a tap outside close it without asking', async () => {
    const s = await setup();
    await s.result(REGISTERS, page([{ id: 'r1', name: 'Bar', is_active: true }]));
    const { expectUntouchedWindowClosesAtOnce } = await import('../../../../base/frontend/__tests__/unsaved-form');
    await expectUntouchedWindowClosesAtOnce(s, 'cash-register-open');
  });
});

describe('OpenSessionModal: the float, read as every amount of the Hub', () => {
  const window = {
    open: async (business?: Business | null) => {
      const m = await mountCash(OpenSessionModal, { props: { open: true }, business });
      await m.live();
      await m.result(REGISTERS, page([]));
      return m;
    },
    field: 'cash-register-open-balance',
    submit: 'cash-register-open-submit',
    amount: (body: Record<string, unknown>) => body.opening_balance,
  };
  itReadsAmountsAsTheHub(window);
  itReadsWhatWasLeftOnceTheMoneyArrives(window);
});
