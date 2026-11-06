// The test helper of a window whose «Save» waits for the business's money (hub#918) passes a window that waits and lights
// up once the business answers, and catches each way a window can get it wrong: a «Save» that is not grey, a save that
// reads past the grey button (a `submit` FormModal did not hold), a field that complains while it waits, and a «Save»
// that stays grey after the answer. A window without FormModal (the till's sheets and its charge sheet, hub#921) says its
// own door past the grey button, or that its button is its only one. When the money cannot be read instead (hub#938), the
// window says so with «Retry» — the platform's BusinessMoneyError, in a window with FormModal or in a sheet without it —
// and the helper fails a window that waits without a word, or that lights «Save» up with no money to read in.
import { FormModal } from '@erplora/ui/components';
import { IonButton } from '@ionic/vue';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { defineComponent, h, nextTick, ref } from 'vue';

import BusinessMoneyError from '../components/BusinessMoneyError.vue';
import { useBusinessMoney } from '../lib/money';
import { business, flush, mountBase, resultFrame, subId } from './mount-base';
import { expectSaveWaitsForMoney, expectSaysMoneyUnreadable, moneyReadOf } from './save-waits-for-money';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

type Control = HTMLElement & { disabled?: boolean; errorText?: string };

/** A window like the four of hub#918, its money not answered yet: «Save» grey or not until `answer()`, and a save that
 *  sends what it reads («1500» read with two decimals) unless it is guarded. */
async function windowThat(behaves: { grey: boolean; guarded: boolean; complains?: boolean; staysGrey?: boolean }) {
  const sent: unknown[] = [];
  const answered = ref(false);
  const Window = defineComponent({
    setup() {
      function save(): void {
        if (!behaves.guarded) sent.push({ price: 150000 });
      }
      const grey = () => behaves.grey && (!answered.value || !!behaves.staysGrey);
      return () => h(FormModal, { open: true, title: 'New thing', testid: 'thing', submitDisabled: grey(), onSubmit: save }, () => []);
    },
  });
  const m = await mountBase(Window);
  const answer = async () => {
    answered.value = true;
    await nextTick();
  };
  return {
    answer,
    wrapper: m.wrapper,
    save: () => document.querySelector<Control>('[data-testid="thing-submit"]'),
    amount: () => ({ errorText: behaves.complains ? 'This is not an amount.' : undefined }) as Control,
    sent: () => sent,
    settle: async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    },
  };
}

describe('expectSaveWaitsForMoney', () => {
  it('passes a window that waits — nothing sent, «Save» grey, the field silent — and lights up once the business answers', async () => {
    const w = await windowThat({ grey: true, guarded: true });
    await expect(expectSaveWaitsForMoney(w, w.answer)).resolves.toBeUndefined();
  });

  it('fails a window whose «Save» is not grey', async () => {
    const w = await windowThat({ grey: false, guarded: true });
    await expect(expectSaveWaitsForMoney(w, w.answer)).rejects.toThrow(/true/);
  });

  it('fails a window that reads the amount past the grey button', async () => {
    const w = await windowThat({ grey: true, guarded: false });
    await expect(expectSaveWaitsForMoney(w, w.answer)).rejects.toThrow(/150000/);
  });

  it('fails a window whose field complains while it waits', async () => {
    const w = await windowThat({ grey: true, guarded: true, complains: true });
    await expect(expectSaveWaitsForMoney(w, w.answer)).rejects.toThrow(/not an amount/);
  });

  it('fails a window whose «Save» stays grey once the business answers', async () => {
    const w = await windowThat({ grey: true, guarded: true, staysGrey: true });
    await expect(expectSaveWaitsForMoney(w, w.answer)).rejects.toThrow(/once the business answered/);
  });
});

/** A window without FormModal, its money not answered yet: its button grey until `answer()`. `button: 'reaches'` — a
 *  click reaches its handler grey or not (the till's sheets), so only its own guard holds it; `'holds'` — the button
 *  holds its own click while grey (the charge sheet's foot) and `confirm` is the door past it. Unguarded, it hands up
 *  what it reads («1500» read with two decimals). */
async function sheetThat(behaves: { button: 'reaches' | 'holds'; guarded: boolean }) {
  const handed: unknown[] = [];
  const answered = ref(false);
  const confirm = (): void => {
    if (!behaves.guarded || answered.value) handed.push({ unit_price: 150000 });
  };
  const press = (): void => {
    if (behaves.button === 'reaches' || answered.value) confirm();
  };
  const m = await mountBase(() => h(IonButton, { 'data-testid': 'sheet-add', disabled: !answered.value, onClick: press }, () => 'Add'));
  return {
    confirm,
    answer: async () => {
      answered.value = true;
      await nextTick();
    },
    wrapper: m.wrapper,
    save: () => m.wrapper.find<Control>('[data-testid="sheet-add"]').element,
    amount: () => null,
    sent: () => handed,
    settle: async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    },
  };
}

describe('expectSaveWaitsForMoney: a window without FormModal (hub#921)', () => {
  it('passes a sheet whose button is its only door (`submit: null`) when its own guard holds the click', async () => {
    const w = await sheetThat({ button: 'reaches', guarded: true });
    await expect(expectSaveWaitsForMoney({ ...w, submit: null }, w.answer)).resolves.toBeUndefined();
  });

  it('fails a sheet whose click reaches its handler and reads the amount past its grey button', async () => {
    const w = await sheetThat({ button: 'reaches', guarded: false });
    await expect(expectSaveWaitsForMoney({ ...w, submit: null }, w.answer)).rejects.toThrow(/150000/);
  });

  it('presses the door the window says (`submit`) past a button that holds itself: passes it guarded…', async () => {
    const w = await sheetThat({ button: 'holds', guarded: true });
    await expect(expectSaveWaitsForMoney({ ...w, submit: w.confirm }, w.answer)).resolves.toBeUndefined();
  });

  it('…and fails it unguarded', async () => {
    const w = await sheetThat({ button: 'holds', guarded: false });
    await expect(expectSaveWaitsForMoney({ ...w, submit: w.confirm }, w.answer)).rejects.toThrow(/150000/);
  });
});

/** A window whose «Save» waits for the business's real money (`useBusinessMoney`), with FormModal (`form`) or as a sheet
 *  with its own button (`sheet`), that places the platform's notice (`says`) or not; `lightsUp`: «Save» does not wait. */
async function waitingFor(money: { kind: 'form' | 'sheet'; says: boolean; lightsUp?: boolean }) {
  const sent: unknown[] = [];
  const Window = {
    setup() {
      const known = useBusinessMoney();
      const grey = () => !known.value && !money.lightsUp;
      const notice = () => (money.says ? [h(BusinessMoneyError)] : []);
      const save = (): void => {
        if (known.value) sent.push({ price: 1500 });
      };
      return () =>
        money.kind === 'form'
          ? h(FormModal, { open: true, title: 'New thing', testid: 'thing', submitDisabled: grey(), onSubmit: save }, () => notice())
          : h('div', [...notice(), h(IonButton, { 'data-testid': 'thing-submit', disabled: grey(), onClick: save }, () => 'Add')]);
    },
  };
  const m = await mountBase(Window);
  await m.live();
  const settle = async () => {
    await flush();
    await flush();
  };
  const window = {
    wrapper: m.wrapper,
    save: () => document.querySelector<Control>('[data-testid="thing-submit"]'),
    amount: () => null,
    sent: () => sent,
    settle,
  };
  const read = moneyReadOf(m, async () => {
    m.net.lastStream().push(resultFrame(subId(m.client, 'base.business.get'), business(), 1));
    await settle();
  });
  return { window, read };
}

describe('expectSaysMoneyUnreadable (hub#938)', () => {
  afterEach(() => {
    document.body.innerHTML = '';
  });

  it.each(['form', 'sheet'] as const)('passes a window (%s) that says the money could not be read, with «Retry», and lights up once it answers', async (kind) => {
    const w = await waitingFor({ kind, says: true });
    await expect(expectSaysMoneyUnreadable(w.window, w.read)).resolves.toBeUndefined();
  });

  it.each(['form', 'sheet'] as const)('fails a window (%s) that waits in grey without a word', async (kind) => {
    const w = await waitingFor({ kind, says: false });
    await expect(expectSaysMoneyUnreadable(w.window, w.read)).rejects.toThrow(/could not be read/);
  });

  it('fails a window whose «Save» is not grey while the money cannot be read', async () => {
    const w = await waitingFor({ kind: 'form', says: true, lightsUp: true });
    await expect(expectSaysMoneyUnreadable(w.window, w.read)).rejects.toThrow(/grey/);
  });
});
