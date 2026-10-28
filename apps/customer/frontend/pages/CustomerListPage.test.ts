// Customers → Customers (WORKBOOK «Pantallas · Clientes»; CUSTOMER-F01, F02, F07, F08, F09): the four
// figures, then the live `customer.customer.list` in a server-side DataTable — Name, Email, Phone,
// Stage, Spent —, search on the server (name, phone, email, tax id, company), filters behind the table's
// funnel, sort by any
// column, 50 a page; «Add» and «Import CSV» to whoever manages cards, «Export CSV» to whoever exports;
// a row opens the card; «Delete» on a row (owner, admin) asks first. Every state of the screen.
import { DataTable, EmptyState, InlineFeedback } from '@erplora/ui/components';
import { AppPage, toastSuccess } from '@erplora/ui/shell';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import {
  business,
  BYE,
  EMPLOYEE,
  errorFrame,
  flush,
  JAPANESE,
  json,
  MANAGER,
  type MountOptions,
  mountCustomer,
  POLISH,
  sent,
  subId,
  VIEWER,
} from '../__tests__/mount-customer';
import CustomerCreateModal from '../components/CustomerCreateModal.vue';
import CustomerExportButton from '../components/CustomerExportButton.vue';
import CustomerStats from '../components/CustomerStats.vue';
import ImportReport from '../components/ImportReport.vue';
import { formatMoney } from '../lib/money';
import CustomerListPage from './CustomerListPage.vue';
import source from './CustomerListPage.vue?raw';
import { listFillProblems } from '../../../../frontend/testing/list-fill';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});
vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...((await importOriginal()) as object),
  toastSuccess: vi.fn(() => Promise.resolve()),
}));

const row = (id: string, name: string, extra: Record<string, unknown> = {}) => ({
  id,
  name,
  email: `${id}@x.es`,
  phone: '+34600111222',
  tax_id: '',
  company_name: '',
  lifecycle_stage: 'active',
  source: 'walk_in',
  is_active: true,
  total_purchases: 2,
  total_spent: 4550,
  last_purchase_at: null,
  ...extra,
});
const PAGE = { rows: [row('c1', 'Ana García'), row('c2', 'Luis', { lifecycle_stage: 'vip' })], total: 2, limit: 50, offset: 0 };
const EMPTY = { rows: [], total: 0, limit: 50, offset: 0 };
const LIST = 'customer.customer.list';

afterEach(() => {
  document.body.innerHTML = '';
});
beforeEach(() => vi.mocked(toastSuccess).mockClear());

async function setup(options: MountOptions = {}) {
  const m = await mountCustomer(CustomerListPage, { attachTo: document.body, ...options });
  const call = await m.live();
  const testid = (id: string) => m.wrapper.find(`[data-testid="${id}"]`);
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const rows = () => m.wrapper.findAll('[data-testid="customer-list-row"]');
  const show = (page: unknown, rev?: number) => m.result(call, LIST, page, rev);
  async function showOnNewStream(page: unknown) {
    await m.clock.advance(150);
    await m.result(m.net.lastStream(), LIST, page);
  }
  async function search(text: string) {
    const bar = testid('customer-list-search').element as HTMLElement & { value?: string };
    bar.value = text;
    bar.dispatchEvent(new CustomEvent('ionInput', { detail: { value: text } }));
    await flush();
  }
  async function filter(values: Record<string, string>) {
    table().vm.$emit('update:filters', values);
    await flush();
  }
  return { ...m, call, testid, table, prop, rows, show, showOnNewStream, search, filter };
}

describe('CustomerListPage: the screen', () => {
  it('on a phone the card names the row once: its title stands for the Name column (customers#95)', async () => {
    const s = await setup();
    expect(s.prop('cardTitleColumn')).toBe('name');
  });

  it('is «Customers» with the four section tabs', async () => {
    const s = await setup();
    const page = s.wrapper.findComponent(AppPage);
    expect(page.props('title')).toBe('Customers');
    expect((page.props('tabs') as { id: string; to: string }[]).map((t) => [t.id, t.to])).toEqual([
      ['customers', '/customer/customers'],
      ['groups', '/customer/groups'],
      ['tags', '/customer/tags'],
      ['fields', '/customer/fields'],
    ]);
    expect(page.props('tabsLabel')).toBe('Customer sections');
  });

  it('shows the four figures above the table', async () => {
    const s = await setup();
    await s.show(PAGE);
    const stats = s.wrapper.findComponent(CustomerStats);
    expect(stats.exists()).toBe(true);
    expect(stats.element.compareDocumentPosition(s.table().element) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('follows customer.customer.list: 50 by name from the first, the spinner until the first result', async () => {
    const s = await setup();
    expect(s.params(LIST)).toEqual([{ sort: 'name', descending: false, limit: 50, offset: 0 }]);
    expect(s.testid('customer-list-loading').exists()).toBe(true);
    await s.show(PAGE);
    expect(s.table().props()).toMatchObject({
      serverSide: true,
      searchable: true,
      rowClickable: true,
      testid: 'customer-list',
      pageSize: 50,
      total: 2,
      sort: 'name',
      sortDir: 'asc',
      views: ['table', 'cards'],
    });
  });

  it('paints Name, Email, Phone, Stage and Spent (money), each sortable on the server', async () => {
    const s = await setup();
    await s.show(PAGE);
    const columns = s.prop<{ key: string; label: string; sortable?: boolean }[]>('columns');
    expect(columns.map((c) => [c.key, c.label, c.sortable])).toEqual([
      ['name', 'Name', true],
      ['email', 'Email', true],
      ['phone', 'Phone', true],
      ['lifecycle_stage', 'Stage', true],
      ['total_spent', 'Spent', true],
    ]);
    expect(s.rows().map((r) => r.attributes('data-id'))).toEqual(['c1', 'c2']);
    expect(s.wrapper.findAll('[data-testid="customer-list-stage"]').map((c) => c.text())).toEqual(['Active', 'VIP']);
    expect(s.wrapper.findAll('[data-testid="customer-list-phone"]').map((c) => c.text())).toEqual(['+34 600 111 222', '+34 600 111 222']);
    expect(s.wrapper.findAll('[data-testid="customer-list-spent"]').map((c) => c.text())).toEqual([
      formatMoney(4550, 'en'),
      formatMoney(4550, 'en'),
    ]);
  });

  it('a header click sorts on the server, from the first page', async () => {
    const s = await setup();
    await s.show(PAGE);
    s.table().vm.$emit('sortChange', { sort: 'total_spent', dir: 'desc' });
    await flush();
    expect(s.params(LIST)).toEqual([{ sort: 'total_spent', descending: true, limit: 50, offset: 0 }]);
  });

  it('searches on the server with the trimmed text (a phone however it is typed)', async () => {
    const s = await setup();
    await s.show(PAGE);
    expect((s.testid('customer-list-search').element as HTMLElement & { placeholder?: string }).placeholder).toBe(
      'Search name, phone or email…',
    );
    await s.search(' 600 111 222 ');
    expect(s.params(LIST)).toEqual([{ search: '600 111 222', sort: 'name', descending: false, limit: 50, offset: 0 }]);
    await s.showOnNewStream(EMPTY);
    const empty = s.wrapper.findComponent(EmptyState);
    expect([empty.props('heading'), empty.props('message')]).toEqual(['No results', 'No customer matches your search or filters.']);
  });

  it('filters behind the table funnel: stage and spent (euros, as typed) on their columns, then source and active', async () => {
    // flow: ninguno — FIX DataTable parte 2b-1 (PLAN-MIGRATIONS §13: filtros como en la vieja)
    const s = await setup();
    await s.show(PAGE);
    expect(s.prop('filterable')).toBe(true);
    type Filter = { type: string; key?: string; keys?: string[]; amount?: boolean; label?: string; options?: Array<{ value: string; label: string }> };
    const columns = s.prop<Array<{ key: string; label: string; filter?: Filter }>>('columns');
    expect(columns.filter((c) => c.filter).map((c) => [c.label, c.filter?.key ?? c.key, c.filter?.type, c.filter?.keys, c.filter?.amount])).toEqual([
      ['Stage', 'lifecycle_stage', 'select', undefined, undefined],
      ['Spent', 'total_spent', 'range', ['spent_from', 'spent_to'], true],
    ]);
    expect(columns.find((c) => c.key === 'lifecycle_stage')?.filter?.options?.map((o) => o.label)).toEqual([
      'Lead',
      'Prospect',
      '1st purchase',
      'Active',
      'At risk',
      'Dormant',
      'Churned',
      'VIP',
    ]);
    const fields = s.prop<Filter[]>('filterFields');
    expect(fields.map((f) => [f.key, f.label, f.type])).toEqual([
      ['source', 'Source', 'select'],
      ['is_active', 'Active', 'select'],
    ]);
    expect(fields[0].options?.map((o) => o.value)).toEqual(['walk_in', 'phone', 'whatsapp', 'website', 'social', 'referral', 'import', 'other']);
    expect(fields[1].options).toEqual([
      { value: 'true', label: 'Active' },
      { value: 'false', label: 'Not active' },
    ]);
  });

  it('the funnel panel applies on «Apply», reads «1.000» as a thousand euros and counts the filters in use', async () => {
    const s = await setup();
    await s.show(PAGE);
    await s.testid('customer-list-filters-toggle').trigger('click');
    await flush();
    const panel = s.testid('customer-list-filters-panel');
    const set = (name: string, event: string, value: string) =>
      panel.get(`[data-testid="customer-list-filter-${name}"]`).element.dispatchEvent(new CustomEvent(event, { detail: { value } }));
    set('lifecycle_stage', 'ionChange', 'vip');
    set('spent_from', 'ionInput', '1.000');
    set('is_active', 'ionChange', 'false');
    await flush();
    expect(s.params(LIST), 'the panel edits a draft: nothing is asked before «Apply»').toEqual([{ sort: 'name', descending: false, limit: 50, offset: 0 }]);
    await panel.get('[data-testid="customer-list-filters-apply"]').trigger('click');
    await flush();
    expect(s.params(LIST)).toEqual([
      { lifecycle_stage: 'vip', is_active: false, spent_min: 100000, sort: 'name', descending: false, limit: 50, offset: 0 },
    ]);
    expect(s.testid('customer-list-filters-count').text()).toBe('3');
  });

  it('filters by stage, source, active and spent (euros → cents), from the first page', async () => {
    const s = await setup();
    await s.show({ ...PAGE, total: 200 });
    s.table().vm.$emit('pageChange', 2);
    await flush();
    await s.filter({ lifecycle_stage: 'vip', source: 'import', spent_from: '10', spent_to: '10,5' });
    expect(s.params(LIST)).toEqual([
      { lifecycle_stage: 'vip', source: 'import', spent_min: 1000, spent_max: 1050, sort: 'name', descending: false, limit: 50, offset: 0 },
    ]);
  });

  it('«Export CSV» exports with the search and the filters in use', async () => {
    const s = await setup();
    await s.show(PAGE);
    await s.search('ana');
    await s.filter({ is_active: 'true', spent_to: '20' });
    expect(s.wrapper.findComponent(CustomerExportButton).props('filters')).toEqual({
      search: 'ana',
      is_active: true,
      spent_max: 2000,
      sort: 'name',
      descending: false,
    });
  });

  it('on a phone, «Load more» grows the list without any query asking for more than 100 rows', async () => {
    const s = await setup();
    await s.show({ ...PAGE, total: 400 });
    for (let i = 0; i < 4; i++) s.table().vm.$emit('loadMore');
    await flush();
    const params = s.params(LIST) as { limit: number; offset: number }[];
    expect(params.map((p) => [p.offset, p.limit]).sort((a, b) => a[0] - b[0])).toEqual([
      [0, 100],
      [100, 100],
      [200, 50],
    ]);
  });

  it('an amount it cannot read is said under its field, and neither filters nor makes the list look filtered', async () => {
    const s = await setup();
    await s.show(PAGE);
    expect(s.prop('filterErrors')).toEqual({});
    await s.filter({ spent_from: 'mil' });
    expect(s.prop('filterErrors')).toEqual({ spent_from: 'Write an amount, like 1.000,50.' });
    expect(s.params(LIST)).toEqual([{ sort: 'name', descending: false, limit: 50, offset: 0 }]);
    await s.show(EMPTY, 2);
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No customers.');
  });

  it('a row opens the customer\'s card', async () => {
    const s = await setup();
    await s.show(PAGE);
    await s.rows()[1].trigger('click');
    await flush();
    expect(s.router.currentRoute.value.path).toBe('/customer/customers/c2');
  });

  it('with no customers yet invites to add or import them', async () => {
    const s = await setup();
    await s.show(EMPTY);
    const empty = s.wrapper.findComponent(EmptyState);
    expect([empty.props('heading'), empty.props('message'), empty.props('icon')]).toEqual([
      'No customers.',
      'Add the first one with «Add» or bring yours with «Import CSV».',
      'people-outline',
    ]);
  });

  it('on an error the table says so with the server message and Retry', async () => {
    const s = await setup();
    s.call.push(errorFrame(subId(s.client, LIST), 'boom'));
    await flush();
    expect(s.prop('error')).toBe('msg boom');
    expect(s.wrapper.get('[data-role="load-error"]').text()).toContain('The customers could not be loaded');
    const reconnect = vi.spyOn(s.client.stream, 'reconnect');
    await s.testid('customer-list-retry').trigger('click');
    expect(reconnect).toHaveBeenCalledOnce();
  });

  it('when the app is not active says so, without the table', async () => {
    const s = await setup();
    s.call.push(errorFrame(subId(s.client, LIST), 'app_inactive'));
    await flush();
    const banner = s.wrapper.findAllComponents(InlineFeedback).find((b) => b.attributes('data-testid') === 'customer-list-inactive')!;
    expect(banner.props('heading')).toBe('This app is not active in this business');
    expect(s.table().exists()).toBe(false);
  });

  it('while the stream reconnects keeps the rows and shows «Reconnecting…»', async () => {
    const s = await setup();
    await s.show(PAGE);
    s.call.push(BYE);
    await flush();
    expect(s.testid('customer-list-reconnecting').text()).toBe('Reconnecting…');
    expect(s.rows()).toHaveLength(2);
  });
});

describe('CustomerListPage: actions by permission', () => {
  it('the owner gets «Add», «Import CSV», «Export CSV» and «Delete» on each row', async () => {
    const s = await setup();
    await s.show(PAGE);
    expect(s.testid('customer-list-add').text()).toBe('Add');
    expect(s.testid('customer-import').exists()).toBe(true);
    expect(s.testid('customer-export').exists()).toBe(true);
    expect(s.prop<{ id: string }[]>('actions').map((a) => a.id)).toEqual(['open', 'delete']);
  });

  it('the employee views, adds and imports, but neither exports nor deletes (role_permissions)', async () => {
    const s = await setup({ session: EMPLOYEE });
    await s.show(PAGE);
    expect(s.testid('customer-list-add').exists()).toBe(true);
    expect(s.testid('customer-import').exists()).toBe(true);
    expect(s.testid('customer-export').exists()).toBe(false);
    expect(s.prop<{ id: string }[]>('actions').map((a) => a.id)).toEqual(['open']);
  });

  it('the manager exports but does not delete', async () => {
    const s = await setup({ session: MANAGER });
    await s.show(PAGE);
    expect(s.testid('customer-export').exists()).toBe(true);
    expect(s.prop<{ id: string }[]>('actions').map((a) => a.id)).toEqual(['open']);
  });

  it('who only views gets no «Add» nor «Import CSV», and no invitation to add', async () => {
    const s = await setup({ session: VIEWER });
    await s.show(EMPTY);
    expect(s.testid('customer-list-add').exists()).toBe(false);
    expect(s.testid('customer-import').exists()).toBe(false);
    expect(s.wrapper.findComponent(EmptyState).props('message')).toBeUndefined();
  });

  it('«Add» opens «New customer»', async () => {
    const s = await setup();
    await s.show(PAGE);
    expect(s.wrapper.findComponent(CustomerCreateModal).props('open')).toBe(false);
    await s.testid('customer-list-add').trigger('click');
    expect(s.wrapper.findComponent(CustomerCreateModal).props('open')).toBe(true);
  });

  it('«Delete» on a row asks first, then deletes and says so (F07)', async () => {
    const s = await setup();
    await s.show(PAGE);
    s.net.onApi(() => json({ id: 'c1' }));
    s.table().vm.$emit('action', { actionId: 'delete', row: PAGE.rows[0] });
    await flush();
    const dialog = document.querySelector('[data-testid="customer-delete-confirm"]');
    expect(dialog?.textContent).toContain(
      'Delete Ana García? They no longer show in the list, at the till or in the search by phone. Their sales are kept.',
    );
    expect(s.net.api).toHaveLength(0);
    document.querySelector<HTMLElement>('[data-testid="customer-delete-confirm-submit"]')!.click();
    await flush();
    expect(sent(s.net.api[0])).toMatchObject({ path: '/api/customer/customers/delete', body: { id: 'c1' } });
    expect(toastSuccess).toHaveBeenCalledWith('Customer Ana García deleted');
  });

  it('«View» on a row opens the card', async () => {
    const s = await setup();
    await s.show(PAGE);
    s.table().vm.$emit('action', { actionId: 'open', row: PAGE.rows[0] });
    await flush();
    expect(s.router.currentRoute.value.path).toBe('/customer/customers/c1');
  });
});

describe('CustomerListPage: import (F08)', () => {
  it('a picked file is imported, says «Importing…» meanwhile and leaves its report above the table', async () => {
    const s = await setup();
    await s.show(PAGE);
    let release!: (r: Response) => void;
    s.net.onApi(() => new Promise<Response>((r) => (release = r)));
    s.wrapper.findComponent({ name: 'CustomerImportButton' }).vm.$emit('pick', new File(['name\nAna\n'], 'c.csv'));
    await flush();
    expect(s.testid('customer-list-importing').text()).toBe('Importing…');
    release(json({ created: 1, skipped: 0, rows: [{ index: 0, id: 'n1', errors: {}, warnings: {} }] }));
    await flush();
    expect(s.testid('customer-list-importing').exists()).toBe(false);
    const report = s.wrapper.findComponent(ImportReport);
    expect(report.props('report')).toMatchObject({ total: 1, created: 1 });
    report.vm.$emit('close');
    await flush();
    expect(s.wrapper.findComponent(ImportReport).exists()).toBe(false);
  });

  it('a file without customers is told so', async () => {
    const s = await setup();
    await s.show(PAGE);
    s.wrapper.findComponent({ name: 'CustomerImportButton' }).vm.$emit('pick', new File(['foo\n1\n'], 'c.csv'));
    await flush();
    await flush();
    expect(s.testid('customer-list-import-problem').text()).toContain('The file has no customers');
  });
});

describe('CustomerListPage: the business\'s currency (customer-business-currency)', () => {
  const BUSINESS = 'base.business.get';
  const plain = (text: string) => text.replace(/\s/g, ' ');
  const spent = (s: Awaited<ReturnType<typeof setup>>) =>
    s.wrapper.findAll('[data-testid="customer-list-spent"]').map((c) => plain(c.text()));

  it('a business in Poland sees «Spent» in złoty, never in euros', async () => {
    const s = await setup({ locale: 'es' });
    await s.result(s.call, BUSINESS, business(POLISH));
    await s.show(PAGE);
    expect(spent(s)).toEqual(['45,50 zł', '45,50 zł']);
    expect(s.wrapper.text()).not.toContain('€');
  });

  it('a business in Spain still sees euros', async () => {
    const s = await setup();
    await s.result(s.call, BUSINESS, business());
    await s.show(PAGE);
    expect(spent(s)).toEqual(['€45.50', '€45.50']);
  });

  it('until the business answers, «Spent» is a figure without a symbol, never euros', async () => {
    const s = await setup();
    await s.show(PAGE);
    expect(spent(s)).toEqual(['45.50', '45.50']);
  });

  it('«Spent» is typed in the business\'s currency: złoty with its symbol, yen without decimals', async () => {
    const s = await setup();
    await s.result(s.call, BUSINESS, business(POLISH));
    await s.show(PAGE);
    await s.filter({ spent_from: '12,50 zł', spent_to: 'PLN 100' });
    expect(s.params(LIST)).toEqual([{ spent_min: 1250, spent_max: 10000, sort: 'name', descending: false, limit: 50, offset: 0 }]);

    const yen = await setup();
    await yen.result(yen.call, BUSINESS, business(JAPANESE));
    await yen.show(PAGE);
    await yen.filter({ spent_from: '1250', spent_to: '12,5' });
    expect(yen.params(LIST)).toEqual([{ spent_min: 1250, sort: 'name', descending: false, limit: 50, offset: 0 }]);
    expect(yen.prop('filterErrors')).toEqual({ spent_to: 'Write an amount, like 1.000,50.' });
    expect(spent(yen)).toEqual(['¥4,550', '¥4,550']);
  });

  it('an amount typed before the business answers is read again in its currency when it does', async () => {
    const s = await setup();
    await s.show(PAGE);
    await s.filter({ spent_from: '1250' });
    expect(s.params(LIST)).toEqual([{ spent_min: 125000, sort: 'name', descending: false, limit: 50, offset: 0 }]);
    await s.result(s.call, BUSINESS, business(JAPANESE));
    await s.showOnNewStream(PAGE);
    expect(s.params(LIST)).toEqual([{ spent_min: 1250, sort: 'name', descending: false, limit: 50, offset: 0 }]);
  });
});

describe('CustomerListPage: language and markup', () => {
  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.show(PAGE);
    expect(s.wrapper.findComponent(AppPage).props('title')).toBe('Clientes');
    expect(s.prop<{ label: string }[]>('columns').map((c) => c.label)).toEqual(['Nombre', 'Email', 'Teléfono', 'Etapa', 'Gastado']);
    expect(s.testid('customer-list-add').text()).toBe('Añadir');
    expect(s.wrapper.get('[data-testid="customer-list-stage"]').text()).toBe('Activo');
    const fields = s.prop<Array<{ label: string; options?: Array<{ label: string }> }>>('filterFields');
    expect(fields.map((f) => f.label)).toEqual(['Origen', 'Activo']);
    expect(fields[1].options?.map((o) => o.label)).toEqual(['Activos', 'No activos']);
    await s.filter({ spent_to: 'mil' });
    expect(s.prop('filterErrors')).toEqual({ spent_to: 'Escribe un importe, como 1.000,50.' });
  });

  it('has no OutfitKit tag and formats nothing by hand', () => {
    expect(source).not.toMatch(/<ok[-]/);
    expect(source).not.toMatch(/Intl\.|toLocale|toFixed|new Date\(/);
  });
});

describe('CustomerListPage: the list fills the page (FIX-DATATABLE-HUB)', () => {
  it('AppPage `fill` and its DataTable `fill`, only stacks between them: from the topbar to the tabbar', async () => {
    const s = await setup();
    expect(listFillProblems(s.wrapper)).toEqual([]);
  });
});
