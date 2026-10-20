// flow: SALE-F11 — the options sheet of the till (MODIFIER-F06): the product's name, each group with its rule
// and its options with their supplement, the defaults already chosen, a counter where an option repeats, and
// «Add · <price>», which waits (and says so) while a required group is short. It hands the ids up, in the
// order chosen; the server values them.
import { describe, expect, it, vi } from 'vitest';

import type { TargetGroupOut } from '../../../../modifier/frontend/operations';
import { click, mountSale, settle } from '../../__tests__/mount-sale';
import { plain } from '../../lib/format';
import { product } from './__tests__/fixtures';
import ModifierSheet from './ModifierSheet.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const option = (id: string, name: string, price_delta = 0, is_default = false) => ({
  id,
  name,
  kitchen_name: '',
  price_delta,
  tax_category_key: null,
  is_default,
});

const GROUPS: TargetGroupOut[] = [
  {
    id: 'extras',
    name: 'Extras',
    kitchen_name: '',
    min_choices: 0,
    max_choices: 3,
    allow_repeat: true,
    is_required: false,
    options: [option('cheese', 'Queso', 100), option('onion', 'Sin cebolla', 0, true), option('meat', 'Sin carne', -200)],
  },
  {
    id: 'doneness',
    name: 'Punto',
    kitchen_name: '',
    min_choices: 1,
    max_choices: 1,
    allow_repeat: false,
    is_required: true,
    options: [option('rare', 'Poco hecha'), option('done', 'Muy hecha')],
  },
];

async function setup(props: Record<string, unknown> = {}) {
  const m = await mountSale(ModifierSheet, {
    props: { open: true, product: product({ id: 'p1', name: 'Hamburguesa', price: 800 }), groups: GROUPS, pending: false, error: null, ...props },
    locale: 'es',
  });
  await settle();
  return m;
}

describe('ModifierSheet', () => {
  it('names the product and says each group’s rule; the supplement shows with its sign and a free one shows none', async () => {
    const s = await setup();
    expect(s.inDoc('pos-options-title')?.textContent).toContain('Hamburguesa');
    expect(s.inDoc('pos-options-rule-extras')?.textContent).toContain('Hasta 3');
    expect(s.inDoc('pos-options-rule-doneness')?.textContent).toContain('Elige 1');
    expect(plain(s.inDoc('pos-option-cheese')?.textContent ?? '')).toContain('+1,00 €');
    expect(plain(s.inDoc('pos-option-meat')?.textContent ?? '')).toContain('−2,00 €');
    expect(s.inDoc('pos-option-onion')?.textContent).not.toContain('€');
  });

  it('opens with the defaults chosen and «Add» waiting for the required group, saying so on a tap', async () => {
    const s = await setup();
    expect(s.inDoc('pos-option-onion')?.getAttribute('aria-pressed')).toBe('true');
    const add = s.inDoc('pos-options-add');
    expect(add?.textContent).toContain('Elige una opción para continuar');
    await click(add);
    expect(s.wrapper.emitted('add')).toBeUndefined();
    expect(s.inDoc('pos-options-group-doneness')?.classList.contains('pos-options__group--missing')).toBe(true);
  });

  it('counts a repeated option and hands the ids up in the order chosen, with the price it previews', async () => {
    const s = await setup();
    await click(s.inDoc('pos-option-cheese'));
    await click(s.inDoc('pos-option-rare'));
    await click(s.inDoc('pos-option-cheese'));
    expect(s.inDoc('pos-option-count-cheese')?.textContent).toContain('2');
    expect(plain(s.inDoc('pos-options-add')?.textContent ?? '')).toContain('Añadir · 10,00 €');
    await click(s.inDoc('pos-options-add'));
    expect(s.wrapper.emitted('add')).toEqual([[['onion', 'cheese', 'rare', 'cheese']]]);
  });

  it('swaps in a group of one', async () => {
    const s = await setup();
    await click(s.inDoc('pos-option-rare'));
    await click(s.inDoc('pos-option-done'));
    expect(s.inDoc('pos-option-rare')?.getAttribute('aria-pressed')).toBe('false');
    expect(s.inDoc('pos-option-done')?.getAttribute('aria-pressed')).toBe('true');
  });

  it('a counted option goes down with its minus', async () => {
    const s = await setup();
    await click(s.inDoc('pos-option-cheese'));
    await click(s.inDoc('pos-option-less-cheese'));
    expect(s.inDoc('pos-option-cheese')?.getAttribute('aria-pressed')).toBe('false');
  });

  it('reads the server’s refusal over the button', async () => {
    const s = await setup({ error: 'Elige al menos 1 en «Punto».' });
    expect(s.inDoc('pos-options-error')?.textContent).toContain('Elige al menos 1');
  });
});
