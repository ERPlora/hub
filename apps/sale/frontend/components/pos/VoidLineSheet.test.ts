// «Void «<item>»» (SALE-F20): a line already sent to the kitchen leaves the check with a reason — one
// tap («Ordered by mistake», «Customer changed their mind», «Sold out», «Entered twice») or typed —
// and «Void item» cannot be pressed without one. A refusal is read in the sheet.
import { describe, expect, it, vi } from 'vitest';
import { h, ref } from 'vue';

import { click, mountSale, settle } from '../../__tests__/mount-sale';
import VoidLineSheet from './VoidLineSheet.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

async function setup(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const open = ref(true);
  const m = await mountSale(
    {
      setup: () => () =>
        h(VoidLineSheet, { open: open.value, 'onUpdate:open': (v: boolean) => (open.value = v), name: 'Soup', pending: false, error: null, ...props }),
    },
    { locale },
  );
  await settle();
  const confirm = () => m.find('pos-void-confirm');
  const disabled = () => (confirm().element as HTMLElement & { disabled?: boolean }).disabled === true;
  const box = () => m.find('pos-void-reason').element as HTMLTextAreaElement;
  return { ...m, open, confirm, disabled, box, sheet: () => m.wrapper.findComponent(VoidLineSheet) };
}

describe('VoidLineSheet', () => {
  it('says what voiding means and offers the one-tap reasons, in Spanish too', async () => {
    const m = await setup({}, 'es');
    expect(m.find('pos-void-title').text()).toBe('Anular «Soup»');
    expect(m.find('pos-void-hint').text()).toBe(
      'Ya se envió a cocina. Sale de la cuenta y se guarda el motivo. Tiene que autorizarlo un responsable.',
    );
    expect(m.wrapper.findAll('.pos-sheet-chip').map((c) => c.text())).toEqual(['Error al pedir', 'El cliente lo cambia', 'Agotado', 'Pedido dos veces']);
    expect(m.box().placeholder).toBe('O escribe el motivo…');
    expect(m.confirm().text()).toBe('Anular artículo');
  });

  it('cannot void without a reason; a one-tap reason fills it and voids with it', async () => {
    const m = await setup();
    expect(m.disabled()).toBe(true);
    await click(m.find('pos-void-reason-soldOut').element);
    expect(m.box().value).toBe('Sold out');
    expect(m.disabled()).toBe(false);
    await click(m.confirm().element);
    expect(m.sheet().emitted('void')).toEqual([['Sold out']]);
  });

  it('a typed reason goes trimmed', async () => {
    const m = await setup();
    m.box().value = '  burnt ';
    m.box().dispatchEvent(new Event('input'));
    await settle();
    await click(m.confirm().element);
    expect(m.sheet().emitted('void')).toEqual([['burnt']]);
  });

  it('a refusal is read in the sheet', async () => {
    const m = await setup({ error: 'You do not have permission.' });
    expect(m.find('pos-void-error').text()).toBe('You do not have permission.');
  });
});
