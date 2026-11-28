// Sales & POS → Sell: what the catalogue adds besides a product (the services of Services, an open price, the options
// of Modifiers, the menus of Menus) and its VeriFactu notice.
import { toast, toastError, toastWarning } from '@erplora/ui/shell';
import { describe, expect, it, vi } from 'vitest';

import { click, EMPLOYEE, MANAGER, settle } from '../__tests__/mount-sale';
import { CHECK, freshEachTest, setup } from '../__tests__/pos-page';
import OpenPriceSheet from '../components/pos/OpenPriceSheet.vue';
import PosCatalog from '../components/pos/PosCatalog.vue';
import ServicePriceSheet from '../components/pos/ServicePriceSheet.vue';
import { line, memoryStorage, order, product, refused, service } from '../components/pos/__tests__/fixtures';

freshEachTest();

describe('PosPage: services of Services (SALE-F38)', () => {
  /** Services is on in this business and the person reads its catalog. */
  const WITH_SERVICES = { ...MANAGER, permissions: [...MANAGER.permissions, 'service.view_service'], apps: [{ label: 'service', state: 'on' as const }] };
  const SERVICE_CHECK = order({ id: 'o1', version: 1, lines: [line({ id: 'l1', product_id: null, service_id: 'sv1', is_service: true })] });

  it('the catalogue offers the services with Services on, the setting on and the permission to read them', async () => {
    const on = await setup({ session: WITH_SERVICES });
    expect(on.wrapper.findComponent(PosCatalog).props('showServices')).toBe(true);
    const hidden = await setup({ session: WITH_SERVICES, settings: { show_services: false } });
    expect(hidden.wrapper.findComponent(PosCatalog).props('showServices')).toBe(false);
    const off = await setup({ session: { ...WITH_SERVICES, apps: [] } });
    expect(off.wrapper.findComponent(PosCatalog).props('showServices')).toBe(false);
    const blind = await setup({ session: { ...WITH_SERVICES, permissions: MANAGER.permissions } });
    expect(blind.wrapper.findComponent(PosCatalog).props('showServices')).toBe(false);
  });

  it('a fixed-price service opens the check with it', async () => {
    const s = await setup({ session: WITH_SERVICES });
    s.reply(SERVICE_CHECK);
    s.wrapper.findComponent(PosCatalog).vm.$emit('service', service({ id: 'sv1' }));
    await settle();
    expect(s.writes()).toEqual([['/api/sale/orders', { service_lines: [{ service_id: 'sv1' }] }]]);
  });

  it('a service without a fixed price asks its amount first, then adds it and closes the sheet', async () => {
    const s = await setup({ session: WITH_SERVICES });
    const colour = service({ id: 'sv2', name: 'Color', pricing_type: 'from', price: 6500 });
    s.wrapper.findComponent(PosCatalog).vm.$emit('service', colour);
    await settle();
    const sheet = s.wrapper.findComponent(ServicePriceSheet);
    expect(sheet.props()).toMatchObject({ open: true, service: colour });
    expect(s.writes()).toEqual([]);
    s.reply(SERVICE_CHECK);
    sheet.vm.$emit('add', 7000);
    await settle();
    expect(s.writes()).toEqual([['/api/sale/orders', { service_lines: [{ service_id: 'sv2', unit_price: 7000 }] }]]);
    expect(s.wrapper.findComponent(ServicePriceSheet).props('open')).toBe(false);
  });

  it('a refused amount stays in the sheet in the server’s words', async () => {
    const s = await setup({ session: WITH_SERVICES });
    s.wrapper.findComponent(PosCatalog).vm.$emit('service', service({ id: 'sv2', pricing_type: 'variable' }));
    await settle();
    s.net.onApi(() => Response.json({ error: { code: 'sale.service_price_out_of_range', message: 'Out of range.' } }, { status: 409 }));
    s.wrapper.findComponent(ServicePriceSheet).vm.$emit('add', 100);
    await settle();
    expect(s.wrapper.findComponent(ServicePriceSheet).props()).toMatchObject({ open: true, error: 'Out of range.' });
  });

  it('a refused fixed-price service says why in a toast', async () => {
    const s = await setup({ session: WITH_SERVICES });
    s.net.onApi(() => Response.json({ error: { code: 'sale.service_not_available', message: 'Not offered.' } }, { status: 409 }));
    s.wrapper.findComponent(PosCatalog).vm.$emit('service', service({ id: 'sv1' }));
    await settle();
    expect(toastError).toHaveBeenCalledWith('Not offered.');
  });
});

describe('PosPage: open price', () => {
  it('an employee opens the sheet too: a manager approves the open price when it is added', async () => {
    const s = await setup({ session: EMPLOYEE });
    s.wrapper.findComponent(PosCatalog).vm.$emit('openPrice');
    await settle();
    expect(toast).not.toHaveBeenCalled();
    expect(toastWarning).not.toHaveBeenCalled();
    expect(s.wrapper.findComponent(OpenPriceSheet).props('open')).toBe(true);
  });

  it('with it, the sheet adds an open-price line and closes', async () => {
    const s = await setup();
    s.wrapper.findComponent(PosCatalog).vm.$emit('openPrice');
    await settle();
    expect(s.wrapper.findComponent(OpenPriceSheet).props('open')).toBe(true);
    s.reply(CHECK);
    s.wrapper.findComponent(OpenPriceSheet).vm.$emit('add', { unit_price: 300, department_id: 'd1', name: 'Fruit' });
    await settle();
    expect(s.writes()).toEqual([['/api/sale/orders', { open_lines: [{ unit_price: 300, department_id: 'd1', name: 'Fruit' }] }]]);
    expect(s.wrapper.findComponent(OpenPriceSheet).props('open')).toBe(false);
  });
});

describe('PosPage: the options of Modifiers (SALE-F11)', () => {
  /** Modifiers is on in this business and the person reads its groups. */
  const WITH_MODIFIERS = { ...MANAGER, permissions: [...MANAGER.permissions, 'modifier.view'], apps: [{ label: 'modifier', state: 'on' as const }] };
  const EXTRAS = {
    product_id: 'p1',
    product_name: 'Burger',
    groups: [
      {
        id: 'g1',
        name: 'Extras',
        kitchen_name: '',
        min_choices: 0,
        max_choices: 0,
        allow_repeat: false,
        is_required: false,
        options: [{ id: 'cheese', name: 'Cheese', kitchen_name: '', price_delta: 100, tax_category_key: null, is_default: false }],
      },
    ],
  };
  const forTarget = (s: Awaited<ReturnType<typeof setup>>) => s.sent().filter((c) => c.path === '/api/modifier/groups/for_target');

  it('without Modifiers on (or without the right to read it) a product goes straight to the check, nothing asked', async () => {
    for (const session of [MANAGER, { ...WITH_MODIFIERS, permissions: MANAGER.permissions }]) {
      vi.stubGlobal('localStorage', memoryStorage());
      const s = await setup({ session });
      await s.addProduct();
      expect(forTarget(s)).toEqual([]);
      expect(s.writes()).toEqual([['/api/sale/orders', { lines: [{ product_id: 'p1' }] }]]);
    }
  });

  it('a product with groups opens the sheet and adds nothing until «Add»; then the line carries the ids', async () => {
    const s = await setup({ session: WITH_MODIFIERS });
    s.net.onApi((call) => (call.url.startsWith('/api/modifier/groups/for_target') ? Response.json(EXTRAS) : Response.json(CHECK)));
    s.wrapper.findComponent(PosCatalog).vm.$emit('add', product({ id: 'p1', name: 'Burger', price: 800 }));
    await settle();
    expect(forTarget(s).map((c) => c.query)).toEqual([{ product_id: 'p1' }]);
    expect(s.writes()).toEqual([]);
    expect(s.inDoc('pos-options-title')?.textContent).toContain('Burger');
    await click(s.inDoc('pos-option-cheese'));
    await click(s.inDoc('pos-options-add'));
    await settle();
    expect(s.writes()).toEqual([['/api/sale/orders', { lines: [{ product_id: 'p1', option_ids: ['cheese'] }] }]]);
  });

  it('a product without groups goes straight to the check', async () => {
    const s = await setup({ session: WITH_MODIFIERS });
    s.net.onApi((call) => (call.url.startsWith('/api/modifier/groups/for_target') ? Response.json({ ...EXTRAS, groups: [] }) : Response.json(CHECK)));
    s.wrapper.findComponent(PosCatalog).vm.$emit('add', product({ id: 'p1' }));
    await settle();
    expect(s.writes()).toEqual([['/api/sale/orders', { lines: [{ product_id: 'p1' }] }]]);
    expect(s.inDoc('pos-options-title')).toBeNull();
  });

  it('when the groups cannot be read (a proxy’s error page) nothing is added and the till says so', async () => {
    const s = await setup({ session: WITH_MODIFIERS, locale: 'es' });
    s.net.onApi((call) => (call.url.startsWith('/api/modifier/groups/for_target') ? new Response('Bad gateway', { status: 502 }) : Response.json(CHECK)));
    s.wrapper.findComponent(PosCatalog).vm.$emit('add', product({ id: 'p1' }));
    await settle();
    expect(s.writes()).toEqual([]);
    expect(toastError).toHaveBeenCalledWith('No se han podido leer los suplementos de este producto. Inténtalo de nuevo.');
  });
});

describe('PosPage: the menus of Menus (SALE-F12)', () => {
  /** Menus is on in this business and the person reads it. */
  const WITH_MENUS = { ...MANAGER, permissions: [...MANAGER.permissions, 'combo.view'], apps: [{ label: 'combo', state: 'on' as const }] };
  const MENU = {
    id: 'm1',
    name: 'Menu of the day',
    kitchen_name: 'MENU',
    price: 1350,
    supply_kind: 'service' as const,
    sort_order: 0,
    groups: [
      {
        id: 'mains',
        name: 'Mains',
        min_choices: 1,
        max_choices: 1,
        allow_repeat: false,
        options: [{ id: 'hake', product_id: 'p9', product_name: 'Hake', sku: '', price_delta: 0 }],
      },
    ],
  };

  it('without Menus on (or without the right to read it) the till offers no menus', async () => {
    for (const session of [MANAGER, { ...WITH_MENUS, permissions: MANAGER.permissions }]) {
      vi.stubGlobal('localStorage', memoryStorage());
      const s = await setup({ session });
      expect(s.wrapper.findComponent(PosCatalog).props('showCombos')).toBe(false);
    }
  });

  it('a menu tapped opens its sheet and adds nothing until «Add»; then the check opens with the menu and its dishes', async () => {
    const s = await setup({ session: WITH_MENUS });
    expect(s.wrapper.findComponent(PosCatalog).props('showCombos')).toBe(true);
    s.reply(CHECK);
    s.wrapper.findComponent(PosCatalog).vm.$emit('combo', MENU);
    await settle();
    expect(s.writes()).toEqual([]);
    expect(s.inDoc('pos-menu-title')?.textContent).toContain('Menu of the day');
    await click(s.inDoc('pos-menu-dish-hake'));
    await click(s.inDoc('pos-menu-add'));
    await settle();
    expect(s.writes()).toEqual([['/api/sale/orders', { combo_lines: [{ combo_id: 'm1', choices: [{ option_id: 'hake', quantity: 1 }] }] }]]);
    expect(s.inDoc('pos-menu-title')).toBeNull();
  });

  it('Menus’ refusal stays on the sheet, over its button', async () => {
    const s = await setup({ session: WITH_MENUS });
    s.net.onApi(() => refused('combo.option_sold_out', '«Hake» is sold out.'));
    s.wrapper.findComponent(PosCatalog).vm.$emit('combo', MENU);
    await settle();
    await click(s.inDoc('pos-menu-dish-hake'));
    await click(s.inDoc('pos-menu-add'));
    await settle();
    expect(s.inDoc('pos-menu-error')?.textContent).toContain('«Hake» is sold out.');
  });
});

describe('PosPage: the VeriFactu notice (SALE-F07)', () => {
  const WITH_VERIFACTU = { ...MANAGER, permissions: [...MANAGER.permissions, 'verifactu.view_record'], apps: [{ label: 'verifactu', state: 'on' as const }] };

  it('the catalogue follows VeriFactu only with it on and the right to read it', async () => {
    for (const [session, on] of [
      [MANAGER, false],
      [{ ...WITH_VERIFACTU, permissions: MANAGER.permissions }, false],
      [WITH_VERIFACTU, true],
    ] as const) {
      vi.stubGlobal('localStorage', memoryStorage());
      const s = await setup({ session });
      expect(s.wrapper.findComponent(PosCatalog).props('fiscal')).toBe(on);
    }
  });
});
