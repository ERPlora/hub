// flow: SALE-F12 — the menus on the till's grid (COMBO-F07): Menus' menus on sale (`combo.combo.for_sale`, live, up
// to 50), first in «All», each tile marked «Menu» with its name and closed price; a tap hands the menu up. A failed
// read says so with «Retry»; Menus off (or not readable) shows nothing and the products sell as before.
import { describe, expect, it } from 'vitest';

import type { SaleComboOut } from '../../../../combo/frontend/operations';
import { click, errorFrame, mountSale } from '../../__tests__/mount-sale';
import { plain } from '../../lib/format';
import { page } from './__tests__/fixtures';
import ComboTiles from './ComboTiles.vue';

const OP = 'combo.combo.for_sale';

const menu = (over: Partial<SaleComboOut> = {}): SaleComboOut => ({
  id: 'm1',
  name: 'Menú del día',
  kitchen_name: 'MENU',
  price: 1350,
  supply_kind: 'service',
  sort_order: 0,
  groups: [],
  ...over,
});

async function setup() {
  const m = await mountSale(ComboTiles, { locale: 'es' });
  await m.live();
  return m;
}

describe('ComboTiles', () => {
  it('follows the menus on sale and paints a tile each, marked «Menú», with its closed price', async () => {
    const s = await setup();
    expect(s.params(OP)).toEqual([{ limit: 50 }]);
    await s.result(OP, page([menu(), menu({ id: 'm2', name: 'Menú infantil', price: 900 })], 2));
    const tile = s.find('pos-menu-m1');
    expect(tile.text()).toContain('Menú del día');
    expect(s.find('pos-menu-m1-badge').text()).toBe('Menú');
    expect(plain(tile.text())).toContain('13,50 €');
    expect(s.find('pos-menu-m2').exists()).toBe(true);
  });

  it('a tap hands the menu up', async () => {
    const s = await setup();
    await s.result(OP, page([menu()]));
    await click(s.find('pos-menu-m1').element);
    expect(s.wrapper.emitted('pick')).toEqual([[menu()]]);
  });

  it('a failed read says so with «Retry»', async () => {
    const s = await setup();
    s.net.lastStream().push(errorFrame(s.subId(OP), 'internal_error'));
    await s.reopen();
    expect(s.find('pos-menus-error').text()).toContain('No se han podido leer los menús.');
    expect(s.find('pos-menus-retry').exists()).toBe(true);
  });

  it('Menus off shows nothing: the products sell as before', async () => {
    const s = await setup();
    s.net.lastStream().push(errorFrame(s.subId(OP), 'app_inactive'));
    await s.reopen();
    expect(s.find('pos-menus-error').exists()).toBe(false);
    expect(s.wrapper.findAll('[data-testid^="pos-menu-"]').length).toBe(0);
  });
});
