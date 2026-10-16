// Taxes → Categories (TAX-F01, F02; the WORKBOOK's screens): the live `tax.category.list` in a
// server-side DataTable — Key, Name, Description, Origin, Active and the rate in force today —,
// search «Search key or name…», filters by Key, Name, Description and Origin, sort by any column,
// 50 a page sorted by key; «+» opens «New tax category» for whoever can manage; every state of the
// screen (loading, empty, no results, error with Retry, reconnecting, app inactive, read-only) and
// the tabbar of the three sections.
import { DataTable, EmptyState } from '@erplora/ui/components';
import { AppPage } from '@erplora/ui/shell';
import { describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import type { CategoryRowOut } from '../operations';
import { BYE, EMPLOYEE, errorFrame, flush, type MountOptions, mountTax } from '../__tests__/mount-tax';
import CategoryCreateModal from '../components/CategoryCreateModal.vue';
import FilterPanel from '../components/FilterPanel.vue';
import CategoriesPage from './CategoriesPage.vue';
import source from './CategoriesPage.vue?raw';
import { listFillProblems } from '../../../../frontend/testing/list-fill';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const OP = 'tax.category.list';

const category = (key: string, over: Partial<CategoryRowOut> = {}): CategoryRowOut => ({
  id: key,
  key,
  name: key,
  description: '',
  display_name: key,
  display_description: '',
  is_system: true,
  is_active: true,
  rate_pct: '21.00',
  operation_class: 'subject',
  ...over,
});

const PAGE = {
  rows: [
    category('restaurant.food', { name: 'Restaurant — food', display_name: 'Restauración — comida', rate_pct: '10.00' }),
    category('service.health', { display_name: 'Service — health', display_description: 'Exempt (art. 20)', rate_pct: '0.00', operation_class: 'exempt' }),
    category('product.books', { display_name: 'Books', is_system: false, rate_pct: null, operation_class: null }),
  ],
  total: 3,
  limit: 50,
  offset: 0,
};
const EMPTY = { rows: [], total: 0, limit: 50, offset: 0 };

async function setup(options: MountOptions = {}) {
  const m = await mountTax(CategoriesPage, options);
  const call = await m.live();
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const rows = () => m.wrapper.findAll('[data-testid="tax-categories-row"]');
  /** The params of the list's subscription (the only one of this page). */
  const params = () => m.params(OP);
  const show = (page: unknown) => m.result(OP, page);
  async function showOnNewStream(page: unknown) {
    await m.reopen();
    await m.result(OP, page);
  }
  async function filter(values: Record<string, string>) {
    m.wrapper.findComponent(FilterPanel).vm.$emit('update:modelValue', values);
    await flush();
  }
  return { ...m, call, table, prop, rows, params, show, showOnNewStream, filter };
}

describe('CategoriesPage: the live list', () => {
  it('follows tax.category.list, 50 sorted by key from the first, with the spinner until the first result', async () => {
    const s = await setup();
    expect(s.params()).toEqual([{ sort: 'key', dir: 'asc', limit: 50, offset: 0 }]);
    expect(s.find('tax-categories-loading').exists()).toBe(true);
    await s.show(PAGE);
    expect(s.find('tax-categories-loading').exists()).toBe(false);
    expect(s.table().props()).toMatchObject({ serverSide: true, searchable: true, testid: 'tax-categories', pageSize: 50, total: 3, page: 0, views: ['table', 'cards'] });
    expect(s.prop('searchPlaceholder')).toBe('Search key or name…');
  });

  it('sits under «Taxes» with the tabbar of the three sections', async () => {
    const s = await setup();
    const page = s.wrapper.findComponent(AppPage);
    expect(page.props('title')).toBe('Taxes');
    expect(page.props('tabsLabel')).toBe('Tax sections');
    expect((page.props('tabs') as Array<{ id: string; to: string }>).map((t) => [t.id, t.to])).toEqual([
      ['categories', '/tax/categories'],
      ['rules', '/tax/rules'],
      ['aliases', '/tax/aliases'],
    ]);
  });

  it('paints Key, Name, Description, Origin, Active and the rate in force today, one row per category', async () => {
    const s = await setup();
    await s.show(PAGE);
    expect(s.prop<Array<{ key: string; label: string }>>('columns').map((c) => [c.key, c.label])).toEqual([
      ['key', 'Key'],
      ['display_name', 'Name'],
      ['display_description', 'Description'],
      ['is_system', 'Origin'],
      ['is_active', 'Active'],
      ['rate_pct', 'Rate today'],
    ]);
    expect(s.rows().map((r) => r.attributes('data-id'))).toEqual(['restaurant.food', 'service.health', 'product.books']);
    const text = (i: number) => s.rows()[i].findAll('[role="cell"]').map((c) => c.text().trim());
    expect(text(0)).toEqual(['restaurant.food', 'Restauración — comida', '—', 'System', 'Yes', '10.00%']);
    expect(text(1)).toEqual(['service.health', 'Service — health', 'Exempt (art. 20)', 'System', 'Yes', 'Exempt']);
    expect(text(2)).toEqual(['product.books', 'Books', '—', 'Custom', 'Yes', '—']);
    expect(s.rows()[0].find('[data-testid="tax-category-system"] ion-icon').exists()).toBe(true);
  });

  it('every column sorts on the server but the rate; a new sort starts from the first page', async () => {
    const s = await setup();
    await s.show(PAGE);
    expect(s.prop<Array<{ key: string; sortable?: boolean }>>('columns').map((c) => [c.key, !!c.sortable])).toEqual([
      ['key', true],
      ['display_name', true],
      ['display_description', true],
      ['is_system', true],
      ['is_active', true],
      ['rate_pct', false],
    ]);
    s.table().vm.$emit('sortChange', { sort: 'display_name', dir: 'desc' });
    await flush();
    expect(s.params()).toEqual([{ sort: 'display_name', dir: 'desc', limit: 50, offset: 0 }]);
    expect([s.prop('sort'), s.prop('sortDir')]).toEqual(['display_name', 'desc']);
  });

  it('searches on the server, trimmed; an empty answer says «No results»', async () => {
    const s = await setup();
    await s.show(PAGE);
    s.table().vm.$emit('update:search', '  comida ');
    await flush();
    expect(s.params()).toEqual([{ search: 'comida', sort: 'key', dir: 'asc', limit: 50, offset: 0 }]);
    await s.showOnNewStream(EMPTY);
    const empty = s.wrapper.findComponent(EmptyState);
    expect([empty.attributes('data-testid'), empty.props('heading'), empty.props('message')]).toEqual([
      'tax-categories-empty',
      'No results',
      'Nothing matches your search or filters.',
    ]);
  });

  it('with no category at all says «No tax categories.»', async () => {
    const s = await setup();
    await s.show(EMPTY);
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No tax categories.');
  });

  it('pages on the server and counts «categories» in the footer', async () => {
    const s = await setup();
    await s.show({ ...PAGE, total: 120 });
    await s.find('tax-categories-page-next').trigger('click');
    await flush();
    expect(s.params()).toEqual([{ sort: 'key', dir: 'asc', limit: 50, offset: 50 }]);
    expect(s.prop('entityLabel')).toEqual({ one: 'category', many: 'categories' });
  });
});

describe('CategoriesPage: the filters (Key, Name, Description, Origin)', () => {
  it('offers them in the filters dialog, Origin as System or Custom', async () => {
    const s = await setup();
    await s.show(PAGE);
    const panel = s.wrapper.findComponent(FilterPanel);
    expect(panel.props('testid')).toBe('tax-categories');
    expect(
      (panel.props('filters') as Array<{ key: string; label: string; kind: string; options?: unknown; maxlength?: number }>).map((f) => [
        f.key,
        f.label,
        f.kind,
        f.options ?? f.maxlength ?? null,
      ]),
    ).toEqual([
      // As long as the schema takes each one (CategoryListIn): a longer text would be a 422.
      ['key', 'Key', 'text', 80],
      ['display_name', 'Name', 'text', 255],
      ['display_description', 'Description', 'text', 1000],
      [
        'is_system',
        'Origin',
        'select',
        [
          { value: 'true', label: 'System' },
          { value: 'false', label: 'Custom' },
        ],
      ],
    ]);
  });

  it('filters on the server from the first page, Origin as a yes/no; no filter left, back to all', async () => {
    const s = await setup();
    await s.show({ ...PAGE, total: 120 });
    await s.find('tax-categories-page-next').trigger('click');
    await flush();
    await s.filter({ key: 'restaurant', is_system: 'false' });
    expect(s.params()).toEqual([{ key: 'restaurant', is_system: false, sort: 'key', dir: 'asc', limit: 50, offset: 0 }]);
    await s.showOnNewStream(EMPTY);
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No results');
    await s.filter({ is_system: 'true' });
    expect(s.params()).toEqual([{ is_system: true, sort: 'key', dir: 'asc', limit: 50, offset: 0 }]);
    await s.filter({});
    expect(s.params()).toEqual([{ sort: 'key', dir: 'asc', limit: 50, offset: 0 }]);
  });
});

describe('CategoriesPage: a filter the server refuses (422)', () => {
  it('goes under its filter; the table keeps its rows and is not replaced by an error', async () => {
    const s = await setup();
    await s.show(PAGE);
    await s.filter({ key: 'x' });
    await s.reopen();
    const refused = { code: 'invalid_payload', message: 'Some fields are not valid.', fields: { key: 'String should have at most 80 characters' } };
    s.net.lastStream().push(`event: error\ndata: ${JSON.stringify({ id: s.subId(OP), error: refused })}\n\n`);
    await flush();
    expect(s.wrapper.findComponent(FilterPanel).props('fieldErrors')).toEqual({ key: 'String should have at most 80 characters' });
    expect(s.prop('error')).toBeUndefined();
    expect(s.wrapper.find('[data-role="load-error"]').exists()).toBe(false);
    expect(s.rows()).toHaveLength(3);
  });
});

describe('CategoriesPage on a phone: «Load more» never asks for more than 100 rows at once', () => {
  it('grows in windows of at most 100, each a subscription', async () => {
    const s = await setup();
    await s.show({ ...PAGE, total: 400 });
    s.table().vm.$emit('pageSizeChange', 100);
    await flush();
    s.table().vm.$emit('loadMore');
    s.table().vm.$emit('loadMore');
    await flush();
    await s.reopen();
    expect(s.params().map((p) => [p.limit, p.offset])).toEqual([
      [100, 0],
      [100, 100],
      [100, 200],
    ]);
  });
});

describe('CategoriesPage: the states of the screen', () => {
  it('on an error the table says so with the server message and Retry, which reopens the stream', async () => {
    const s = await setup();
    s.call.push(errorFrame(s.subId(OP), 'tax.boom'));
    await flush();
    expect(s.prop('error')).toBe('msg tax.boom');
    expect(s.wrapper.get('[data-role="load-error"]').text()).toContain('The tax categories could not be loaded');
    const reconnect = vi.spyOn(s.client.stream, 'reconnect');
    await s.find('tax-categories-retry').trigger('click');
    expect(reconnect).toHaveBeenCalledOnce();
  });

  it('when the app is not active says so instead of the table', async () => {
    const s = await setup();
    s.call.push(errorFrame(s.subId(OP), 'app_inactive'));
    await flush();
    expect(s.find('tax-categories-inactive').text()).toContain('This app is not active in this business');
    expect(s.table().exists()).toBe(false);
  });

  it('while the stream reconnects keeps the rows and shows «Reconnecting…»', async () => {
    const s = await setup();
    await s.show(PAGE);
    s.call.push(BYE);
    await flush();
    expect(s.find('tax-categories-reconnecting').text()).toBe('Reconnecting…');
    expect(s.rows()).toHaveLength(3);
  });
});

describe('CategoriesPage: who may create (TAX-F02)', () => {
  it('a manager gets «+» (Add), which opens «New tax category»', async () => {
    const s = await setup();
    await s.show(PAGE);
    expect(s.find('tax-categories-readonly').exists()).toBe(false);
    const modal = s.wrapper.findComponent(CategoryCreateModal);
    expect(modal.props('open')).toBe(false);
    await s.find('tax-categories-add').trigger('click');
    await flush();
    expect(s.wrapper.findComponent(CategoryCreateModal).props('open')).toBe(true);
  });

  it('an employee only looks: the read-only notice, no «+», no dialog', async () => {
    const s = await setup({ session: EMPLOYEE });
    await s.show(EMPTY);
    expect(s.find('tax-categories-readonly').text()).toBe('You can view the tax rules but not change them.');
    expect(s.find('tax-categories-add').exists()).toBe(false);
    expect(s.wrapper.findComponent(CategoryCreateModal).exists()).toBe(false);
  });
});

describe('CategoriesPage: the rest', () => {
  it('names its cards after the category a person reads', async () => {
    const s = await setup();
    await s.show(PAGE);
    const title = s.prop<(row: CategoryRowOut) => string>('cardTitle');
    expect(PAGE.rows.map(title)).toEqual(['Restauración — comida', 'Service — health', 'Books']);
  });

  it('has no OutfitKit tag and formats nothing by hand', () => {
    expect(source).not.toMatch(/<ok[-]/);
    expect(source).not.toMatch(/Intl\.|toLocale|new Date\(/);
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    expect(s.wrapper.findComponent(AppPage).props('title')).toBe('Impuestos');
    await s.show(PAGE);
    expect(s.prop<Array<{ label: string }>>('columns').map((c) => c.label)).toEqual(['Clave', 'Nombre', 'Descripción', 'Origen', 'Activa', 'Tipo vigente']);
    expect(s.rows()[1].findAll('[role="cell"]').map((c) => c.text().trim())).toEqual([
      'service.health',
      'Service — health',
      'Exempt (art. 20)',
      'Sistema',
      'Sí',
      'Exenta',
    ]);
    // The rate as a Spanish reader writes it, not «10.00%».
    expect(s.rows()[0].findAll('[role="cell"]').at(-1)?.text().replace(/[\u00a0\u202f]/g, ' ')).toBe('10,00 %');
    expect(s.prop('searchPlaceholder')).toBe('Buscar clave o nombre…');
    expect(s.find('tax-categories-add').text()).toBe('Añadir');
  });
});

describe('CategoriesPage: the list fills the page (FIX-DATATABLE-HUB)', () => {
  it('AppPage `fill` and its DataTable `fill`, only stacks between them: from the topbar to the tabbar', async () => {
    const s = await setup();
    expect(listFillProblems(s.wrapper)).toEqual([]);
  });
});
