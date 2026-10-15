// Cart & Checkout → Carts (WORKBOOK «Pantallas · Carritos»; CART_CHECKOUT-F01, F05, F06, F12): the live
// `cart_checkout.cart.list` with the old table's Session, Email, Status, Items and Total, «Search session
// or email…», filters per column (session and email by fragment, the status by list, items and total
// from / to in the unit the column shows), newest first, 50 a page, list or cards. «New cart» opens the
// form; each row offers «Abandon» (an active cart only) and «Delete» (confirmed), only to whoever may.
// The old tests kept here: the create form lives behind the table's «+» (erp-cart-checkout-carts), the
// status filters by list, the total paints in the cart's own currency (cart_checkout#32), the range
// filters compare in the unit shown (cart_checkout#26) and a failed load offers Retry.
import { DataTable, type DataTableAction, EmptyState, InlineFeedback, StatusPill } from '@erplora/ui/components';
import { AppPage } from '@erplora/ui/shell';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import type { CartOut, CartStatus } from '../operations';
import { EMPLOYEE, errorFrame, flush, type MountOptions, mountCartCheckout, page } from '../__tests__/mount-cart-checkout';
import CartFormModal from '../components/CartFormModal.vue';
import CartsPage from './CartsPage.vue';

const mocks = vi.hoisted(() => ({ confirm: vi.fn() }));
vi.mock('@erplora/ui/components', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/components')>()),
  useConfirm: () => ({ confirm: mocks.confirm }),
}));
vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

afterEach(() => mocks.confirm.mockReset());

const OP = 'cart_checkout.cart.list';
const cart = (id: string, status: CartStatus, over: Partial<CartOut> = {}): CartOut => ({
  id,
  session_token: `sess_${id}`,
  customer_email: `${id}@example.com`,
  customer_name: 'Ana García',
  status,
  total_items: '2.000',
  total_amount: 3150,
  currency: 'EUR',
  expires_at: null,
  last_activity_at: null,
  notes: '',
  abandon_reason: '',
  created_by: 'Ana',
  updated_by: 'Ana',
  created_at: '2026-10-14T10:00:00Z',
  updated_at: '2026-10-14T10:00:00Z',
  ...over,
});
const ACTIVE = cart('a1', 'active');
const ABANDONED = cart('a2', 'abandoned', { customer_email: '' });
const CONVERTED = cart('a3', 'converted', { total_items: '0.500', total_amount: 1999, currency: 'JPY' });
const EXPIRED = cart('a4', 'expired');
const ROWS = [ACTIVE, ABANDONED, CONVERTED, EXPIRED];

async function setup(options: MountOptions = {}) {
  const m = await mountCartCheckout(CartsPage, { path: '/cart_checkout/carts', ...options });
  await m.live();
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const rows = () => m.wrapper.findAll('[data-testid="cart-checkout-carts-row"]');
  const cells = (i: number) => rows()[i].findAll('[role="cell"]').map((c) => c.text().trim());
  const action = (id: string) => prop<DataTableAction<CartOut>[]>('actions').find((a) => a.id === id)!;
  const offered = (row: CartOut) =>
    prop<DataTableAction<CartOut>[]>('actions')
      .filter((a) => !a.hidden?.(row))
      .map((a) => (typeof a.label === 'function' ? a.label(row) : a.label));
  return { ...m, table, prop, rows, cells, action, offered, list: () => m.params(OP), show: (data: unknown) => m.result(OP, data) };
}

describe('CartsPage', () => {
  it('follows the carts newest first, with the old table’s columns', async () => {
    const s = await setup();
    expect(s.list()).toEqual([{ sort: '-created_at', limit: 50, offset: 0 }]);
    await s.show(page(ROWS));
    expect(s.wrapper.findComponent(AppPage).props('title')).toBe('Carts');
    expect(s.prop('searchPlaceholder')).toBe('Search session or email…');
    expect(s.prop<{ add: string }>('labels').add).toBe('New cart');
    expect(s.prop<Array<{ key: string; label: string }>>('columns').map((c) => [c.key, c.label])).toEqual([
      ['session_token', 'Session'],
      ['customer_email', 'Email'],
      ['status', 'Status'],
      ['total_items', 'Items'],
      ['total_amount', 'Total'],
    ]);
    expect(s.cells(0).slice(0, 5)).toEqual(['sess_a1', 'a1@example.com', 'Active', '2', '€31.50']);
    // No email: a dash, as the old table.
    expect(s.cells(1)[1]).toBe('—');
  });

  it('paints each total in the cart’s own currency and the items without decorative zeros', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    expect(s.cells(2).slice(3, 5)).toEqual(['0.5', '¥1,999']);
  });

  it('paints every status as its pill', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    expect(s.wrapper.findAllComponents(StatusPill).map((p) => [p.props('label'), p.props('tone')])).toEqual([
      ['Active', 'info'],
      ['Abandoned', 'warning'],
      ['Converted', 'success'],
      ['Expired', 'neutral'],
    ]);
  });

  it('filters on the server: fragments, the status by list, items and total in the unit the column shows', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    const columns = s.prop<Array<{ key: string; filter?: { type: string; options?: Array<{ value: string; label: string }> } }>>('columns');
    expect(columns.map((c) => [c.key, c.filter?.type ?? null])).toEqual([
      ['session_token', 'text'],
      ['customer_email', 'text'],
      ['status', 'select'],
      ['total_items', 'range'],
      ['total_amount', 'range'],
    ]);
    expect(columns[2].filter?.options?.map((o) => [o.value, o.label])).toEqual([
      ['active', 'Active'],
      ['abandoned', 'Abandoned'],
      ['converted', 'Converted'],
      ['expired', 'Expired'],
    ]);
    s.table().vm.$emit('filtersChange', {
      session_token: 'sess',
      customer_email: 'ana',
      status: 'active',
      total_items_from: '2',
      total_items_to: '2,5',
      total_amount_from: '12',
      total_amount_to: '12,1',
    });
    await flush();
    expect(s.list()).toEqual([
      {
        session_token: 'sess',
        customer_email: 'ana',
        status: 'active',
        total_items_min: '2',
        total_items_max: '2.5',
        total_amount_min: 1200,
        total_amount_max: 1210,
        sort: '-created_at',
        limit: 50,
        offset: 0,
      },
    ]);
  });

  it('a bound that is not a number is left out, never «from 0»', async () => {
    const s = await setup();
    s.table().vm.$emit('filtersChange', { total_amount_from: 'abc', total_items_to: 'two' });
    await flush();
    expect(s.list()).toEqual([{ sort: '-created_at', limit: 50, offset: 0 }]);
  });

  it('searches and sorts on the server; none at all says «No carts.», a search without rows «No results»', async () => {
    const s = await setup();
    await s.show(page([]));
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No carts.');
    s.table().vm.$emit('sortChange', { sort: 'total_amount', dir: 'asc' });
    s.table().vm.$emit('update:search', 'sess_');
    await flush();
    expect(s.list()).toEqual([{ search: 'sess_', sort: 'total_amount', limit: 50, offset: 0 }]);
    await s.reopen();
    await s.show(page([]));
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No results');
  });

  it('a list that could not load says so in the table and Retry asks again', async () => {
    const s = await setup();
    s.net.lastStream().push(errorFrame(s.subId(OP), 'boom'));
    await flush();
    expect(s.prop('error')).toBe('The carts could not be loaded.');
    s.table().vm.$emit('retry');
    await flush();
    expect(s.list()).toHaveLength(1);
  });

  it('Abandon is offered on an active cart only, Delete on every one', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    expect(ROWS.map((row) => s.offered(row))).toEqual([['Abandon', 'Delete'], ['Delete'], ['Delete'], ['Delete']]);
  });

  it('Abandon sends its command; a refusal shows above the table', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    s.answer(200, { ...ACTIVE, status: 'abandoned' });
    s.table().vm.$emit('action', { actionId: 'abandon', row: ACTIVE });
    await flush();
    expect(s.sent().map((c) => [c.path, c.body])).toEqual([['/api/cart_checkout/carts/mark_abandoned', { cart_id: 'a1' }]]);
    const message = 'This cart no longer takes changes: it is Expired.';
    s.answer(409, { error: { code: 'cart_checkout.cart_not_active', message } });
    s.table().vm.$emit('action', { actionId: 'abandon', row: ACTIVE });
    await flush();
    const banner = s.wrapper.findAllComponents(InlineFeedback).find((b) => b.attributes('data-testid') === 'cart-checkout-carts-row-error');
    expect([banner?.props('heading'), banner?.text()]).toEqual(['Could not complete the action', expect.stringContaining(message)]);
  });

  it('a double tap on Abandon sends it once, and the row says it is running', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    s.answer(200, { ...ACTIVE, status: 'abandoned' });
    s.table().vm.$emit('action', { actionId: 'abandon', row: ACTIVE });
    s.table().vm.$emit('action', { actionId: 'abandon', row: ACTIVE });
    expect(s.action('abandon').loading?.(ACTIVE)).toBe(true);
    await flush();
    expect(s.sent()).toHaveLength(1);
    expect(s.action('abandon').loading?.(ACTIVE)).toBe(false);
  });

  it('Delete asks first and, confirmed, deletes; cancelled, sends nothing', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    mocks.confirm.mockResolvedValue(false);
    s.table().vm.$emit('action', { actionId: 'delete', row: CONVERTED });
    await flush();
    expect(mocks.confirm).toHaveBeenCalledWith({
      title: 'Delete the cart sess_a3?',
      message: 'It leaves the list. Its orders stay, and its session code can be used again.',
      confirmLabel: 'Delete',
      cancelLabel: 'Cancel',
      tone: 'danger',
    });
    expect(s.sent()).toEqual([]);
    mocks.confirm.mockResolvedValue(true);
    s.answer(200, CONVERTED);
    s.table().vm.$emit('action', { actionId: 'delete', row: CONVERTED });
    await flush();
    expect(s.sent().map((c) => [c.path, c.body])).toEqual([['/api/cart_checkout/carts/delete', { cart_id: 'a3' }]]);
  });

  it('«New cart» opens the form behind the table’s add; a cart created from a later page brings the list back to the first one', async () => {
    const s = await setup();
    await s.show(page(ROWS, 120));
    s.table().vm.$emit('pageChange', 2);
    await flush();
    expect(s.list()).toEqual([{ sort: '-created_at', limit: 50, offset: 100 }]);
    expect(s.prop('addable')).toBe(true);
    s.table().vm.$emit('add');
    await flush();
    const modal = s.wrapper.findComponent(CartFormModal);
    expect(modal.props('open')).toBe(true);
    modal.vm.$emit('created', ACTIVE);
    await flush();
    expect(s.list()).toEqual([{ sort: '-created_at', limit: 50, offset: 0 }]);
  });

  it('cards show the customer’s email, else the session code', async () => {
    const s = await setup();
    const title = s.prop<(row: CartOut) => string>('cardTitle');
    expect([title(ACTIVE), title(ABANDONED)]).toEqual(['a1@example.com', 'sess_a2']);
  });

  it('an employee only looks', async () => {
    const s = await setup({ session: EMPLOYEE });
    await s.show(page(ROWS));
    expect(s.prop('addable')).toBe(false);
    expect(ROWS.map((row) => s.offered(row))).toEqual([[], [], [], []]);
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.show(page(ROWS));
    expect(s.wrapper.findComponent(AppPage).props('title')).toBe('Carritos');
    expect([s.prop('searchPlaceholder'), s.prop<{ add: string }>('labels').add]).toEqual(['Buscar sesión o email…', 'Nuevo carrito']);
    expect(s.cells(0).slice(2, 5).map((cell) => cell.replace(/[  ]/g, ' '))).toEqual(['Activo', '2', '31,50 €']);
    expect(s.offered(ACTIVE)).toEqual(['Abandonar', 'Borrar']);
  });
});
