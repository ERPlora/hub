// Taxes → Aliases (TAX-F13, F14; the WORKBOOK's screens): the live `tax.alias.list` in a server-side
// DataTable — Alias, Category, Origin («Shipped» or «Learned») and Active —, search «Search alias or
// category…», filters by Alias, Category and Origin, sort by any column; «+» with «New category alias»
// for whoever can manage; every state of the screen.
import { DataTable, EmptyState } from '@erplora/ui/components';
import { AppPage } from '@erplora/ui/shell';
import { describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import type { AliasOut, CategoryRowOut } from '../operations';
import { BYE, EMPLOYEE, errorFrame, flush, type MountOptions, mountTax } from '../__tests__/mount-tax';
import AliasCreateModal from '../components/AliasCreateModal.vue';
import FilterPanel from '../components/FilterPanel.vue';
import AliasesPage from './AliasesPage.vue';
import source from './AliasesPage.vue?raw';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const OP = 'tax.alias.list';

const alias = (id: string, text: string, key: string, source: 'shipped' | 'learned'): AliasOut => ({
  id,
  alias: text,
  tax_category_key: key,
  tax_category_name: key,
  source,
  is_active: true,
});
const PAGE = { rows: [alias('a1', 'beer', 'restaurant.alcohol', 'shipped'), alias('a2', 'comida', 'restaurant.food', 'learned')], total: 2, limit: 50, offset: 0 };
const EMPTY = { rows: [], total: 0, limit: 50, offset: 0 };
const category = (key: string, display: string): CategoryRowOut => ({
  id: key,
  key,
  name: display,
  description: '',
  display_name: display,
  display_description: '',
  is_system: true,
  is_active: true,
  rate_pct: null,
  operation_class: null,
});
const CATEGORIES = { rows: [category('restaurant.food', 'Restauración — comida')], total: 1, limit: 100, offset: 0 };

async function setup(options: MountOptions = {}) {
  const m = await mountTax(AliasesPage, { path: '/tax/aliases', ...options });
  const call = await m.live();
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const rows = () => m.wrapper.findAll('[data-testid="tax-aliases-row"]');
  const listParams = () => m.params(OP);
  const show = (page: unknown) => m.result(OP, page);
  async function showOnNewStream(page: unknown) {
    await m.reopen();
    await m.result(OP, page);
  }
  async function filter(values: Record<string, string>) {
    m.wrapper.findComponent(FilterPanel).vm.$emit('update:modelValue', values);
    await flush();
  }
  return { ...m, call, table, prop, rows, listParams, show, showOnNewStream, filter };
}

describe('AliasesPage: the live list', () => {
  it('follows tax.alias.list sorted by alias, 50 from the first, and the categories for its pickers', async () => {
    const s = await setup();
    expect(s.listParams()).toEqual([{ sort: 'alias', dir: 'asc', limit: 50, offset: 0 }]);
    expect(s.params('tax.category.list')).toEqual([{ sort: 'display_name', dir: 'asc', limit: 50 }]);
    expect(s.find('tax-aliases-loading').exists()).toBe(true);
    await s.show(PAGE);
    expect(s.table().props()).toMatchObject({ serverSide: true, searchable: true, testid: 'tax-aliases', total: 2, views: ['table', 'cards'] });
    expect(s.prop('searchPlaceholder')).toBe('Search alias or category…');
    expect(s.prop('entityLabel')).toEqual({ one: 'alias', many: 'aliases' });
    expect(s.wrapper.findComponent(AppPage).props('title')).toBe('Taxes');
  });

  it('paints Alias, Category, Origin and Active; every column sorts on the server', async () => {
    const s = await setup();
    await s.show(PAGE);
    expect(s.prop<Array<{ key: string; label: string; sortable?: boolean }>>('columns').map((c) => [c.key, c.label, !!c.sortable])).toEqual([
      ['alias', 'Alias', true],
      ['tax_category_key', 'Category', true],
      ['source', 'Source', true],
      ['is_active', 'Active', true],
    ]);
    expect(s.rows().map((r) => r.findAll('[role="cell"]').map((c) => c.text().trim()))).toEqual([
      ['beer', 'restaurant.alcohol', 'Shipped', 'Yes'],
      ['comida', 'restaurant.food', 'Learned', 'Yes'],
    ]);
    s.table().vm.$emit('sortChange', { sort: 'source', dir: 'desc' });
    await flush();
    expect(s.listParams()).toEqual([{ sort: 'source', dir: 'desc', limit: 50, offset: 0 }]);
    expect(s.prop<(row: AliasOut) => string>('cardTitle')(PAGE.rows[0])).toBe('beer');
  });

  it('searches on the server; an empty answer says «No results», no alias at all «No category aliases.»', async () => {
    const s = await setup();
    await s.show(EMPTY);
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No category aliases.');
    s.table().vm.$emit('update:search', ' beer ');
    await flush();
    expect(s.listParams()).toEqual([{ search: 'beer', sort: 'alias', dir: 'asc', limit: 50, offset: 0 }]);
    await s.showOnNewStream(EMPTY);
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No results');
  });
});

describe('AliasesPage: the filters (Alias, Category, Origin)', () => {
  it('offers the alias as text (as long as the schema takes it), the category searched on the server and the origin', async () => {
    const s = await setup();
    await s.show(PAGE);
    await s.result('tax.category.list', CATEGORIES);
    type Spec = { key: string; label: string; kind: string; options?: unknown; maxlength?: number; search?: (text: string) => void };
    const specs = s.wrapper.findComponent(FilterPanel).props('filters') as Spec[];
    expect(specs.map((f) => [f.key, f.label, f.kind, f.options ?? f.maxlength ?? null])).toEqual([
      ['alias', 'Alias', 'text', 200],
      ['tax_category_key', 'Category', 'search', [{ value: 'restaurant.food', label: 'Restauración — comida (restaurant.food)' }]],
      [
        'source',
        'Source',
        'select',
        [
          { value: 'shipped', label: 'Shipped' },
          { value: 'learned', label: 'Learned' },
        ],
      ],
    ]);
    specs[1].search?.('comida');
    await flush();
    expect(s.params('tax.category.list')).toContainEqual({ search: 'comida', sort: 'display_name', dir: 'asc', limit: 50 });
  });

  it('filters on the server from the first page', async () => {
    const s = await setup();
    await s.show({ ...PAGE, total: 120 });
    await s.find('tax-aliases-page-next').trigger('click');
    await flush();
    await s.filter({ tax_category_key: 'restaurant.food', source: 'learned' });
    expect(s.listParams()).toEqual([{ tax_category_key: 'restaurant.food', source: 'learned', sort: 'alias', dir: 'asc', limit: 50, offset: 0 }]);
  });
});

describe('AliasesPage: who may create, and the states of the screen', () => {
  it('a manager gets «+», which opens «New category alias»', async () => {
    const s = await setup();
    await s.show(PAGE);
    await s.find('tax-aliases-add').trigger('click');
    await flush();
    expect(s.wrapper.findComponent(AliasCreateModal).props('open')).toBe(true);
  });

  it('an employee only looks: the read-only notice, no «+», no dialog', async () => {
    const s = await setup({ session: EMPLOYEE });
    await s.show(PAGE);
    expect(s.find('tax-aliases-readonly').exists()).toBe(true);
    expect(s.find('tax-aliases-add').exists()).toBe(false);
    expect(s.wrapper.findComponent(AliasCreateModal).exists()).toBe(false);
  });

  it('an error offers Retry; an inactive app says so; a reconnection keeps the rows', async () => {
    const s = await setup();
    await s.show(PAGE);
    s.call.push(BYE);
    await flush();
    expect(s.find('tax-aliases-reconnecting').exists()).toBe(true);
    expect(s.rows()).toHaveLength(2);
    const t = await setup();
    t.call.push(errorFrame(t.subId(OP), 'tax.boom'));
    await flush();
    expect(t.wrapper.get('[data-role="load-error"]').text()).toContain('The category aliases could not be loaded');
    const u = await setup();
    u.call.push(errorFrame(u.subId(OP), 'app_inactive'));
    await flush();
    expect(u.find('tax-aliases-inactive').exists()).toBe(true);
    expect(u.table().exists()).toBe(false);
  });

  it('has no OutfitKit tag and formats nothing by hand', () => {
    expect(source).not.toMatch(/<ok[-]/);
    expect(source).not.toMatch(/Intl\.|toLocale|new Date\(/);
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.show(PAGE);
    expect(s.prop<Array<{ label: string }>>('columns').map((c) => c.label)).toEqual(['Alias', 'Categoría', 'Origen', 'Activo']);
    expect(s.rows()[0].findAll('[role="cell"]').map((c) => c.text().trim())).toEqual(['beer', 'restaurant.alcohol', 'De fábrica', 'Sí']);
    expect(s.prop('searchPlaceholder')).toBe('Buscar alias o categoría…');
  });
});
