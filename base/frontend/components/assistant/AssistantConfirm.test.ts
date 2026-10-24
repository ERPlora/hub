// BASE-G115, G116 and G119: the card of a write before it runs — the platform's ConfirmDialog. A normal one in one
// line, «Run it» in one click; a dangerous one with every datum and the word (or how many) to type; «Cancel all»
// when more actions of the turn wait behind it.
import { ConfirmDialog } from '@erplora/ui/components';
import { describe, expect, it } from 'vitest';

import { mountBase } from '../../__tests__/mount-base';
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

async function card(value: AssistantCard, more = false) {
  const m = await mountBase(AssistantConfirm, { locale: 'es', props: { card: value, more, money: { currency: 'EUR', decimals: 2 } } });
  return { ...m, dialog: m.wrapper.findComponent(ConfirmDialog) };
}

describe('AssistantConfirm', () => {
  it('a normal write: its action, its app and its data in one line, and a click', async () => {
    const { wrapper, dialog } = await card(NORMAL);
    expect(dialog.props('title')).toBe('El asistente quiere ejecutar una acción');
    expect(wrapper.text()).toContain('Crear en Servicios: Corte caballero · 15,00 € · general');
    expect(dialog.props('requireText')).toBeUndefined();
    expect(dialog.props('tone')).toBe('primary');
    dialog.vm.$emit('confirm');
    expect(wrapper.emitted('decide')).toEqual([[true, '', false]]);
    wrapper.unmount();
  });

  it('a dangerous one: every datum by its name, how many, and what to type before it runs', async () => {
    const { wrapper, dialog } = await card(HIGH);
    expect(dialog.props('tone')).toBe('danger');
    expect(dialog.props('requireText')).toBe('3');
    expect(dialog.props('consequences')).toEqual(['Registros: 3 elementos']);
    expect(wrapper.text()).toContain('Borrar en Citas. Revisa cada dato antes de seguir.');
    expect(wrapper.text()).toContain('Afecta a 3 registros.');
    dialog.vm.$emit('confirm');
    expect(wrapper.emitted('decide')).toEqual([[true, '3', false]]);
    wrapper.unmount();
  });

  it('cancelling runs nothing', async () => {
    const { wrapper, dialog } = await card(NORMAL);
    dialog.vm.$emit('cancel');
    expect(wrapper.emitted('decide')).toEqual([[false, '', false]]);
    wrapper.unmount();
  });

  it('«Cancel all» only when more actions wait, and it stops them all', async () => {
    const single = await card(NORMAL);
    expect(single.wrapper.find('[data-testid="assistant-cancel-all"]').exists()).toBe(false);
    single.wrapper.unmount();
    const chain = await card(NORMAL, true);
    await chain.wrapper.find('[data-testid="assistant-cancel-all"]').trigger('click');
    expect(chain.wrapper.emitted('decide')).toEqual([[false, '', true]]);
    chain.wrapper.unmount();
  });
});
