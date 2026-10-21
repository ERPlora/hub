// `useTill()`: the check on screen and every write to it (SALE-F01, F09, F13–F18; spec «Cart → order
// mapping»). The first line opens the check (and the device remembers it); the next ones go to it; a
// second tap on the same product raises its line. One write in flight at a time per check. What the
// screen shows is what the operations answer (no money of its own); a refusal says the server's words.
import { toastError } from '@erplora/ui/shell';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { defineComponent, h } from 'vue';

import { EMPLOYEE, flush, MANAGER, mountSale } from '../../__tests__/mount-sale';
import { deferred, line, memoryStorage, order, product, refused, settings } from '../../components/pos/__tests__/fixtures';
import type { OrderOut, SettingsOut } from '../../operations';
import { CURRENT_CHECK_KEY } from './useCurrentCheck';
import { type Till, useTill } from './useTill';

vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/shell')>()),
  toastError: vi.fn(() => Promise.resolve()),
  toast: vi.fn(() => Promise.resolve()),
}));

beforeEach(() => vi.stubGlobal('localStorage', memoryStorage()));
afterEach(() => {
  vi.unstubAllGlobals();
  vi.mocked(toastError).mockClear();
});

async function setup(options: { settings?: Partial<SettingsOut>; session?: typeof MANAGER; locale?: 'en' | 'es' } = {}) {
  let till!: Till;
  const opened: string[] = [];
  const Probe = defineComponent({
    setup() {
      till = useTill({ settings: () => settings(options.settings), onOpened: (id) => opened.push(id) });
      return () => h('div');
    },
  });
  const m = await mountSale(Probe, { session: options.session, locale: options.locale });
  /** The server answers every write with `body` (an OrderOut by default). */
  const reply = (body: unknown) => m.net.onApi(() => Response.json(body));
  const calls = () => m.sent().map((c) => [c.path.replace('/api/sale/orders', ''), c.body]);
  return { ...m, till: () => till, reply, calls, opened };
}

const CHECK = order({ id: 'o1', version: 1, lines: [line({ id: 'l1', product_id: 'p1' })] });

describe('useTill: adding products', () => {
  it('the first product opens the check with it; the device remembers the check', async () => {
    const s = await setup();
    s.reply(CHECK);
    await s.till().addProduct(product({ id: 'p1' }), null);
    expect(s.calls()).toEqual([['', { lines: [{ product_id: 'p1' }] }]]);
    expect(s.till().order.value).toEqual(CHECK);
    expect(localStorage.getItem(CURRENT_CHECK_KEY)).toBe('o1');
    expect(s.opened).toEqual(['o1']);
  });

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

  it('one write at a time: two quick taps never open two checks', async () => {
    const s = await setup();
    const first = deferred();
    let count = 0;
    s.net.onApi(() => (++count === 1 ? first.promise : Response.json(order({ version: 2, lines: [line(), line({ id: 'l2', product_id: 'p2' })] }))));
    const a = s.till().addProduct(product({ id: 'p1' }), null);
    const b = s.till().addProduct(product({ id: 'p2' }), null);
    await flush();
    expect(s.calls()).toHaveLength(1);
    expect(s.till().busy.value).toBe(true);
    first.resolve(Response.json(CHECK));
    await Promise.all([a, b]);
    expect(s.calls()).toEqual([
      ['', { lines: [{ product_id: 'p1' }] }],
      ['/add_line', { order_id: 'o1', product_id: 'p2' }],
    ]);
    expect(s.till().busy.value).toBe(false);
  });

  it('a refused product says the server’s words and the check stays as it was', async () => {
    const s = await setup();
    s.net.onApi(() => refused('sale.product_not_available', 'That product is no longer in the catalogue.'));
    await s.till().addProduct(product({ id: 'p1' }), null);
    expect(toastError).toHaveBeenCalledExactlyOnceWith('That product is no longer in the catalogue.');
    expect(s.till().order.value).toBeNull();
  });

  it('nobody answering says «tap again»', async () => {
    const s = await setup();
    s.net.onApi(() => Promise.reject(new TypeError('Failed to fetch')));
    await s.till().addProduct(product({ id: 'p1' }), null);
    expect(toastError).toHaveBeenCalledExactlyOnceWith("Couldn't save that item — tap again");
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

describe('useTill: sending the round to the kitchen (SALE-F20, KITCHEN-F18)', () => {
  const SENT = order({ id: 'o1', version: 3, lines: [line({ id: 'l1', product_id: 'p1', round_no: 1, fired_at: '2026-10-20T12:00:00Z' })] });
  const TICKET = { id: 't1', number: 'K-0001', short_number: '1', round_no: 1 };
  const answer = (s: Awaited<ReturnType<typeof setup>>) =>
    s.net.onApi((call) => Response.json(call.url.startsWith('/api/kitchen/tickets/send') ? TICKET : SENT));

  it('asks Kitchen to send what is pending, normal or rush, then reads the check back with its round', async () => {
    const s = await setup();
    s.reply(CHECK);
    await s.till().addProduct(product({ id: 'p1' }), null);
    answer(s);
    expect(await s.till().sendToKitchen(true)).toEqual({ ok: true, round: 1, printed: true });
    const sent = s.sent().filter((c) => c.path === '/api/kitchen/tickets/send');
    expect(sent.map((c) => c.body)).toEqual([{ order_id: 'o1', priority: 'rush' }]);
    expect(s.till().order.value?.lines[0].round_no).toBe(1);
    await s.till().sendToKitchen(false);
    expect(s.sent().filter((c) => c.path === '/api/kitchen/tickets/send').at(-1)?.body).toEqual({ order_id: 'o1', priority: 'normal' });
  });

  it('says when the round went but its sheet did not print (hub#2257)', async () => {
    const s = await setup();
    s.reply(CHECK);
    await s.till().addProduct(product({ id: 'p1' }), null);
    s.net.onApi((call) =>
      Response.json(call.url.startsWith('/api/kitchen/tickets/send') ? { ...TICKET, print_error: 'no printer' } : SENT),
    );
    expect(await s.till().sendToKitchen(false)).toEqual({ ok: true, round: 1, printed: false });
  });

  it('hands the refusal back in the server’s words', async () => {
    const s = await setup();
    s.reply(CHECK);
    await s.till().addProduct(product({ id: 'p1' }), null);
    s.net.onApi(() => refused('sale.nothing_to_fire', 'There is nothing new to send to the kitchen.'));
    expect(await s.till().sendToKitchen(false)).toEqual({
      ok: false,
      message: 'There is nothing new to send to the kitchen.',
      code: 'sale.nothing_to_fire',
    });
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

  it('hands a refusal back to the sheet, in the server’s words', async () => {
    const s = await setup();
    s.net.onApi(() => refused('permission_denied', 'You do not have permission.', 403));
    expect(await s.till().addOpenLine({ unit_price: 300, department_id: 'd1', name: 'Fruit' }, null)).toEqual({
      ok: false,
      message: 'You do not have permission.',
    });
  });
});

describe('useTill: the lines', () => {
  async function withCheck(extra: Parameters<typeof setup>[0] = {}) {
    const s = await setup(extra);
    s.reply(CHECK);
    await s.till().addProduct(product({ id: 'p1' }), null);
    return s;
  }

  it('a quantity goes to the line; zero takes the line off', async () => {
    const s = await withCheck();
    await s.till().setQuantity(line({ id: 'l1' }), '0.532');
    await s.till().setQuantity(line({ id: 'l1' }), '0');
    expect(s.calls().slice(1)).toEqual([
      ['/update_line', { order_id: 'o1', line_id: 'l1', quantity: '0.532' }],
      ['/remove_line', { order_id: 'o1', line_id: 'l1' }],
    ]);
  });

  it('a refused quantity says why and the line stays as the server keeps it', async () => {
    const s = await withCheck();
    s.net.onApi(() => refused('sale.quantity_off_grid', 'Quantity doesn’t fit the product’s step'));
    await s.till().setQuantity(line({ id: 'l1' }), '0.5');
    expect(toastError).toHaveBeenCalledExactlyOnceWith('Quantity doesn’t fit the product’s step');
    expect(s.till().order.value).toEqual(CHECK);
  });

  it('comps a line with its reason, and takes the comp off', async () => {
    const s = await withCheck({ locale: 'es' });
    await s.till().toggleGift(line({ id: 'l1', is_gift: false }));
    await s.till().toggleGift(line({ id: 'l1', is_gift: true }));
    expect(s.calls().slice(1)).toEqual([
      ['/update_line', { order_id: 'o1', line_id: 'l1', is_gift: true, gift_reason: 'Invitación' }],
      ['/update_line', { order_id: 'o1', line_id: 'l1', is_gift: false, gift_reason: '' }],
    ]);
  });

  it('a note goes to the line and the sheet learns it went', async () => {
    const s = await withCheck();
    expect(await s.till().setNote(line({ id: 'l1' }), 'No ice')).toEqual({ ok: true });
    expect(s.calls().at(-1)).toEqual(['/update_line', { order_id: 'o1', line_id: 'l1', notes: 'No ice' }]);
  });

  it('moves a line to another professional; a refusal says it stays with the one it had', async () => {
    const s = await withCheck();
    await s.till().setLineStaff(line({ id: 'l1' }), 's3');
    expect(s.calls().at(-1)).toEqual(['/set_line_staff', { order_id: 'o1', line_id: 'l1', staff_id: 's3' }]);
    s.net.onApi(() => Promise.reject(new TypeError('Failed to fetch')));
    await s.till().setLineStaff(line({ id: 'l1' }), null);
    expect(toastError).toHaveBeenCalledWith('The line could not be moved to another professional. It stays with the one it had.');
  });

  it('voids a line sent to the kitchen with its reason', async () => {
    const s = await withCheck();
    expect(await s.till().voidLine(line({ id: 'l1' }), 'Sold out')).toEqual({ ok: true });
    expect(s.calls().at(-1)).toEqual(['/void_line', { order_id: 'o1', line_id: 'l1', reason: 'Sold out' }]);
  });
});

describe('useTill: discounts and the manager’s door', () => {
  async function withCheck(extra: Parameters<typeof setup>[0] = {}) {
    const s = await setup({ settings: { max_discount_percent: 15 }, ...extra });
    s.reply(CHECK);
    await s.till().addProduct(product({ id: 'p1' }), null);
    return s;
  }

  it('a line discount within the cap goes through the ordinary door', async () => {
    const s = await withCheck();
    expect(await s.till().setLineDiscount(line({ id: 'l1' }), '10')).toEqual({ ok: true });
    expect(s.calls().at(-1)).toEqual(['/set_line_discount', { order_id: 'o1', line_id: 'l1', discount_percent: '10' }]);
  });

  it('above the cap a manager goes through the manager’s door', async () => {
    const s = await withCheck();
    await s.till().setLineDiscount(line({ id: 'l1' }), '30');
    expect(s.calls().at(-1)).toEqual(['/set_line_discount_over_limit', { order_id: 'o1', line_id: 'l1', discount_percent: '30' }]);
  });

  it('above the cap an employee gets the server’s refusal', async () => {
    const s = await withCheck({ session: EMPLOYEE });
    s.net.onApi(() => refused('sale.discount_over_limit', 'That discount is over what this business allows without the manager.'));
    expect(await s.till().setLineDiscount(line({ id: 'l1' }), '30')).toEqual({
      ok: false,
      message: 'That discount is over what this business allows without the manager.',
    });
    expect(s.calls().at(-1)?.[0]).toBe('/set_line_discount');
  });

  it('a fixed ticket amount over the cap (the server says so) is retried through the manager’s door', async () => {
    const s = await withCheck();
    let count = 0;
    s.net.onApi(() => (++count === 1 ? refused('sale.discount_over_limit', 'Over the cap.') : Response.json(CHECK)));
    expect(await s.till().setTicketDiscount({ percent: '0', amount: 900 })).toEqual({ ok: true });
    expect(s.calls().slice(1)).toEqual([
      ['/set_discount', { order_id: 'o1', discount_percent: '0', discount_amount: 900 }],
      ['/set_discount_over_limit', { order_id: 'o1', discount_percent: '0', discount_amount: 900 }],
    ]);
  });
});

describe('useTill: the check', () => {
  it('a title typed with a check open is saved on it; a refusal says so', async () => {
    const s = await setup();
    s.reply(CHECK);
    await s.till().addProduct(product({ id: 'p1' }), null);
    await s.till().rename('Table 4');
    expect(s.calls().at(-1)).toEqual(['/set_label', { order_id: 'o1', label: 'Table 4' }]);
    s.net.onApi(() => Promise.reject(new TypeError('Failed to fetch')));
    await s.till().rename('Table 5');
    expect(toastError).toHaveBeenCalledWith('The check title could not be saved');
  });

  it('parks under a title and lets the screen go', async () => {
    const s = await setup();
    s.reply(CHECK);
    await s.till().addProduct(product({ id: 'p1' }), null);
    expect(await s.till().park('Ana')).toEqual({ ok: true });
    expect(s.calls().at(-1)).toEqual(['/set_label', { order_id: 'o1', label: 'Ana' }]);
    expect(s.till().order.value).toBeNull();
    expect(s.till().orderId.value).toBeNull();
    expect(localStorage.getItem(CURRENT_CHECK_KEY)).toBeNull();
  });

  it('a refused park keeps the check on screen', async () => {
    const s = await setup();
    s.reply(CHECK);
    await s.till().addProduct(product({ id: 'p1' }), null);
    s.net.onApi(() => Promise.reject(new TypeError('Failed to fetch')));
    expect(await s.till().park('Ana')).toEqual({ ok: false, message: 'The check could not be parked. It is still on screen.' });
    expect(s.till().orderId.value).toBe('o1');
  });

  it('voids the check on screen and lets it go', async () => {
    const s = await setup();
    s.reply(CHECK);
    await s.till().addProduct(product({ id: 'p1' }), null);
    expect(await s.till().voidCheck()).toEqual({ ok: true });
    expect(s.calls().at(-1)).toEqual(['/void', { order_id: 'o1' }]);
    expect(s.till().orderId.value).toBeNull();
  });

  it('resumes another check: the device remembers it and the live result brings it', async () => {
    const s = await setup();
    s.till().resume('o9');
    expect(s.till().orderId.value).toBe('o9');
    expect(localStorage.getItem(CURRENT_CHECK_KEY)).toBe('o9');
    s.till().follow(order({ id: 'o9', version: 4 }));
    expect(s.till().order.value?.id).toBe('o9');
  });
});

describe('useTill: following the check live', () => {
  async function withCheck() {
    const s = await setup({ locale: 'en' });
    s.reply(CHECK);
    await s.till().addProduct(product({ id: 'p1' }), null);
    return s;
  }

  it('takes a newer version and never goes back to an older one', async () => {
    const s = await withCheck();
    const newer: OrderOut = order({ id: 'o1', version: 3, lines: [line({ quantity: '3.000', line_total: 450 })] });
    s.till().follow(newer);
    s.till().follow(order({ id: 'o1', version: 2 }));
    expect(s.till().order.value).toEqual(newer);
  });

  it('ignores another check’s result', async () => {
    const s = await withCheck();
    s.till().follow(order({ id: 'o7', version: 9 }));
    expect(s.till().order.value?.id).toBe('o1');
  });

  it('a check closed on another device lets the screen go and says so', async () => {
    const s = await withCheck();
    s.till().follow(order({ id: 'o1', version: 5, status: 'completed' }));
    expect(s.till().orderId.value).toBeNull();
    expect(toastError).toHaveBeenCalledWith('That check was closed on another device: the screen starts a new one.');
  });

  it('a closed check arriving while this screen voids it is left to that write: no «closed on another device»', async () => {
    const s = await withCheck();
    const answer = deferred();
    s.net.onApi(() => answer.promise);
    const voiding = s.till().voidCheck();
    await flush();
    s.till().follow(order({ id: 'o1', version: 5, status: 'voided' }));
    expect(toastError).not.toHaveBeenCalled();
    answer.resolve(Response.json(order({ id: 'o1', version: 5, status: 'voided' })));
    expect(await voiding).toEqual({ ok: true });
    expect(s.till().orderId.value).toBeNull();
    expect(toastError).not.toHaveBeenCalled();
  });

  it('a check that no longer exists lets the screen go too', async () => {
    const s = await withCheck();
    s.till().gone();
    expect(s.till().orderId.value).toBeNull();
  });
});
