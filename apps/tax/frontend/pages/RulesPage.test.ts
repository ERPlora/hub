// Taxes → Rules (TAX-F03–F08, F11; the WORKBOOK's screens): the live `tax.rule.list` in a server-side
// DataTable — Category (a component as «↳ label», right under its root), Country, Region, %, Type,
// Qualification (with the exemption reason), Valid from, Valid to and Active —; search «Search category
// or country…»; Status Active (to begin with) · Deactivated · All; the filters Country (the ones the
// business has rules for), Region, Category, Type, Qualification, Regime and % from–to; «+» with
// «New tax rule»; row actions «Set end date» and «Deactivate» (confirmed), «Restore» on a deactivated
// one. An employee sees the rules without «+» nor row actions.
import { ConfirmDialog, DataTable, EmptyState } from '@erplora/ui/components';
import { AppPage } from '@erplora/ui/shell';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import type { CategoryRowOut, RuleOut } from '../operations';
import { BYE, click, EMPLOYEE, errorFrame, flush, type MountOptions, mountTax, settle } from '../__tests__/mount-tax';
import RuleCreateModal from '../components/RuleCreateModal.vue';
import RuleEndModal from '../components/RuleEndModal.vue';
import RulesPage from './RulesPage.vue';
import source from './RulesPage.vue?raw';
import { listFillProblems } from '../../../../frontend/testing/list-fill';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const OP = 'tax.rule.list';

const rule = (id: string, over: Partial<RuleOut> = {}): RuleOut => ({
  id,
  country_code: 'ES',
  region_code: null,
  tax_category_key: 'restaurant.food',
  tax_category_name: 'Restauración — comida',
  rate_pct: '10.00',
  tax_type: 'vat',
  operation_class: 'subject',
  exempt_reason: null,
  regime_key: null,
  parent_id: null,
  component_label: null,
  valid_from: '2012-09-01',
  valid_to: null,
  is_active: true,
  updated_at: '2026-10-13T10:00:00Z',
  ...over,
});

const ROWS = [
  rule('r1'),
  rule('r2', { parent_id: 'r1', component_label: 'Recargo de equivalencia', tax_type: 'surcharge', rate_pct: '1.40', valid_from: null }),
  rule('r3', {
    tax_category_key: 'service.health',
    tax_category_name: 'Servicio — sanitario',
    rate_pct: '0.00',
    operation_class: 'exempt',
    exempt_reason: 'E1',
    region_code: 'ES-CN',
    valid_to: '2026-12-31',
  }),
];
const PAGE = { rows: ROWS, total: 3, limit: 50, offset: 0 };
const EMPTY = { rows: [], total: 0, limit: 50, offset: 0 };
const INACTIVE = { rows: [rule('r9', { is_active: false })], total: 1, limit: 50, offset: 0 };
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
const CATEGORIES = {
  rows: [category('restaurant.food', 'Restauración — comida'), category('service.health', 'Servicio — sanitario')],
  total: 2,
  limit: 100,
  offset: 0,
};

async function setup(options: MountOptions = {}) {
  const m = await mountTax(RulesPage, { path: '/tax/rules', ...options });
  const call = await m.live();
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const rows = () => m.wrapper.findAll('[data-testid="tax-rules-row"]');
  const cells = (i: number) => rows()[i].findAll('[role="cell"]').map((c) => c.text().trim());
  /** The params of the table's subscription (the page's only one to the rules). */
  const params = () => m.params(OP);
  const listId = () => m.subId(OP);
  async function show(page: unknown) {
    m.net.lastStream().push(`event: result\ndata: ${JSON.stringify({ id: listId(), data: page, rev: 1 })}\n\n`);
    await flush();
  }
  async function showOnNewStream(page: unknown) {
    await m.reopen();
    await show(page);
  }
  const showCountries = (countries: string[]) => m.result('tax.rule.countries', { countries });
  const showCategories = () => m.result('tax.category.list', CATEGORIES);
  async function status(value: string) {
    m.find('tax-rules-status').element.dispatchEvent(new CustomEvent('ionChange', { detail: { value } }));
    await flush();
  }
  /** The table's funnel applies its filters (`v-model:filters`): what the panel's «Apply» emits. */
  async function filter(values: Record<string, string>) {
    table().vm.$emit('update:filters', values);
    await flush();
  }
  async function action(id: string, actionId: string) {
    await m.find(`tax-rules-row-${id}-${actionId}`).trigger('click');
    await settle();
  }
  return { ...m, paramsOf: m.params, call, table, prop, rows, cells, params, listId, show, showOnNewStream, showCountries, showCategories, status, filter, action };
}

describe('RulesPage: the live list', () => {
  it('follows the active rules sorted by category (a component after its root), 50 from the first', async () => {
    const s = await setup();
    expect(s.params()).toEqual([{ status: 'active', sort: 'tax_category_key', dir: 'asc', limit: 50, offset: 0 }]);
    expect(s.find('tax-rules-loading').exists()).toBe(true);
    await s.show(PAGE);
    expect(s.find('tax-rules-loading').exists()).toBe(false);
    expect(s.table().props()).toMatchObject({ serverSide: true, searchable: true, testid: 'tax-rules', total: 3, views: ['table', 'cards'] });
    expect(s.prop('searchPlaceholder')).toBe('Search category or country…');
    expect(s.prop('entityLabel')).toEqual({ one: 'rule', many: 'rules' });
    expect(s.wrapper.findComponent(AppPage).props('title')).toBe('Taxes');
  });

  it('asks the server the countries of the business’s rules (the Country filter offers those)', async () => {
    const s = await setup();
    expect(s.paramsOf('tax.rule.countries')).toEqual([{}]);
  });

  it('paints Category, Country, Region, %, Type, Qualification, Valid from, Valid to and Active', async () => {
    const s = await setup();
    await s.show(PAGE);
    expect(s.prop<Array<{ key: string; label: string }>>('columns').map((c) => [c.key, c.label])).toEqual([
      ['tax_category_key', 'Category'],
      ['country_code', 'Country'],
      ['region_code', 'Region'],
      ['rate_pct', '%'],
      ['tax_type', 'Type'],
      ['operation_class', 'Qualification'],
      ['valid_from', 'Valid from'],
      ['valid_to', 'Valid to'],
      ['is_active', 'Active'],
    ]);
    expect(s.rows().map((r) => r.attributes('data-id'))).toEqual(['r1', 'r2', 'r3']);
    expect(s.cells(0).slice(0, 9)).toEqual(['restaurant.food', 'ES', '—', '10.00%', 'VAT', 'Subject', 'Sep 1, 2012', '—', 'Yes']);
    expect(s.cells(1).slice(0, 9)).toEqual(['↳ Recargo de equivalencia', 'ES', '—', '1.40%', 'Surcharge', 'Subject', '—', '—', 'Yes']);
    expect(s.cells(2).slice(0, 9)).toEqual(['service.health', 'ES', 'ES-CN', '0.00%', 'VAT', 'Exempt · E1', 'Sep 1, 2012', 'Dec 31, 2026', 'Yes']);
  });

  it('sorts on the server by any column; a new sort starts from the first page', async () => {
    const s = await setup();
    await s.show(PAGE);
    expect(s.prop<Array<{ sortable?: boolean }>>('columns').every((c) => c.sortable)).toBe(true);
    s.table().vm.$emit('sortChange', { sort: 'rate_pct', dir: 'desc' });
    await flush();
    expect(s.params()).toEqual([{ status: 'active', sort: 'rate_pct', dir: 'desc', limit: 50, offset: 0 }]);
  });

  it('searches on the server; an empty answer says «No results», no rule at all «No tax rules.»', async () => {
    const s = await setup();
    await s.show(EMPTY);
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No tax rules.');
    s.table().vm.$emit('update:search', ' ES ');
    await flush();
    expect(s.params()).toEqual([{ search: 'ES', status: 'active', sort: 'tax_category_key', dir: 'asc', limit: 50, offset: 0 }]);
    await s.showOnNewStream(EMPTY);
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No results');
  });

  it('names a card after the category a person reads (a component, with its root and its label)', async () => {
    const s = await setup();
    await s.show(PAGE);
    const title = s.prop<(row: RuleOut) => string>('cardTitle');
    expect(ROWS.map(title)).toEqual(['Restauración — comida', '↳ Restauración — comida · Recargo de equivalencia', 'Servicio — sanitario']);
  });
});

// On a phone the list is cards (the DataTable's breakpoint): a card's body says every field once,
// without the category its title already names, and leaves out the columns the person hid.
describe('RulesPage on a phone: the rule cards', () => {
  function phone(): void {
    vi.stubGlobal('matchMedia', (query: string) => ({
      media: query,
      matches: true,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }));
  }
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('shows every field but the category once, and drops the ones hidden in the column chooser', async () => {
    phone();
    const s = await setup();
    await s.show(PAGE);
    const fields = () =>
      s.rows()[2].findAll('[data-testid="tax-rule-card-field"]').map((f) => [f.attributes('data-key'), f.find('.tax-rule-card__value').text()]);
    expect(s.rows()[2].text()).toContain('Servicio — sanitario');
    expect(fields()).toEqual([
      ['country_code', 'ES'],
      ['region_code', 'ES-CN'],
      ['rate_pct', '0.00%'],
      ['tax_type', 'VAT'],
      ['operation_class', 'Exempt · E1'],
      ['valid_from', 'Sep 1, 2012'],
      ['valid_to', 'Dec 31, 2026'],
      ['is_active', 'Yes'],
    ]);
    s.table().vm.$emit('columnsChange', ['tax_category_key', 'country_code', 'rate_pct']);
    await flush();
    expect(fields().map(([key]) => key)).toEqual(['country_code', 'rate_pct']);
  });
});

describe('RulesPage: Status (TAX-F03, F08)', () => {
  it('is an ion-select in the toolbar, «Active» to begin with, then Deactivated and All', async () => {
    const s = await setup();
    await s.show(PAGE);
    const select = s.find('tax-rules-status');
    expect(select.element.tagName).toBe('ION-SELECT');
    expect([(select.element as HTMLElement & { value?: unknown }).value, select.attributes('aria-label')]).toEqual(['active', 'Filter by status']);
    expect(select.findAll('ion-select-option').map((o) => o.text())).toEqual(['Active', 'Deactivated', 'All']);
  });

  it('asks the server for the deactivated ones, from the first page, and back', async () => {
    const s = await setup();
    await s.show({ ...PAGE, total: 120 });
    await s.find('tax-rules-page-next').trigger('click');
    await flush();
    await s.status('inactive');
    expect(s.params()).toEqual([{ status: 'inactive', sort: 'tax_category_key', dir: 'asc', limit: 50, offset: 0 }]);
    await s.status('all');
    expect(s.params()[0]).toMatchObject({ status: 'all' });
  });
});

describe('RulesPage: the filters (TAX-F03; the jurisdiction, TAX-F11)', () => {
  it('offers Category (searched), Country (the business’s), Region, %, Type and Qualification on their columns, then Regime', async () => {
    // flow: ninguno — FIX DataTable parte 2b-1 (PLAN-MIGRATIONS §13: filtros como en la vieja)
    const s = await setup();
    await s.show(PAGE);
    await s.showCountries(['ES', 'PT']);
    expect(s.prop('filterable')).toBe(true);
    type Filter = {
      type: string;
      keys?: string[];
      options?: Array<{ value: string; label: string }>;
      maxlength?: number;
      min?: number;
      max?: number;
      load?: (query: string) => Promise<unknown>;
    };
    const columns = () => s.prop<Array<{ key: string; label: string; filter?: Filter }>>('columns').filter((c) => c.filter);
    expect(columns().map((c) => [c.key, c.label, c.filter?.type])).toEqual([
      ['tax_category_key', 'Category', 'lookup'],
      ['country_code', 'Country', 'select'],
      ['region_code', 'Region', 'text'],
      ['rate_pct', '%', 'range'],
      ['tax_type', 'Type', 'select'],
      ['operation_class', 'Qualification', 'select'],
    ]);
    const fields = s.prop<Array<Filter & { key: string; label: string }>>('filterFields');
    expect(fields.map((f) => [f.key, f.label, f.type])).toEqual([['regime_key', 'Regime', 'text']]);
    const byKey = (key: string) => columns().find((c) => c.key === key)?.filter;
    // Bounded as RuleListIn takes them: a longer region or regime, or a % off 0–100, would be a 422.
    expect([byKey('region_code')?.maxlength, fields[0].maxlength, byKey('rate_pct')?.min, byKey('rate_pct')?.max]).toEqual([6, 10, 0, 100]);
    expect(byKey('rate_pct')?.keys).toEqual(['rate_min', 'rate_max']);
    expect(byKey('country_code')?.options).toEqual([
      { value: 'PT', label: 'Portugal (PT)' },
      { value: 'ES', label: 'Spain (ES)' },
    ]);
    expect(byKey('tax_type')?.options?.[1]).toEqual({ value: 'igic', label: 'IGIC (Canary Islands)' });
    expect(byKey('operation_class')?.options?.map((o) => o.value)).toEqual(['subject', 'subject_reverse', 'exempt', 'not_subject', 'not_subject_location']);
    // The category is searched on the server: every category of the business, not a first page.
    s.answer(200, CATEGORIES);
    expect(await byKey('tax_category_key')?.load?.('food')).toEqual([
      { value: 'restaurant.food', label: 'Restauración — comida (restaurant.food)' },
      { value: 'service.health', label: 'Servicio — sanitario (service.health)' },
    ]);
    expect(s.sent().map((c) => [c.path, c.query])).toEqual([['/api/tax/categories', { search: 'food', sort: 'display_name', dir: 'asc', limit: '50' }]]);
  });

  it('the Status select stays out of the funnel, beside it', async () => {
    const s = await setup();
    await s.show(PAGE);
    expect(s.find('tax-rules-status').exists()).toBe(true);
    await s.find('tax-rules-filters-toggle').trigger('click');
    await flush();
    expect(s.find('tax-rules-filters-panel').find('[data-testid="tax-rules-status"]').exists()).toBe(false);
  });

  it('filters by country and region on the server, from the first page, with the % as a range', async () => {
    const s = await setup();
    await s.show({ ...PAGE, total: 120 });
    await s.find('tax-rules-page-next').trigger('click');
    await flush();
    await s.filter({ country_code: 'ES', region_code: 'CN', rate_min: '5', rate_max: '10' });
    expect(s.params()).toEqual([
      { country_code: 'ES', region_code: 'CN', rate_min: '5', rate_max: '10', status: 'active', sort: 'tax_category_key', dir: 'asc', limit: 50, offset: 0 },
    ]);
    expect(s.find('tax-rules-filters-count').text(), 'the % from–to counts once').toBe('3');
    await s.showOnNewStream(EMPTY);
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No results');
  });
});

describe('RulesPage: the row actions (TAX-F07, F08)', () => {
  it('an active rule offers «Set end date» and «Deactivate»; a deactivated one only «Restore»', async () => {
    const s = await setup();
    await s.show(PAGE);
    expect(s.prop<Array<{ id: string; label: string; icon: string; color?: string }>>('actions').map((a) => [a.id, a.label, a.icon, a.color ?? null])).toEqual([
      ['end', 'Set end date', 'calendar-outline', null],
      ['deactivate', 'Deactivate', 'close-outline', 'danger'],
      ['restore', 'Restore', 'refresh-outline', 'success'],
    ]);
    expect(s.find('tax-rules-row-r1-end').exists()).toBe(true);
    expect(s.find('tax-rules-row-r1-deactivate').exists()).toBe(true);
    await s.status('inactive');
    await s.showOnNewStream(INACTIVE);
    expect(s.find('tax-rules-row-r9-restore').exists()).toBe(true);
    expect(s.find('tax-rules-row-r9-deactivate').exists()).toBe(false);
  });

  it('«Set end date» opens the end dialog for that rule', async () => {
    const s = await setup();
    await s.show(PAGE);
    const end = s.wrapper.findComponent(RuleEndModal);
    expect(end.props('open')).toBe(false);
    await s.action('r1', 'end');
    expect([s.wrapper.findComponent(RuleEndModal).props('open'), (s.wrapper.findComponent(RuleEndModal).props('rule') as RuleOut).id]).toEqual([true, 'r1']);
  });

  it('«Deactivate» asks first («Deactivate tax rule»), then sends tax.rule.deactivate and closes', async () => {
    const s = await setup();
    await s.show(PAGE);
    await s.action('r3', 'deactivate');
    const confirm = s.wrapper.findComponent(ConfirmDialog);
    expect(confirm.props()).toMatchObject({
      open: true,
      title: 'Deactivate tax rule',
      message: 'The rule will no longer apply to new transactions. Previously issued fiscal documents will not change.',
      confirmLabel: 'Deactivate rule',
      tone: 'danger',
      testid: 'tax-rule-deactivate',
    });
    expect(s.sent()).toEqual([]);
    s.answer(200, rule('r3', { is_active: false }));
    await click(s.inDoc('tax-rule-deactivate-submit'));
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/tax/rules/deactivate', query: {}, body: { id: 'r3' } }]);
    expect(s.wrapper.findComponent(ConfirmDialog).props('open')).toBe(false);
  });

  it('cancelling the deactivation sends nothing; a refusal stays in the dialog with its words', async () => {
    const s = await setup();
    await s.show(PAGE);
    await s.action('r1', 'deactivate');
    await click(s.inDoc('tax-rule-deactivate-cancel'));
    expect(s.sent()).toEqual([]);
    await s.action('r1', 'deactivate');
    s.answer(409, { error: { code: 'tax.rule_inactive', message: 'That rule is already deactivated.' } });
    await click(s.inDoc('tax-rule-deactivate-submit'));
    expect(s.inDoc('tax-rule-deactivate-error')?.textContent).toContain('That rule is already deactivated.');
    expect(s.wrapper.findComponent(ConfirmDialog).props('open')).toBe(true);
  });

  it('«Restore» needs no confirmation; a refusal shows on the page with the server’s words', async () => {
    const s = await setup();
    await s.status('inactive');
    await s.showOnNewStream(INACTIVE);
    s.answer(409, { error: { code: 'tax.rule_overlaps', message: 'It overlaps another active rule.' } });
    await s.action('r9', 'restore');
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/tax/rules/activate', query: {}, body: { id: 'r9' } }]);
    expect(s.find('tax-rules-error').text()).toContain('It overlaps another active rule.');
    s.answer(200, rule('r9'));
    await s.action('r9', 'restore');
    expect(s.find('tax-rules-error').exists()).toBe(false);
  });
});

describe('RulesPage: who may manage', () => {
  it('a manager gets «+», which opens «New tax rule»', async () => {
    const s = await setup();
    await s.show(PAGE);
    expect(s.wrapper.findComponent(RuleCreateModal).props('open')).toBe(false);
    await s.find('tax-rules-add').trigger('click');
    await flush();
    expect(s.wrapper.findComponent(RuleCreateModal).props('open')).toBe(true);
  });

  it('an employee sees the rules read-only: the notice, no «+», no row actions, no dialogs', async () => {
    const s = await setup({ session: EMPLOYEE });
    await s.show(PAGE);
    expect(s.find('tax-rules-readonly').exists()).toBe(true);
    expect(s.find('tax-rules-add').exists()).toBe(false);
    expect(s.prop('actions')).toEqual([]);
    expect(s.find('tax-rules-row-r1-deactivate').exists()).toBe(false);
    expect(s.wrapper.findComponent(RuleCreateModal).exists()).toBe(false);
    expect(s.wrapper.findComponent(RuleEndModal).exists()).toBe(false);
  });
});

describe('RulesPage: the states of the screen', () => {
  it('on an error the table says so with Retry', async () => {
    const s = await setup();
    s.call.push(errorFrame(s.listId(), 'tax.boom'));
    await flush();
    expect(s.prop('error')).toBe('msg tax.boom');
    expect(s.wrapper.get('[data-role="load-error"]').text()).toContain('The tax rules could not be loaded');
    const reconnect = vi.spyOn(s.client.stream, 'reconnect');
    await s.find('tax-rules-retry').trigger('click');
    expect(reconnect).toHaveBeenCalledOnce();
  });

  it('when the app is not active says so instead of the table', async () => {
    const s = await setup();
    s.call.push(errorFrame(s.listId(), 'app_inactive'));
    await flush();
    expect(s.find('tax-rules-inactive').exists()).toBe(true);
    expect(s.table().exists()).toBe(false);
  });

  it('while the stream reconnects keeps the rows and shows «Reconnecting…»', async () => {
    const s = await setup();
    await s.show(PAGE);
    s.call.push(BYE);
    await flush();
    expect(s.find('tax-rules-reconnecting').exists()).toBe(true);
    expect(s.rows()).toHaveLength(3);
  });
});

describe('RulesPage: the rest', () => {
  it('has no OutfitKit tag', () => {
    expect(source).not.toMatch(/<ok[-]/);
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.show(PAGE);
    expect(s.prop<Array<{ label: string }>>('columns').map((c) => c.label)).toEqual([
      'Categoría',
      'País',
      'Región',
      '%',
      'Tipo',
      'Calificación',
      'Vigente desde',
      'Vigente hasta',
      'Activa',
    ]);
    expect(s.cells(2).slice(4, 6)).toEqual(['IVA', 'Exenta · E1']);
    // Rates and days as a Spanish reader writes them, not «0.00%» and «2012-09-01».
    const plain = (text: string) => text.replace(/[\u00a0\u202f]/g, ' ');
    expect([plain(s.cells(2)[3]), s.cells(2)[6], s.cells(2)[7]]).toEqual(['0,00 %', '1 sept 2012', '31 dic 2026']);
    expect(s.find('tax-rules-status').findAll('ion-select-option').map((o) => o.text())).toEqual(['Activas', 'Desactivadas', 'Todas']);
    expect(s.prop<Array<{ label: string }>>('actions').map((a) => a.label)).toEqual(['Poner fecha de fin', 'Desactivar', 'Reactivar']);
    expect(s.prop('searchPlaceholder')).toBe('Buscar categoría o país…');
  });
});

describe('RulesPage: the list fills the page (FIX-DATATABLE-HUB)', () => {
  it('AppPage `fill` and its DataTable `fill`, only stacks between them: from the topbar to the tabbar', async () => {
    const s = await setup();
    expect(listFillProblems(s.wrapper)).toEqual([]);
  });
});
