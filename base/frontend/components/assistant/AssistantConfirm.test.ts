// BASE-G115, G116 and G119: the card of a write before it runs — the platform's ConfirmDialog. A normal one in one
// line, «Run it» in one click; a dangerous one with every datum and the word (or how many) to type; «Cancel all»
// when more actions of the turn wait behind it.
import { ConfirmDialog } from '@erplora/ui/components';
import { afterEach, describe, expect, it } from 'vitest';

import { flush, mountBase } from '../../__tests__/mount-base';
import type { AssistantCard } from '../../lib/assistant-card';
import AssistantConfirm from './AssistantConfirm.vue';

const NORMAL: AssistantCard = {
  operation: 'service.service.create',
  app: 'service',
  app_name: 'Servicios',
  action: 'create',
  risk: 'normal',
  fields: [
    { name: 'name', label: 'Name', kind: 'text', value: 'Corte caballero' },
    { name: 'price', label: 'Price', kind: 'money', value: 1500 },
    { name: 'tax_category_key', label: 'Tax Category Key', kind: 'text', value: 'general' },
  ],
  count: null,
  confirm_word: '',
  blocked: false,
};
const HIGH: AssistantCard = {
  ...NORMAL,
  operation: 'appointment.appointment.bulk_delete',
  app: 'appointment',
  app_name: 'Citas',
  action: 'bulk_delete',
  risk: 'high',
  fields: [{ name: 'ids', label: 'Ids', kind: 'list', value: ['a', 'b', 'c'] }],
  count: 3,
  confirm_word: '3',
};

afterEach(() => {
  document.body.innerHTML = '';
});

/** The dialog's body: Ionic moves the modal's content out of the component's root, into the document. */
const body = () => document.querySelector<HTMLElement>('[data-testid="assistant-confirm"]')?.textContent ?? '';

async function card(value: AssistantCard | null, more = false) {
  const m = await mountBase(AssistantConfirm, { locale: 'es', props: { card: value, more, money: { currency: 'EUR', decimals: 2 } } });
  await flush();
  return { ...m, dialog: m.wrapper.findComponent(ConfirmDialog) };
}

describe('AssistantConfirm', () => {
  it('a normal write: its action, its app and its data in one line, and a click', async () => {
    const { wrapper, dialog } = await card(NORMAL);
    expect(dialog.props('open')).toBe(true);
    expect(dialog.props('title')).toBe('¿Ejecutar esta acción?');
    expect(body()).toContain('Crear en Servicios: Corte caballero · 15,00 € · general');
    expect(dialog.props('requireText')).toBeUndefined();
    expect(dialog.props('tone')).toBe('primary');
    dialog.vm.$emit('confirm');
    expect(wrapper.emitted('decide')).toEqual([[true, '', false]]);
  });

  it('a dangerous one: every datum by its name, how many, and what to type before it runs', async () => {
    const { wrapper, dialog } = await card(HIGH);
    expect(dialog.props('tone')).toBe('danger');
    expect(dialog.props('requireText')).toBe('3');
    expect(dialog.props('consequences')).toEqual(['Registros: 3 elementos']);
    expect(body()).toContain('Borrar en Citas. Revisa cada dato antes de seguir.');
    expect(body()).toContain('Afecta a 3 registros.');
    dialog.vm.$emit('confirm');
    expect(wrapper.emitted('decide')).toEqual([[true, '3', false]]);
  });

  it('the amounts in the currency the card brings (gh:hub#1045)', async () => {
    const m = await mountBase(AssistantConfirm, { locale: 'es', props: { card: { ...NORMAL, money: { currency: 'USD', decimals: 2 } }, more: false } });
    await flush();
    expect(body()).toContain('15,00\u00a0$');
    expect(body()).not.toContain('€');
    m.wrapper.unmount();
  });

  it('cancelling runs nothing', async () => {
    const { wrapper, dialog } = await card(NORMAL);
    dialog.vm.$emit('cancel');
    expect(wrapper.emitted('decide')).toEqual([[false, '', false]]);
  });

  it('«Cancel all» only when more actions wait, and it stops them all', async () => {
    const single = await card(NORMAL);
    expect(document.querySelector('[data-testid="assistant-cancel-all"]')).toBeNull();
    single.wrapper.unmount();
    document.body.innerHTML = '';
    const chain = await card(NORMAL, true);
    document.querySelector<HTMLElement>('[data-testid="assistant-cancel-all"]')!.click();
    expect(chain.wrapper.emitted('decide')).toEqual([[false, '', true]]);
  });

  it('closed without a card, and it opens when one arrives and closes when it is answered', async () => {
    const { wrapper, dialog } = await card(null);
    expect(dialog.props('open')).toBe(false);
    await wrapper.setProps({ card: NORMAL });
    await flush();
    expect(dialog.props('open')).toBe(true);
    expect(body()).toContain('Crear en Servicios');
    await wrapper.setProps({ card: null });
    await flush();
    expect(dialog.props('open')).toBe(false);
    expect(wrapper.emitted('decide')).toBeUndefined();
  });
});
