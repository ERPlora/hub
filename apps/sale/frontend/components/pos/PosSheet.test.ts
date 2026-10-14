// The till's sheets (open price, note, discount, void, park, who serves…; spec «Sheets»): an
// `ion-modal` with the title and ✕, the big figure on top, the middle that scrolls and the foot with
// the confirm button always in view. A tap outside or Escape closes it.
import { describe, expect, it, vi } from 'vitest';
import { h, ref } from 'vue';

import { ionModalStubOf } from '../../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub';
import { click, mountSale, settle } from '../../__tests__/mount-sale';
import PosSheet from './PosSheet.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

async function setup(initial = true) {
  const open = ref(initial);
  const m = await mountSale({
    setup: () => () =>
      h(
        PosSheet,
        { open: open.value, 'onUpdate:open': (v: boolean) => (open.value = v), title: 'Open price', testid: 'pos-open-price' },
        {
          top: () => h('div', { 'data-testid': 'slot-top' }, '€12.00'),
          default: () => h('div', { 'data-testid': 'slot-body' }, 'keys'),
          foot: () => h('button', { 'data-testid': 'slot-foot' }, 'Add'),
        },
      ),
  });
  await settle();
  return { ...m, open };
}

describe('PosSheet', () => {
  it('shows its title, the top, the middle and the foot while open', async () => {
    const m = await setup();
    expect(m.find('pos-open-price-title').text()).toBe('Open price');
    for (const id of ['slot-top', 'slot-body', 'slot-foot']) expect(m.find(id).exists()).toBe(true);
    expect(m.find('pos-open-price').attributes('aria-label')).toBe('Open price');
  });

  it('is not there while closed', async () => {
    const m = await setup(false);
    expect(m.find('slot-body').exists()).toBe(false);
  });

  it('✕ closes it', async () => {
    const m = await setup();
    expect(m.find('pos-open-price-close').attributes('aria-label')).toBe('Close');
    await click(m.find('pos-open-price-close').element);
    expect(m.open.value).toBe(false);
  });

  it('a tap outside (Ionic’s own dismissal) closes it too', async () => {
    const m = await setup();
    ionModalStubOf(m.find('pos-open-price').element).tapBackdrop();
    await settle();
    expect(m.open.value).toBe(false);
  });
});
