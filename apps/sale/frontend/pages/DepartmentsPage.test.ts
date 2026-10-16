// Sales & POS → Sections (SALE-F35; WORKBOOK «Pantallas · Secciones»): the old intro, then the live
// `sale.department.list` in a server-side DataTable — Name, «VAT charged» («Name · rate», the rate the
// server says the category charges today, never one the page works out) and Position —, «Search a
// section…», 50 a page sorted by position. Whoever may change the till settings gets «+», «Edit» (also a
// tap on the row) and «Delete» (confirmed with «Delete section»); anyone else sees it read-only.
import { DataTable, EmptyState } from '@erplora/ui/components';
import { AppPage } from '@erplora/ui/shell';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import { BYE, EMPLOYEE, errorFrame, flush, type MountOptions, mountSale } from '../__tests__/mount-sale';
import DepartmentFormModal from '../components/backoffice/DepartmentFormModal.vue';
import { plain } from '../lib/format';
import type { DepartmentOut } from '../operations';
import DepartmentsPage from './DepartmentsPage.vue';
import { listFillProblems } from '../../../../frontend/testing/list-fill';

const mocks = vi.hoisted(() => ({ confirm: vi.fn() }));
vi.mock('@erplora/ui/components', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/components')>()),
  useConfirm: () => ({ confirm: mocks.confirm }),
}));
vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});
beforeEach(() => mocks.confirm.mockReset());

const OP = 'sale.department.list';
const department = (id: string, name: string, over: Partial<DepartmentOut> = {}): DepartmentOut => ({
  id,
  name,
  tax_category_key: 'general',
  tax_category_name: 'General',
  tax_rate_pct: '21.00',
  sort_order: 0,
  ...over,
});
const PAGE = {
  rows: [
    department('d1', 'Fruit and veg', { tax_category_key: 'food.basic', tax_category_name: 'Basic food', tax_rate_pct: '4.00' }),
    department('d2', 'Butchery', { tax_category_key: 'food.reduced', tax_category_name: 'Reduced food', tax_rate_pct: '10.00', sort_order: 1 }),
    department('d3', 'Household', { tax_category_key: 'product.books', tax_category_name: '', tax_rate_pct: null, sort_order: 2 }),
  ],
  total: 3,
  limit: 50,
  offset: 0,
};
const EMPTY = { rows: [], total: 0, limit: 50, offset: 0 };
const GONE = 'That section is no longer in this business. Reload the list and try again.';

async function setup(options: MountOptions = {}) {
  const m = await mountSale(DepartmentsPage, { path: '/sale/departments', ...options });
  await m.live();
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const rows = () => m.wrapper.findAll('[data-testid="sale-departments-row"]');
  const show = (page: unknown) => m.result(OP, page);
  async function emit(event: string, ...args: unknown[]) {
    table().vm.$emit(event, ...args);
    await flush();
    await m.reopen();
  }
  const form = () => m.wrapper.findComponent(DepartmentFormModal);
  const cells = (i: number) => rows()[i].findAll('[role="cell"]').map((c) => plain(c.text().trim())).slice(0, 3);
  return { ...m, table, prop, rows, show, emit, form, cells };
}

describe('DepartmentsPage: the live list', () => {
  it('sits under «Sales & POS» with the tabbar of its sections, the old intro on top', async () => {
    const s = await setup();
    const page = s.wrapper.findComponent(AppPage);
    expect([page.props('title'), page.props('tabsLabel')]).toEqual(['Sales & POS', 'Sales & POS sections']);
    expect(s.find('sale-departments-intro').text()).toBe(
      'The sections the till offers when you charge an amount that is not in the catalogue. Each one carries its own VAT. Leave the list empty and the till falls back to the plain tax categories.',
    );
  });

  it('follows sale.department.list, 50 sorted by position, «Loading sections…» until the first result', async () => {
    const s = await setup();
    expect(s.params(OP)).toEqual([{ sort: 'sort_order', dir: 'asc', limit: 50, offset: 0 }]);
    expect(s.find('sale-departments-loading').text()).toContain('Loading sections…');
    await s.show(PAGE);
    expect(s.table().props()).toMatchObject({ serverSide: true, searchable: true, testid: 'sale-departments', pageSize: 50, total: 3, views: ['table', 'cards'] });
    expect([s.prop('searchPlaceholder'), s.prop('entityLabel')]).toEqual(['Search a section…', { one: 'section', many: 'sections' }]);
  });

  it('paints Name, VAT charged («Name · rate» as the server says) and Position; Name and Position sort', async () => {
    const s = await setup();
    await s.show(PAGE);
    expect(s.prop<Array<{ key: string; label: string; sortable?: boolean }>>('columns').map((c) => [c.key, c.label, !!c.sortable])).toEqual([
      ['name', 'Name', true],
      ['tax_category_key', 'VAT charged', false],
      ['sort_order', 'Position', true],
    ]);
    expect(s.rows().map((r) => r.attributes('data-id'))).toEqual(['d1', 'd2', 'd3']);
    expect(s.cells(0)).toEqual(['Fruit and veg', 'Basic food · 4%', '0']);
    expect(s.cells(1)).toEqual(['Butchery', 'Reduced food · 10%', '1']);
    // No name and no rate today: the key, alone.
    expect(s.cells(2)).toEqual(['Household', 'product.books', '2']);
  });

  it('sorts and searches on the server (60 characters at most), from the first page', async () => {
    const s = await setup();
    await s.show(PAGE);
    await s.emit('sortChange', { sort: 'name', dir: 'asc' });
    await s.emit('update:search', ` ${'x'.repeat(70)} `);
    expect(s.params(OP)).toEqual([{ search: 'x'.repeat(60), sort: 'name', dir: 'asc', limit: 50, offset: 0 }]);
  });

  it('«Load more» on a phone never asks more than 100 at once', async () => {
    const s = await setup();
    await s.show({ ...PAGE, total: 400 });
    await s.emit('loadMore');
    await s.emit('loadMore');
    for (const params of s.params(OP)) expect(params.limit as number).toBeLessThanOrEqual(100);
    expect(s.params(OP)).toHaveLength(2);
  });

  it('with no section, the empty text; a search with no match says «No results»', async () => {
    const s = await setup();
    await s.show(EMPTY);
    const empty = () => s.wrapper.findComponent(EmptyState);
    expect(empty().props('heading')).toBe('No sections yet. Add the ones you ring up by hand — “Fruit and veg”, “Butchery”, “Household”.');
    await s.emit('update:search', 'zzz');
    await s.show(EMPTY);
    expect([empty().props('heading'), empty().props('message')]).toEqual(['No results', 'No section matches your search.']);
  });

  it('a failed read is the table’s error with «Retry»; the app off replaces the list; «Reconnecting…» keeps it', async () => {
    const s = await setup();
    await s.show(PAGE);
    s.net.lastStream().push(BYE);
    await flush();
    expect(s.find('sale-departments-reconnecting').exists()).toBe(true);
    const t = await setup();
    t.net.lastStream().push(errorFrame(t.subId(OP), 'server_error'));
    await flush();
    expect([t.prop('error'), t.prop<Record<string, string>>('labels').loadError]).toEqual(['msg server_error', 'The sections could not be loaded.']);
    const u = await setup();
    u.net.lastStream().push(errorFrame(u.subId(OP), 'app_inactive'));
    await flush();
    expect(u.find('sale-departments-inactive').exists()).toBe(true);
    expect(u.table().exists()).toBe(false);
  });
});

describe('DepartmentsPage: whoever may change the till settings', () => {
  it('«+» opens «New section»; «Edit» and a tap on the row open the section', async () => {
    const s = await setup();
    await s.show(PAGE);
    expect([s.prop('addable'), s.prop('rowClickable')]).toEqual([true, true]);
    expect(s.prop<Array<{ id: string; label: string; icon: string }>>('actions').map((a) => [a.id, a.label, a.icon])).toEqual([
      ['edit', 'Edit', 'ion:create-outline'],
      ['delete', 'Delete', 'ion:trash-outline'],
    ]);
    await s.emit('add');
    expect([s.form().props('open'), s.form().props('department')]).toEqual([true, null]);
    s.form().vm.$emit('update:open', false);
    await s.emit('action', { actionId: 'edit', row: PAGE.rows[0] });
    expect(s.form().props('department')).toEqual(PAGE.rows[0]);
    s.form().vm.$emit('update:open', false);
    await s.emit('rowClick', PAGE.rows[1]);
    expect([s.form().props('open'), s.form().props('department')]).toEqual([true, PAGE.rows[1]]);
  });

  it('«Delete» asks first and, confirmed, deletes it by its id', async () => {
    const s = await setup();
    await s.show(PAGE);
    mocks.confirm.mockResolvedValue(true);
    s.answer(200, PAGE.rows[1]);
    await s.emit('action', { actionId: 'delete', row: PAGE.rows[1] });
    expect(mocks.confirm).toHaveBeenCalledWith({
      title: 'Delete section',
      message: 'Butchery — It stops being offered at the till. Everything already sold keeps the name and the VAT it was charged with.',
      confirmLabel: 'Delete',
      cancelLabel: 'Cancel',
      confirmIcon: 'ion:trash-outline',
      tone: 'danger',
    });
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/sale/departments/delete', query: {}, body: { id: 'd2' } }]);
  });

  it('a section another device deleted: «The section could not be deleted.» and the server’s words', async () => {
    const s = await setup();
    await s.show(PAGE);
    mocks.confirm.mockResolvedValue(true);
    s.answer(404, { error: { code: 'sale.department_not_found', message: GONE } });
    await s.emit('action', { actionId: 'delete', row: PAGE.rows[0] });
    const notice = s.find('sale-departments-error').text();
    expect(notice).toContain('The section could not be deleted.');
    expect(notice).toContain(GONE);
  });
});

describe('DepartmentsPage: anyone else', () => {
  it('sees the list without «+», row actions, row taps or form', async () => {
    const s = await setup({ session: EMPLOYEE });
    await s.show(PAGE);
    expect([s.prop('addable'), s.prop('actions'), s.prop('rowClickable')]).toEqual([false, [], false]);
    expect(s.form().exists()).toBe(false);
  });
});

describe('DepartmentsPage: Spanish', () => {
  it('speaks the old screen’s words, with the rate as Spain writes it', async () => {
    const s = await setup({ locale: 'es' });
    expect(s.find('sale-departments-loading').text()).toContain('Cargando secciones…');
    await s.show(PAGE);
    expect(s.prop('searchPlaceholder')).toBe('Buscar una sección…');
    expect(s.prop<Array<{ label: string }>>('columns').map((c) => c.label)).toEqual(['Nombre', 'IVA que cobra', 'Posición']);
    expect(s.cells(1)).toEqual(['Butchery', 'Reduced food · 10 %', '1']);
  });
});

describe('DepartmentsPage: the list fills the page (FIX-DATATABLE-HUB)', () => {
  it('AppPage `fill` and its DataTable `fill`, only stacks between them: from the topbar to the tabbar', async () => {
    const s = await setup();
    expect(listFillProblems(s.wrapper)).toEqual([]);
  });
});
