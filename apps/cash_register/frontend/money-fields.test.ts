// hub#1160: the drawer reads an amount the way every money field of the Hub reads it — the platform's `MoneyInput` and
// its `parseMoney` (`@erplora/ui/components`) — in the four windows that take one: «Open cash session» (the float,
// CASH_REGISTER-F03), «Cash movement» (F05), «Cash count» without a breakdown (its total, F06) and «Close session» (the
// counted cash, F09). Each text of the table is typed and left: the field shows and says what the platform's field
// shows and says for it (rewritten in the page format, or why it is not an amount), and the window sends exactly
// `parseMoney`'s minor units, or nothing. «12,555» is 12.555 € here as in a price, «0,515» is no amount in euros, and
// «1.250» still asks. As every money field, the three read in the business's money neither rewrite nor judge what was
// left before it answers (hub#945): «12,50 zł» stays as typed and is then read in złoty. A guard keeps the drawer's own reader out of its windows: it only reads the list's filters
// (hub#1196 takes those to the platform's reader).
import { MoneyInput, parseMoney, type Money } from '@erplora/ui/components';
import { toastSuccess } from '@erplora/ui/shell';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { business, ionValue, mountCash, POLISH, settle } from './__tests__/mount-cash-register';
import { expectAmountLeftWaitsForMoney } from '../../../base/frontend/__tests__/save-waits-for-money';
import type { Business } from '../../../base/frontend/operations';
import CloseSessionForm from './components/CloseSessionForm.vue';
import CountModal from './components/CountModal.vue';
import MovementModal from './components/MovementModal.vue';
import OpenSessionModal from './components/OpenSessionModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});
vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...((await importOriginal()) as object),
  toastSuccess: vi.fn(() => Promise.resolve()),
}));
beforeEach(() => vi.mocked(toastSuccess).mockClear());

const EUR: Money = { currency: 'EUR', decimals: 2 };
const SESSION = { id: 's1', number: 'S-261014-0001' };
const page = (rows: unknown[]) => ({ rows, total: rows.length, limit: 20, offset: 0 });
const prop = (el: Element | null, name: string): unknown => (el as unknown as Record<string, unknown> | null)?.[name];
/** Every window's answer to a send it makes: enough for each one's «done» toast. */
const DONE = { id: 's1', key: 'm1', number: 'S-261014-0001', status: 'closed', total: 0, expected_balance: 0, closing_balance: 0, difference: 0 };

/** What a person types in a money field of a business in euros: the two that the drawer read otherwise («12,555»,
 *  «0,515»), the one that reads two ways, too many decimals, grouped thousands, the currency around the figure, a minus
 *  and letters. */
const TYPED = ['12,555', '0,515', '1.250', '12,5555', '1.234,56', '12,50 €', '€ 12,50', '150,5', '-5', 'abc'];

type Mounted = Awaited<ReturnType<typeof mountCash>>;

interface MoneyWindow {
  /** The window, mounted in a business in euros (or in `business`; `null`: it never answers) and ready to take an
   *  amount. */
  open: (business?: Business | null) => Promise<Mounted>;
  /** Its amount is read in the business's money (`base.business.get`), not in the count's currency. */
  business: boolean;
  /** The `data-testid` of its money field and of its button. */
  field: string;
  submit: string;
  /** The minor units the window sent, out of the body of its call. */
  amount: (body: Record<string, unknown>) => unknown;
}

const WINDOWS: Record<string, MoneyWindow> = {
  'Open cash session · Opening float (F03)': {
    open: async (business) => {
      const m = await mountCash(OpenSessionModal, { props: { open: true }, business });
      await m.live();
      await m.result('cash_register.register.list', { ...page([]), limit: 100 });
      return m;
    },
    business: true,
    field: 'cash-register-open-balance',
    submit: 'cash-register-open-submit',
    amount: (body) => body.opening_balance,
  },
  'Cash movement · Amount (F05)': {
    open: async (business) => {
      const m = await mountCash(MovementModal, { props: { open: true, session: SESSION }, business });
      await m.live();
      return m;
    },
    business: true,
    field: 'cash-register-movement-amount',
    submit: 'cash-register-movement-submit',
    amount: (body) => body.amount,
  },
  'Cash count without a breakdown · Total counted (F06)': {
    open: async () => {
      const m = await mountCash(CountModal, { props: { open: true, session: SESSION } });
      await m.live();
      await m.result('cash_register.currency.get', { ...EUR, bills: [], coins: [] });
      return m;
    },
    business: false,
    field: 'cash-register-count-total-input',
    submit: 'cash-register-count-submit',
    amount: (body) => body.total,
  },
  'Close session · Counted cash (F09)': {
    open: async (business) => {
      const m = await mountCash(CloseSessionForm, { props: { session: SESSION }, business });
      await m.live();
      await m.result('cash_register.session.get', { ...SESSION, status: 'open', summary: { expected_cash: 10150 } });
      await m.result('cash_register.count.list', page([]));
      await m.result('sale.order.list', page([]));
      await m.result('kitchen.ticket.board', { cooking: [], ready: [], cooking_count: 0, ready_count: 0, stations: [], truncated: false });
      await m.result('printing.job.summary', { usages: [], pending: 0, sent: 0, failed: 0 });
      return m;
    },
    business: true,
    field: 'cash-register-close-counted',
    submit: 'cash-register-close-submit',
    amount: (body) => body.closing_balance,
  },
};

/** Types `text` in the field and leaves it, as a person does: what it shows and what it says under itself then. */
async function typeAndLeave(m: Mounted, field: string, text: string): Promise<{ shows: unknown; says: unknown }> {
  await ionValue(m.inDoc(field), text, 'ionInput');
  m.inDoc(field)?.dispatchEvent(new CustomEvent('ionBlur'));
  await settle();
  return { shows: prop(m.inDoc(field), 'value'), says: prop(m.inDoc(field), 'errorText') || undefined };
}

/** The platform's money field of a business in euros, the one every price of the Hub is typed in. */
async function platformField(text: string): Promise<{ shows: unknown; says: unknown }> {
  const m = await mountCash(MoneyInput, { props: { modelValue: '', label: 'Amount', testid: 'platform-amount', money: EUR } });
  return typeAndLeave(m, 'platform-amount', text);
}

describe.each(Object.entries(WINDOWS))('%s reads an amount as the rest of the Hub (hub#1160)', (_, window) => {
  it.each(TYPED)('«%s»', async (text) => {
    const m = await window.open();
    m.answer(200, DONE);
    const field = await typeAndLeave(m, window.field, text);
    m.inDoc(window.submit)?.dispatchEvent(new MouseEvent('click', { bubbles: true, composed: true }));
    await settle();
    const read = parseMoney(text, { money: EUR });
    expect({ field, sent: m.sent().map((call) => window.amount(call.body as Record<string, unknown>)) }).toEqual({
      field: await platformField(text),
      sent: read.ok && read.cents !== null ? [read.cents] : [],
    });
  });
});

const IN_THE_BUSINESS_MONEY = Object.entries(WINDOWS).filter(([, window]) => window.business);

describe.each(IN_THE_BUSINESS_MONEY)('%s before the business says its money (hub#945)', (_, window) => {
  it('«12,50 zł» left while it waits stays as typed and unmarked, then is read and sent in złoty', async () => {
    const m = await window.open(null);
    await expectAmountLeftWaitsForMoney({ amount: () => m.inDoc(window.field), settle }, '12,50 zł', () =>
      m.result('base.business.get', business(POLISH)),
    );
    m.answer(200, DONE);
    m.inDoc(window.submit)?.dispatchEvent(new MouseEvent('click', { bubbles: true, composed: true }));
    await settle();
    expect(m.sent().map((call) => window.amount(call.body as Record<string, unknown>))).toEqual([1250]);
  });
});

describe('the drawer’s own reader (hub#1160)', () => {
  const sources = import.meta.glob(['./**/*.{ts,vue}', '!./**/*.test.ts', '!./**/__tests__/**'], {
    query: '?raw',
    import: 'default',
    eager: true,
  }) as Record<string, string>;

  it('no window reads an amount with it nor has a money field of its own: only the list’s filters still use it', () => {
    const readers = Object.entries(sources)
      .filter(([, source]) => /\b(readMoney|readAmount|moneyRefusal)\b|MoneyField\.vue/.test(source))
      .map(([file]) => file);
    expect(readers.sort()).toEqual(['./lib/money.ts', './lib/sessionFilters.ts']);
  });
});
