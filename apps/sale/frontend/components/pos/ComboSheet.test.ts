// flow: SALE-F12 — the menu sheet of the till (COMBO-F07): the menu's name, every course at once with its rule
// and its dishes (the supplement with its sign), nothing picked to begin with, a course of one that swaps, a full
// course that answers, and a button that names the course still short («Elige 1 en «Segundos»») until each
// required course is complete, then sums the total live. It hands the dishes up; Menus prices them.
import { describe, expect, it, vi } from 'vitest';

import type { SaleComboOut } from '../../../../combo/frontend/operations';
import { click, mountSale, settle } from '../../__tests__/mount-sale';
import { plain } from '../../lib/format';
import ComboSheet from './ComboSheet.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const dish = (id: string, name: string, price_delta = 0) => ({ id, product_id: `p-${id}`, product_name: name, sku: '', price_delta });

const MENU: SaleComboOut = {
  id: 'm1',
  name: 'Menú del día',
  kitchen_name: 'MENU',
  price: 1350,
  supply_kind: 'service',
  sort_order: 0,
  groups: [
    { id: 'starters', name: 'Primeros', min_choices: 1, max_choices: 1, allow_repeat: false, options: [dish('lentils', 'Lentejas'), dish('salad', 'Ensalada')] },
    { id: 'mains', name: 'Segundos', min_choices: 1, max_choices: 1, allow_repeat: false, options: [dish('hake', 'Merluza'), dish('steak', 'Entrecot', 200)] },
    { id: 'coffee', name: 'Café', min_choices: 0, max_choices: 2, allow_repeat: false, options: [dish('espresso', 'Solo'), dish('latte', 'Con leche'), dish('cut', 'Cortado')] },
  ],
};

async function setup(props: Record<string, unknown> = {}) {
  const m = await mountSale(ComboSheet, {
    props: { open: true, combo: MENU, pending: false, error: null, ...props },
    locale: 'es',
  });
  await m.live();
  await settle();
  return m;
}

describe('ComboSheet', () => {
  it('names the menu and shows every course with its rule and its dishes, the supplement with its sign', async () => {
    const s = await setup();
    expect(s.inDoc('pos-menu-title')?.textContent).toContain('Menú del día');
    expect(s.inDoc('pos-menu-rule-starters')?.textContent).toContain('Elige 1');
    expect(s.inDoc('pos-menu-rule-coffee')?.textContent).toContain('Hasta 2');
    expect(s.inDoc('pos-menu-dish-lentils')?.textContent).toContain('Lentejas');
    expect(plain(s.inDoc('pos-menu-dish-steak')?.textContent ?? '')).toContain('+2,00 €');
    expect(s.inDoc('pos-menu-dish-hake')?.textContent).not.toContain('€');
  });

  it('opens with nothing picked and the button naming the course still short; a tap marks it and adds nothing', async () => {
    const s = await setup();
    expect(s.inDoc('pos-menu-dish-lentils')?.getAttribute('aria-pressed')).toBe('false');
    const add = s.inDoc('pos-menu-add');
    expect(add?.textContent).toContain('Elige 1 en «Primeros»');
    expect(add?.hasAttribute('disabled')).toBe(false);
    await click(add);
    expect(s.wrapper.emitted('add')).toBeUndefined();
    expect(s.inDoc('pos-menu-course-starters')?.classList.contains('pos-options__group--missing')).toBe(true);
    await click(s.inDoc('pos-menu-dish-salad'));
    expect(s.inDoc('pos-menu-add')?.textContent).toContain('Elige 1 en «Segundos»');
  });

  it('sums the total live once each required course is complete and hands the dishes up', async () => {
    const s = await setup();
    await click(s.inDoc('pos-menu-dish-lentils'));
    await click(s.inDoc('pos-menu-dish-steak'));
    await click(s.inDoc('pos-menu-dish-latte'));
    expect(plain(s.inDoc('pos-menu-add')?.textContent ?? '')).toContain('Añadir · 15,50 €');
    await click(s.inDoc('pos-menu-add'));
    expect(s.wrapper.emitted('add')).toEqual([
      [
        [
          { option_id: 'lentils', quantity: 1 },
          { option_id: 'steak', quantity: 1 },
          { option_id: 'latte', quantity: 1 },
        ],
      ],
    ]);
  });

  it('swaps the dish of a course of one, and a full course answers naming it', async () => {
    const s = await setup();
    await click(s.inDoc('pos-menu-dish-lentils'));
    await click(s.inDoc('pos-menu-dish-salad'));
    expect(s.inDoc('pos-menu-dish-lentils')?.getAttribute('aria-pressed')).toBe('false');
    expect(s.inDoc('pos-menu-dish-salad')?.getAttribute('aria-pressed')).toBe('true');
    await click(s.inDoc('pos-menu-dish-espresso'));
    await click(s.inDoc('pos-menu-dish-latte'));
    await click(s.inDoc('pos-menu-dish-cut'));
    expect(s.inDoc('pos-menu-dish-cut')?.getAttribute('aria-pressed')).toBe('false');
    expect(s.inDoc('pos-menu-course-coffee')?.textContent).toContain('«Café» está completo');
  });

  it('reads the server’s refusal over the button', async () => {
    const s = await setup({ error: '«Flan» está agotado.' });
    expect(s.inDoc('pos-menu-error')?.textContent).toContain('agotado');
  });
});
