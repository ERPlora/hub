// «Note on <item>» (SALE-F13): the quick-note chips, the box (up to 255 characters, «e.g. medium rare…»)
// with what the line already says, «The kitchen reads this note on the ticket.», «Remove» and «Save».
// Saving trims the text; an empty note removes it. A refusal is read in the sheet.
import { describe, expect, it, vi } from 'vitest';
import { h, ref } from 'vue';

import { click, mountSale, settle } from '../../__tests__/mount-sale';
import LineNoteSheet from './LineNoteSheet.vue';
import QuickNoteChips from './QuickNoteChips.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

async function setup(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const open = ref(true);
  const m = await mountSale(
    {
      setup: () => () =>
        h(LineNoteSheet, {
          open: open.value,
          'onUpdate:open': (v: boolean) => (open.value = v),
          name: 'Steak',
          note: 'No salt',
          pending: false,
          error: null,
          ...props,
        }),
    },
    { locale },
  );
  await settle();
  const box = () => m.find('pos-note-text').element as HTMLTextAreaElement;
  const sheet = () => m.wrapper.findComponent(LineNoteSheet);
  return { ...m, open, box, sheet };
}

describe('LineNoteSheet', () => {
  it('is «Note on <item>» with the line’s note in the box and the quick notes on top', async () => {
    const m = await setup({}, 'es');
    expect(m.find('pos-note-title').text()).toBe('Nota en Steak');
    expect(m.box().value).toBe('No salt');
    expect(m.box().maxLength).toBe(255);
    expect(m.box().placeholder).toBe('p. ej. poco hecho, alergia al marisco, sin hielo');
    expect(m.find('pos-note-hint').text()).toBe('Cocina lee esta nota en la comanda.');
    expect(m.wrapper.findComponent(QuickNoteChips).props('modelValue')).toBe('No salt');
  });

  it('«Save» hands the typed note up, trimmed', async () => {
    const m = await setup();
    m.box().value = '  rare, no salt ';
    m.box().dispatchEvent(new Event('input'));
    await click(m.find('pos-note-save').element);
    expect(m.sheet().emitted('save')).toEqual([['rare, no salt']]);
  });

  it('a chip writes into the box', async () => {
    const m = await setup();
    m.wrapper.findComponent(QuickNoteChips).vm.$emit('update:modelValue', 'No salt, Rare');
    await settle();
    expect(m.box().value).toBe('No salt, Rare');
  });

  it('«Remove» saves an empty note', async () => {
    const m = await setup({}, 'es');
    expect(m.find('pos-note-remove').text()).toBe('Quitar');
    await click(m.find('pos-note-remove').element);
    expect(m.sheet().emitted('save')).toEqual([['']]);
  });

  it('a refusal is read in the sheet and the buttons wait while saving', async () => {
    const m = await setup({ error: 'That line can no longer change.', pending: true });
    expect(m.find('pos-note-error').text()).toBe('That line can no longer change.');
    expect((m.find('pos-note-save').element as HTMLElement & { disabled?: boolean }).disabled).toBe(true);
  });
});
