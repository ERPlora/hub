import { describe, expect, it } from 'vitest';

import { EMPLOYEE } from '../../__tests__/mount-sale';
import { answers, asks, CHECK, freshEachTest, setup } from '../../__tests__/till';
import { line, order, product, refused } from '../../components/pos/__tests__/fixtures';

freshEachTest();

describe('useTill: adding products', () => {
  it('seals the line with the chosen professional and opens with the title typed before', async () => {
    const s = await setup();
    s.reply(CHECK);
    await s.till().rename('Ana — terrace');
    expect(s.calls()).toEqual([]);
    await s.till().addProduct(product({ id: 'p1' }), 's1');
    expect(s.calls()).toEqual([['', { label: 'Ana — terrace', lines: [{ product_id: 'p1', staff_id: 's1' }] }]]);
  });

  it('a second tap on the same product raises its line; another professional gets a line of its own', async () => {
    const s = await setup();
    s.reply(CHECK);
    await s.till().addProduct(product({ id: 'p1' }), null);
    await s.till().addProduct(product({ id: 'p1' }), null);
    await s.till().addProduct(product({ id: 'p1' }), 's2');
    expect(s.calls().slice(1)).toEqual([
      ['/update_line', { order_id: 'o1', line_id: 'l1', quantity: '2' }],
      ['/add_line', { order_id: 'o1', product_id: 'p1', staff_id: 's2' }],
    ]);
  });
});

describe('useTill: the options of Modifiers (SALE-F11)', () => {
  const WITH_CHEESE = order({
    id: 'o1',
    version: 1,
    lines: [line({ id: 'l1', product_id: 'p1', modifiers: [pick('cheese')] })],
  });

  function pick(option_id: string) {
    return { option_id, group_id: 'g1', group_name: 'Extras', name: option_id, kitchen_name: option_id, price_delta: 100, tax_category_key: null, own_line: false };
  }

  it('opens the check with the options chosen, in the order chosen, and sends only their ids', async () => {
    const s = await setup();
    s.reply(WITH_CHEESE);
    await s.till().addProduct(product({ id: 'p1' }), null, ['cheese', 'rare', 'cheese']);
    expect(s.calls()).toEqual([['', { lines: [{ product_id: 'p1', option_ids: ['cheese', 'rare', 'cheese'] }] }]]);
  });

  it('a line with options never raises another, and a tap without options does not raise one with them', async () => {
    const s = await setup();
    s.reply(WITH_CHEESE);
    await s.till().addProduct(product({ id: 'p1' }), null, ['cheese']);
    await s.till().addProduct(product({ id: 'p1' }), null, ['cheese']);
    await s.till().addProduct(product({ id: 'p1' }), null);
    expect(s.calls().slice(1)).toEqual([
      ['/add_line', { order_id: 'o1', product_id: 'p1', option_ids: ['cheese'] }],
      ['/add_line', { order_id: 'o1', product_id: 'p1' }],
    ]);
  });
});

describe('useTill: the menus of Menus (SALE-F12)', () => {
  const MENU_CHECK = order({ id: 'o1', version: 1, lines: [line({ id: 'l1', product_id: null, name: 'Menu of the day' })] });
  const PICKS = [
    { option_id: 'lentils', quantity: 1 },
    { option_id: 'hake', quantity: 1 },
  ];

  it('opens the check with the menu and its dishes; only the choices travel, Menus prices them', async () => {
    const s = await setup();
    s.reply(MENU_CHECK);
    const result = await s.till().addComboLine({ id: 'm1' }, null, PICKS);
    expect(result).toEqual({ ok: true });
    expect(s.calls()).toEqual([['', { combo_lines: [{ combo_id: 'm1', choices: PICKS }] }]]);
  });

  it('adds every menu as a line of its own, never raising the one before', async () => {
    const s = await setup();
    s.reply(MENU_CHECK);
    await s.till().addComboLine({ id: 'm1' }, null, PICKS);
    await s.till().addComboLine({ id: 'm1' }, 'st1', PICKS);
    expect(s.calls().slice(1)).toEqual([
      ['/add_combo_line', { order_id: 'o1', combo_id: 'm1', choices: PICKS, staff_id: 'st1' }],
    ]);
  });

  it('hands Menus’ refusal back to the sheet instead of a toast', async () => {
    const s = await setup();
    s.reply(MENU_CHECK);
    await s.till().addComboLine({ id: 'm1' }, null, PICKS);
    s.net.onApi(() => refused('combo.option_sold_out', '«Flan» is sold out.'));
    const result = await s.till().addComboLine({ id: 'm1' }, null, PICKS);
    expect(result).toEqual({ ok: false, message: '«Flan» is sold out.' });
  });
});

describe('useTill: services of Services (SALE-F38)', () => {
  const SERVICE_CHECK = order({ id: 'o1', version: 1, lines: [line({ id: 'l1', product_id: null, service_id: 's1', is_service: true })] });

  it('opens the check with the service, adds the next one, and a second tap of a fixed-price service raises its line', async () => {
    const s = await setup();
    s.reply(SERVICE_CHECK);
    expect(await s.till().addService({ id: 's1' }, null)).toEqual({ ok: true });
    expect(await s.till().addService({ id: 's1' }, 'st1')).toEqual({ ok: true });
    expect(await s.till().addService({ id: 's1' }, null)).toEqual({ ok: true });
    expect(await s.till().addService({ id: 's2' }, null, 6500)).toEqual({ ok: true });
    expect(s.calls()).toEqual([
      ['', { service_lines: [{ service_id: 's1' }] }],
      ['/add_service_line', { order_id: 'o1', service_id: 's1', staff_id: 'st1' }],
      ['/update_line', { order_id: 'o1', line_id: 'l1', quantity: '2' }],
      ['/add_service_line', { order_id: 'o1', service_id: 's2', unit_price: 6500 }],
    ]);
  });

  it('hands a refusal back in the server’s words', async () => {
    const s = await setup();
    s.net.onApi(() => refused('sale.service_price_out_of_range', 'That amount is outside what the service allows (40.00 € – 90.00 €).'));
    expect(await s.till().addService({ id: 's2' }, null, 1000)).toEqual({
      ok: false,
      message: 'That amount is outside what the service allows (40.00 € – 90.00 €).',
    });
  });
});

describe('useTill: open price', () => {
  it('opens the check with the open-price line, or adds it to the one there is', async () => {
    const s = await setup();
    s.reply(CHECK);
    const first = await s.till().addOpenLine({ unit_price: 300, department_id: 'd1', name: 'Fruit' }, 's1');
    const second = await s.till().addOpenLine({ unit_price: 500, tax_category_key: 'food', name: 'Food' }, null);
    expect(first).toEqual({ ok: true });
    expect(second).toEqual({ ok: true });
    expect(s.calls()).toEqual([
      ['', { open_lines: [{ unit_price: 300, department_id: 'd1', name: 'Fruit', staff_id: 's1' }] }],
      ['/add_open_line', { order_id: 'o1', unit_price: 500, tax_category_key: 'food', name: 'Food' }],
    ]);
  });

  it('an employee’s open price on the check is added once a manager approves it with their PIN', async () => {
    const s = await setup({ session: EMPLOYEE });
    s.reply(CHECK);
    await s.till().addProduct(product({ id: 'p1' }), null);
    s.net.onApi(answers(asks('sale.order.add_open_line', 'Sell at an open price')));
    expect(await s.till().addOpenLine({ unit_price: 500, tax_category_key: 'food', name: 'Food' }, null)).toEqual({ ok: true });
    const body = { order_id: 'o1', unit_price: 500, tax_category_key: 'food', name: 'Food' };
    expect(s.calls().slice(1)).toEqual([
      ['/add_open_line', body],
      ['/add_open_line', body],
    ]);
  });

  it('with no check yet, an employee opens it empty and the open price waits for the manager’s approval', async () => {
    const s = await setup({ session: EMPLOYEE });
    s.net.onApi(answers(Response.json(order({ id: 'o1', version: 1, lines: [] })), asks('sale.order.add_open_line', 'Sell at an open price')));
    expect(await s.till().addOpenLine({ unit_price: 300, department_id: 'd1', name: 'Fruit' }, 's1')).toEqual({ ok: true });
    expect(s.calls()).toEqual([
      ['', {}],
      ['/add_open_line', { order_id: 'o1', unit_price: 300, department_id: 'd1', name: 'Fruit', staff_id: 's1' }],
      ['/add_open_line', { order_id: 'o1', unit_price: 300, department_id: 'd1', name: 'Fruit', staff_id: 's1' }],
    ]);
    expect(s.opened).toEqual(['o1']);
  });

  it('hands a refusal back to the sheet, in the server’s words', async () => {
    const s = await setup();
    s.net.onApi(() => refused('permission_denied', 'You do not have permission.', 403));
    expect(await s.till().addOpenLine({ unit_price: 300, department_id: 'd1', name: 'Fruit' }, null)).toEqual({
      ok: false,
      message: 'You do not have permission.',
    });
  });
});
