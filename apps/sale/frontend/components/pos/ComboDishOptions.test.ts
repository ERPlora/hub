// flow: SALE-F42 — the options of a dish picked in a menu: the steak asks its doneness right under it, with the options
// sheet's rules; the button names the group still short («Elige 1 en «Punto de la carne»») and a tap rings it; the total
// adds the options once per pick; the dish goes up with the ids of its options; unpicking or swapping the dish takes
// them away; a failed read is said under the dish with «Reintentar» and the menu cannot be added meanwhile. Without
// Modifiers the dishes are picked as before.
import { describe, expect, it } from 'vitest';

import type { TargetGroupOut } from '../../../../modifier/frontend/operations';
import { click, MANAGER, mountSale, settle } from '../../__tests__/mount-sale';
import { plain } from '../../lib/format';
import { menuDish as dish, product, refused, saleMenu } from './__tests__/fixtures';
import ComboSheet from './ComboSheet.vue';

const MENU = saleMenu([
  { id: 'mains', name: 'Segundos', min_choices: 1, max_choices: 1, allow_repeat: false, options: [dish('hake', 'Merluza'), dish('steak', 'Entrecot', 200)] },
  { id: 'coffee', name: 'Café', min_choices: 0, max_choices: 2, allow_repeat: true, options: [dish('latte', 'Con leche')] },
]);

const option = (id: string, name: string, price_delta = 0) => ({ id, name, kitchen_name: '', price_delta, tax_category_key: null, is_default: false, allergens: [] });
const DONENESS: TargetGroupOut = {
  id: 'doneness',
  name: 'Punto de la carne',
  kitchen_name: '',
  min_choices: 1,
  max_choices: 1,
  allow_repeat: false,
  is_required: true,
  options: [option('rare', 'Poco hecho'), option('done', 'Hecho')],
};
const EXTRAS: TargetGroupOut = {
  ...DONENESS,
  id: 'extras',
  name: 'Extras',
  min_choices: 0,
  max_choices: 2,
  is_required: false,
  options: [option('cheese', 'Queso', 100), option('bacon', 'Beicon'), option('egg', 'Huevo')],
};
const MILK: TargetGroupOut = { ...EXTRAS, id: 'milk', name: 'Leche', options: [option('oat', 'De avena', 20)] };
const GROUPS: Record<string, TargetGroupOut[]> = { 'p-steak': [DONENESS, EXTRAS], 'p-latte': [MILK] };

type Answer = (productId: string) => Response | Promise<Response>;
const groupsOf: Answer = (id) => Response.json({ product_id: id, product_name: id, groups: GROUPS[id] ?? [] });

/** Modifiers on in the business and readable by the manager, as the till asks the options of a dish. */
const WITH_MODIFIERS = { ...MANAGER, permissions: [...MANAGER.permissions, 'modifier.view'], apps: [{ label: 'modifier', state: 'on' as const }] };

async function setup(props: Record<string, unknown> = {}, groups: Answer = groupsOf, modifiers = true) {
  const session = modifiers ? WITH_MODIFIERS : MANAGER;
  const m = await mountSale(ComboSheet, { props: { open: false, combo: MENU, pending: false, error: null, ...props }, locale: 'es', session });
  m.net.onApi((call) => {
    const url = new URL(call.url, 'http://test');
    if (url.pathname === '/api/modifier/groups/for_target') return groups(url.searchParams.get('product_id') ?? '');
    return Response.json(product({ id: url.searchParams.get('id') ?? '', allergens: [] }));
  });
  await m.live();
  await m.wrapper.setProps({ open: true });
  await settle();
  const reads = () => m.sent().filter((call) => call.path === '/api/modifier/groups/for_target');
  const button = () => plain(m.inDoc('pos-menu-add')?.textContent ?? '');
  return { ...m, reads, button };
}

const within = (s: Awaited<ReturnType<typeof setup>>, dishId: string, testid: string) =>
  s.inDoc(`pos-menu-dish-options-${dishId}`)?.querySelector(`[data-testid="${testid}"]`) ?? null;

describe('ComboSheet: the options of a dish', () => {
  it('opens the groups of a picked dish right under it; a dish without groups opens nothing', async () => {
    const s = await setup();
    await click(s.inDoc('pos-menu-dish-hake'));
    await settle();
    expect(s.inDoc('pos-menu-dish-options-hake')).toBeNull();
    await click(s.inDoc('pos-menu-dish-steak'));
    await settle();
    expect(s.inDoc('pos-menu-dish-options-steak')?.textContent).toContain('Entrecot');
    expect(within(s, 'steak', 'pos-options-rule-doneness')?.textContent).toContain('Elige 1');
    expect(within(s, 'steak', 'pos-option-cheese')?.textContent).toContain('+1,00');
  });

  it('names the group still short and a tap rings it without adding', async () => {
    const s = await setup();
    await click(s.inDoc('pos-menu-dish-steak'));
    await settle();
    expect(s.button()).toContain('Elige 1 en «Punto de la carne»');
    await click(s.inDoc('pos-menu-add'));
    expect(s.wrapper.emitted('add')).toBeUndefined();
    expect(within(s, 'steak', 'pos-options-group-doneness')?.classList.contains('pos-options__group--missing')).toBe(true);
  });

  it('waits, marked as waiting, while a group of a dish is short, and stops waiting once it is complete', async () => {
    const s = await setup();
    await click(s.inDoc('pos-menu-dish-steak'));
    await settle();
    const add = () => s.inDoc('pos-menu-add');
    expect(add()?.getAttribute('aria-disabled')).toBe('true');
    expect(add()?.classList.contains('pos-menu__add--waiting')).toBe(true);
    await click(within(s, 'steak', 'pos-option-rare'));
    expect(add()?.hasAttribute('aria-disabled')).toBe(false);
    expect(add()?.classList.contains('pos-menu__add--waiting')).toBe(false);
  });

  it('a tap a full group of a dish refuses points at that group and says it is full', async () => {
    const s = await setup();
    await click(s.inDoc('pos-menu-dish-steak'));
    await settle();
    for (const id of ['cheese', 'bacon', 'egg']) await click(within(s, 'steak', `pos-option-${id}`));
    expect(within(s, 'steak', 'pos-option-egg')?.getAttribute('aria-pressed')).toBe('false');
    const extras = within(s, 'steak', 'pos-options-group-extras');
    expect(extras?.classList.contains('pos-options__group--missing')).toBe(true);
    expect(extras?.textContent).toContain('«Extras» está completo');
  });

  it('adds the options to the total and hands the dish up with them', async () => {
    const s = await setup();
    await click(s.inDoc('pos-menu-dish-steak'));
    await settle();
    await click(within(s, 'steak', 'pos-option-rare'));
    await click(within(s, 'steak', 'pos-option-cheese'));
    expect(s.button()).toContain('Añadir · 16,50 €');
    await click(s.inDoc('pos-menu-add'));
    expect(s.wrapper.emitted('add')).toEqual([[[{ option_id: 'steak', quantity: 1, option_ids: ['rare', 'cheese'] }]]]);
  });

  it('a dish picked twice carries its options each time', async () => {
    const s = await setup();
    await click(s.inDoc('pos-menu-dish-hake'));
    await click(s.inDoc('pos-menu-dish-latte'));
    await click(s.inDoc('pos-menu-dish-latte'));
    await settle();
    await click(within(s, 'latte', 'pos-option-oat'));
    // 13,50 € and 0,20 € of oat milk in each of the two coffees.
    expect(s.button()).toContain('Añadir · 13,90 €');
  });

  it('swapping the dish takes its options away, and picking it again starts over', async () => {
    const s = await setup();
    await click(s.inDoc('pos-menu-dish-steak'));
    await settle();
    await click(within(s, 'steak', 'pos-option-rare'));
    await click(s.inDoc('pos-menu-dish-hake'));
    await settle();
    expect(s.inDoc('pos-menu-dish-options-steak')).toBeNull();
    await click(s.inDoc('pos-menu-dish-steak'));
    await settle();
    expect(within(s, 'steak', 'pos-option-rare')?.getAttribute('aria-pressed')).toBe('false');
    // The steak's groups are read once; the hake's, once too, to know it has none.
    expect(s.reads().map((call) => call.query.product_id)).toEqual(['p-steak', 'p-hake']);
  });

  it('says under the dish when its options could not be read; the menu waits, and «Reintentar» reads them again', async () => {
    let failing = true;
    const s = await setup({}, (id) => (failing ? refused('internal_error', 'Internal error', 500) : groupsOf(id)));
    await click(s.inDoc('pos-menu-dish-steak'));
    await settle();
    expect(within(s, 'steak', 'pos-menu-dish-options-error-steak')?.textContent).toContain('No se han podido leer los suplementos');
    await click(s.inDoc('pos-menu-add'));
    expect(s.wrapper.emitted('add')).toBeUndefined();
    expect(s.inDoc('pos-menu-dish-options-steak')?.classList.contains('pos-menu-dish-options--missing')).toBe(true);
    failing = false;
    await click(within(s, 'steak', 'pos-menu-dish-options-retry-steak'));
    await settle();
    expect(within(s, 'steak', 'pos-options-rule-doneness')?.textContent).toContain('Elige 1');
  });

  it('says it is reading the options of the dish while they load', async () => {
    const waiting: ((answer: Response) => void)[] = [];
    const s = await setup({}, () => new Promise<Response>((resolve) => waiting.push(resolve)));
    await click(s.inDoc('pos-menu-dish-steak'));
    await settle();
    expect(within(s, 'steak', 'pos-menu-dish-options-loading-steak')?.textContent).toContain('Cargando suplementos…');
    for (const resolve of waiting) resolve(Response.json({ product_id: 'p-steak', product_name: 'p-steak', groups: GROUPS['p-steak'] }));
    await settle();
    expect(within(s, 'steak', 'pos-menu-dish-options-loading-steak')).toBeNull();
  });

  it('without Modifiers the dishes are picked as before, with nothing to read', async () => {
    const s = await setup({}, groupsOf, false);
    await click(s.inDoc('pos-menu-dish-steak'));
    await settle();
    expect(s.inDoc('pos-menu-dish-options-steak')).toBeNull();
    expect(s.reads()).toEqual([]);
    expect(s.button()).toContain('Añadir · 15,50 €');
  });
});
