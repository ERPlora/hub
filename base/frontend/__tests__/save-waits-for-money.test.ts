// The test helper of a window whose «Save» waits for the business's money (hub#918) passes a window that waits and lights
// up once the business answers, and catches each way a window can get it wrong: a «Save» that is not grey, a save that
// reads past the grey button (a `submit` FormModal did not hold), a field that complains while it waits, and a «Save»
// that stays grey after the answer.
import { FormModal } from '@erplora/ui/components';
import { describe, expect, it, vi } from 'vitest';
import { defineComponent, h, nextTick, ref } from 'vue';

import { mountBase } from './mount-base';
import { expectSaveWaitsForMoney } from './save-waits-for-money';

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
