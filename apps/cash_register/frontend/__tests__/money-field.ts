// Test helper of the drawer's windows that take an amount (hub#1160): «Open cash session» (the float, CASH_REGISTER-F03),
// «Cash movement» (F05), «Cash count» without a breakdown (its total, F06) and «Close session» (the counted cash, F09).
// Each reads an amount the way every money field of the Hub reads it — the platform's `MoneyInput` and its
// `parseMoney` (`@erplora/ui/components`). `itReadsAmountsAsTheHub` types each text of the table and leaves the field:
// it shows and says what the platform's field shows and says for it (rewritten in the page format, or why it is not an
// amount), and the window sends exactly `parseMoney`'s minor units, or nothing. «12,555» is 12.555 € there as in a
// price, «0,515» is no amount in euros, and «1.250» still asks. `itReadsWhatWasLeftOnceTheMoneyArrives`: a window that
// reads in the business's money neither rewrites nor judges what was left before it answers (hub#945), and then reads
// it in that money. Each window's test calls them in one line, with its own mocks (IonModal, the toasts).
import { MoneyInput, type Money, parseMoney } from '@erplora/ui/components';
import { expect, it } from 'vitest';

import { expectAmountLeftWaitsForMoney } from '../../../../base/frontend/__tests__/save-waits-for-money';
import type { Business } from '../../../../base/frontend/operations';
import { business, ionValue, mountCash, POLISH, settle } from './mount-cash-register';

type Mounted = Pick<Awaited<ReturnType<typeof mountCash>>, 'inDoc' | 'answer' | 'sent' | 'result'>;

export interface MoneyWindow {
  /** The window, mounted in a business in euros (or in `business`; `null`: it never answers) and ready to take an
   *  amount. */
  open: (business?: Business | null) => Promise<Mounted>;
  /** The `data-testid` of its money field and of its button. */
  field: string;
  submit: string;
  /** The minor units the window sent, out of the body of its call. */
  amount: (body: Record<string, unknown>) => unknown;
}

const EUR: Money = { currency: 'EUR', decimals: 2 };
/** Every window's answer to a send it makes: enough for each one's «done» toast. */
const DONE = { id: 's1', key: 'm1', number: 'S-261014-0001', status: 'closed', total: 0, expected_balance: 0, closing_balance: 0, difference: 0 };

/** What a person types in a money field of a business in euros: the two that the drawer read otherwise («12,555»,
 *  «0,515»), the one that reads two ways, too many decimals, grouped thousands, the currency around the figure, a minus
 *  and letters. */
export const TYPED = ['12,555', '0,515', '1.250', '12,5555', '1.234,56', '12,50 €', '€ 12,50', '150,5', '-5', 'abc'];

const prop = (el: Element | null, name: string): unknown => (el as unknown as Record<string, unknown> | null)?.[name];

/** Types `text` in the field and leaves it, as a person does: what it shows and what it says under itself then. */
async function typeAndLeave(m: Pick<Mounted, 'inDoc'>, field: string, text: string): Promise<{ shows: unknown; says: unknown }> {
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

async function press(m: Mounted, submit: string): Promise<void> {
  m.inDoc(submit)?.dispatchEvent(new MouseEvent('click', { bubbles: true, composed: true }));
  await settle();
}

/** One test per text of `TYPED`: the window's field and what it sends are the platform's reading. */
export function itReadsAmountsAsTheHub(window: MoneyWindow): void {
  it.each(TYPED)('«%s» is read as in the rest of the Hub (hub#1160)', async (text) => {
    const m = await window.open();
    m.answer(200, DONE);
    const field = await typeAndLeave(m, window.field, text);
    await press(m, window.submit);
    const read = parseMoney(text, { money: EUR });
    expect({ field, sent: m.sent().map((call) => window.amount(call.body as Record<string, unknown>)) }).toEqual({
      field: await platformField(text),
      sent: read.ok && read.cents !== null ? [read.cents] : [],
    });
  });
}

/** «12,50 zł» left while the window waits for the business's money stays as typed and unmarked, then is read and sent
 *  in złoty (hub#945). */
export function itReadsWhatWasLeftOnceTheMoneyArrives(window: MoneyWindow): void {
  it('«12,50 zł» left while it waits for the money stays as typed and unmarked, then is sent in złoty (hub#945)', async () => {
    const m = await window.open(null);
    await expectAmountLeftWaitsForMoney({ amount: () => m.inDoc(window.field), settle }, '12,50 zł', () =>
      m.result('base.business.get', business(POLISH)),
    );
    m.answer(200, DONE);
    await press(m, window.submit);
    expect(m.sent().map((call) => window.amount(call.body as Record<string, unknown>))).toEqual([1250]);
  });
}
