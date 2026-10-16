// The list of demo items (DEMO-F01/F05/F06): follows `demo.item.list` live in a server-side
// DataTable — search, page and page size are the server's — with every state of the screen:
// loading, empty, error, app inactive, reconnecting; plus «New item» and a row that opens its detail.
// DEMO-F05 (WORKBOOK «Elementos»): the status filter, the «Updated» column (painted by the shared
// formatter, never by the page) and, for whoever can manage, the live figures above the table.
import { DataTable, EmptyState, formatDateTime, InlineFeedback } from '@erplora/ui/components';
import { AppPage } from '@erplora/ui/shell';
import { IonBadge } from '@ionic/vue';
import type { DOMWrapper } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import { BYE, EMPLOYEE, errorFrame, flush, type MountOptions, mountDemo, subId } from '../__tests__/mount-demo';
import ItemStats from '../components/ItemStats.vue';
import ItemListPage from './ItemListPage.vue';
import source from './ItemListPage.vue?raw';
import { listFillProblems } from '../../../../frontend/testing/list-fill';

const row = (id: string, name: string, status: 'open' | 'done', lineCount: number) => ({
  id,
  name,
  status,
  note: '',
  line_count: lineCount,
  updated_at: '2026-10-13T10:00:00Z',
});

const PAGE = {
  rows: [row('i1', 'Table 4', 'open', 2), row('i2', 'Terrace', 'done', 1)],
  total: 2,
  limit: 50,
  offset: 0,
};
const EMPTY = { rows: [], total: 0, limit: 50, offset: 0 };

async function setup(options: MountOptions = {}) {
  const m = await mountDemo(ItemListPage, options);
  const call = await m.live();
  const testid = (id: string) => m.wrapper.find(`[data-testid="${id}"]`);
  // DataTable is generic over its rows: found as a plain component, its props read untyped.
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const rows = () => m.wrapper.findAll('[data-testid="demo-items-row"]');
  const params = () => m.client.stream.subscriptions('demo.item.list').map((s) => s.params);
  /** Opens the table's filters panel with its funnel. */
  async function openFilters() {
    await m.wrapper.get('[data-testid="demo-items-filters-toggle"]').trigger('click');
    await flush();
    return m.wrapper.get('[data-testid="demo-items-filters-panel"]');
  }
  /** Picks a status in the funnel's panel, as Ionic's popover does (`ionChange` with the value; «All»
   *  is the empty one), and applies it. */
  async function filterBy(value: 'open' | 'done' | 'all') {
    const panel = await openFilters();
    panel
      .get('[data-testid="demo-items-filter-status"]')
      .element.dispatchEvent(new CustomEvent('ionChange', { detail: { value: value === 'all' ? '' : value } }));
    await flush();
    await panel.get('[data-testid="demo-items-filters-apply"]').trigger('click');
    await flush();
  }
  /** The SDK reopens the stream 150 ms after the subscriptions change: results come on the new one. */
  async function showOnNewStream(page: unknown) {
    await m.clock.advance(150);
    await m.result(m.net.lastStream(), 'demo.item.list', page);
  }
  return { ...m, call, testid, table, prop, rows, params, openFilters, filterBy, showOnNewStream, show: (page: unknown, rev?: number) => m.result(call, 'demo.item.list', page, rev) };
}

const many = (n: number, from = 1) =>
  Array.from({ length: n }, (_, i) => row(`i${from + i}`, `Item ${from + i}`, 'open', 0));
const ids = (n: number, from = 1) => many(n, from).map((r) => r.id);

describe('ItemListPage: the live list in a server-side DataTable', () => {
  it('follows demo.item.list, 50 from the first, with the table spinner until the first result', async () => {
    const s = await setup();
    expect(s.wrapper.findComponent(AppPage).props('title')).toBe('Demo items');
    expect(s.params()).toEqual([{ limit: 50, offset: 0 }]);
    expect(s.testid('demo-items-loading').exists()).toBe(true);
    await s.show(PAGE);
    expect(s.testid('demo-items-loading').exists()).toBe(false);
    expect(s.table().props()).toMatchObject({
      serverSide: true,
      searchable: true,
      rowClickable: true,
      testid: 'demo-items',
      pageSize: 50,
      pageSizeOptions: [10, 25, 50, 100],
      page: 0,
      total: 2,
      views: ['table', 'cards'],
    });
  });

  it('shows the rows-per-page selector, the column chooser and the list/cards segment', async () => {
    const s = await setup();
    await s.show(PAGE);
    expect(s.wrapper.find('.data-table__page-size-select').exists()).toBe(true);
    expect(s.wrapper.find('.data-table__columns-select').exists()).toBe(true);
    expect(s.testid('demo-items-view').element.tagName).toBe('ION-SEGMENT');
  });

  it('paints a row per item — name, status badge, line count, updated (WORKBOOK order) — hooked as demo-items-row with its id', async () => {
    const s = await setup();
    await s.show(PAGE);
    expect(s.prop<Array<{ key: string; label: string }>>('columns').map((c) => [c.key, c.label])).toEqual([
      ['name', 'Name'],
      ['status', 'Status'],
      ['line_count', 'Lines'],
      ['updated_at', 'Updated'],
    ]);
    expect(s.wrapper.findAll('[role="columnheader"]').map((h) => h.text().trim())).toEqual(['Name', 'Status', 'Lines', 'Updated']);
    expect(s.rows().map((r) => r.attributes('data-id'))).toEqual(['i1', 'i2']);
    expect(s.rows().map((r) => r.get('[data-testid="demo-item-name"]').text())).toEqual(['Table 4', 'Terrace']);
    expect(s.rows().map((r) => r.get('[data-testid="demo-item-lines"]').text())).toEqual(['2 lines', '1 line']);
    const badges = s.wrapper.findAllComponents(IonBadge);
    expect(badges.map((b) => [b.text(), b.props('color')])).toEqual([
      ['Open', 'primary'],
      ['Done', 'success'],
    ]);
    expect(badges.map((b) => b.attributes('data-testid'))).toEqual(['demo-item-status', 'demo-item-status']);
  });

  it('a row opens the detail of its item', async () => {
    const s = await setup();
    await s.show(PAGE);
    await s.rows()[1].trigger('click');
    await flush();
    expect(s.router.currentRoute.value.path).toBe('/demo/items/i2');
  });

  it('pages on the server: the next page and a new page size ask the query again', async () => {
    const s = await setup();
    await s.show({ ...PAGE, total: 120 });
    await s.testid('demo-items-page-next').trigger('click');
    await flush();
    expect(s.params()).toEqual([{ limit: 50, offset: 50 }]);
    expect(s.prop('page')).toBe(1);
    await s.showOnNewStream({ ...PAGE, total: 120, offset: 50 });
    s.wrapper.get('.data-table__page-size-select').element.dispatchEvent(new CustomEvent('ionChange', { detail: { value: 25 } }));
    await flush();
    expect(s.params()).toEqual([{ limit: 25, offset: 0 }]);
    expect(s.table().props()).toMatchObject({ page: 0, pageSize: 25 });
  });

  it('a page left empty by deletions elsewhere steps back to the last page that has rows', async () => {
    const s = await setup();
    await s.show({ ...PAGE, total: 120 });
    await s.testid('demo-items-page-next').trigger('click');
    await flush();
    await s.showOnNewStream({ rows: [], total: 50, limit: 50, offset: 50 });
    expect(s.params()).toEqual([{ limit: 50, offset: 0 }]);
  });

  it('searches on the server: the trimmed text, from the first page; an empty answer says «No results»', async () => {
    const s = await setup();
    await s.show({ ...PAGE, total: 120 });
    await s.testid('demo-items-page-next').trigger('click');
    await flush();
    const bar = s.testid('demo-items-search').element as HTMLElement & { value?: string };
    expect(bar.getAttribute('placeholder') ?? (bar as { placeholder?: string }).placeholder).toBe('Search…');
    bar.value = '  terr ';
    bar.dispatchEvent(new CustomEvent('ionInput', { detail: { value: '  terr ' } }));
    await flush();
    expect(s.params()).toEqual([{ search: 'terr', limit: 50, offset: 0 }]);
    expect(s.prop('search')).toBe('  terr ');
    await s.showOnNewStream(EMPTY);
    const empty = s.wrapper.findComponent(EmptyState);
    expect(empty.attributes('data-testid')).toBe('demo-items-empty');
    expect([empty.props('heading'), empty.props('message')]).toEqual(['No results', 'No item matches your search or filter.']);
  });

  it('invites a manager to create the first item when there are none', async () => {
    const s = await setup();
    await s.show(EMPTY);
    const empty = s.wrapper.findComponent(EmptyState);
    expect([empty.props('heading'), empty.props('message'), empty.props('icon')]).toEqual([
      'No items yet',
      'Create the first one with «New item».',
      'cube-outline',
    ]);
  });

  it('on an error the table says so with the server message and Retry, which reopens the stream', async () => {
    const s = await setup();
    s.call.push(errorFrame(subId(s.client, 'demo.item.list'), 'demo.boom'));
    await flush();
    expect(s.prop('error')).toBe('msg demo.boom');
    const failure = s.wrapper.get('[data-role="load-error"]');
    expect(failure.text()).toContain('The items could not be loaded');
    expect(failure.text()).toContain('msg demo.boom');
    expect(s.testid('demo-items-loading').exists()).toBe(false);
    const reconnect = vi.spyOn(s.client.stream, 'reconnect');
    await s.testid('demo-items-retry').trigger('click');
    expect(reconnect).toHaveBeenCalledOnce();
  });

  it('when the app is not active says so, without the table nor Retry (it comes back when the app is activated)', async () => {
    const s = await setup();
    s.call.push(errorFrame(subId(s.client, 'demo.item.list'), 'app_inactive'));
    await flush();
    const banner = s.wrapper.findComponent(InlineFeedback);
    expect(banner.attributes('data-testid')).toBe('demo-items-inactive');
    expect([banner.props('tone'), banner.props('heading')]).toEqual(['warning', 'This app is not active in this business']);
    expect(banner.text()).toContain('msg app_inactive');
    expect(s.table().exists()).toBe(false);
    expect(s.testid('demo-items-retry').exists()).toBe(false);
  });

  it('while the stream reconnects keeps the rows and shows a «Reconnecting…» strip', async () => {
    const s = await setup();
    await s.show(PAGE);
    expect(s.testid('demo-items-reconnecting').exists()).toBe(false);
    s.call.push(BYE);
    await flush();
    const strip = s.wrapper.findComponent(InlineFeedback);
    expect(strip.attributes('data-testid')).toBe('demo-items-reconnecting');
    expect([strip.props('tone'), strip.text()]).toEqual(['warning', 'Reconnecting…']);
    expect(s.rows()).toHaveLength(2);
  });

  it('«New item» in the toolbar opens the create page', async () => {
    const s = await setup();
    await s.show(PAGE);
    const add = s.testid('demo-items-add');
    expect(add.text()).toBe('New item');
    await add.trigger('click');
    await flush();
    expect(s.router.currentRoute.value.path).toBe('/demo/items/new');
  });

  it('does not offer «New item» to whoever cannot manage, nor invites them to create (DEMO-F06)', async () => {
    const s = await setup({ session: EMPLOYEE });
    await s.show(EMPTY);
    expect(s.testid('demo-items-add').exists()).toBe(false);
    expect(s.wrapper.findComponent(EmptyState).props('message')).toBeUndefined();
  });

  it('has no OutfitKit tag left in any state (PLAN §16.11)', () => {
    expect(source).not.toMatch(/<ok[-]/);
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    expect(s.wrapper.findComponent(AppPage).props('title')).toBe('Elementos');
    await s.show({ ...PAGE, rows: [row('i3', 'Barra', 'open', 0)] });
    expect(s.prop<Array<{ label: string }>>('columns').map((c) => c.label)).toEqual(['Nombre', 'Estado', 'Líneas', 'Actualizado']);
    expect(s.wrapper.get('[data-testid="demo-item-lines"]').text()).toBe('sin líneas');
    expect(s.wrapper.get('[data-testid="demo-item-status"]').text()).toBe('Abierto');
    expect(s.testid('demo-items-add').text()).toBe('Nuevo elemento');
  });
});

describe('ItemListPage: the status filter (WORKBOOK «Elementos»: All, Open, Done), behind the table funnel', () => {
  /** Value and visible text of each option of the panel's status select. */
  const options = (select: Pick<DOMWrapper<Element>, 'findAll'>) =>
    select.findAll('ion-select-option').map((o) => [(o.element as HTMLElement & { value?: unknown }).value, o.text()]);

  it('is the «Status» column filter of the table: the funnel opens its panel, «All» to begin with, then Open and Done', async () => {
    const s = await setup();
    await s.show(PAGE);
    expect([s.prop('filterable'), s.prop('fill')]).toEqual([true, true]);
    expect(s.testid('demo-items-filters-count').exists(), 'no filter in use: the funnel counts nothing').toBe(false);
    const panel = await s.openFilters();
    const select = panel.get('[data-testid="demo-items-filter-status"]');
    expect(select.element.tagName).toBe('ION-SELECT');
    const el = select.element as HTMLElement & { value?: unknown; label?: string; interface?: string };
    expect([el.value, el.label ?? select.attributes('label'), el.interface ?? select.attributes('interface')]).toEqual(['', 'Status', 'popover']);
    expect(options(select)).toEqual([
      ['', 'All'],
      ['open', 'Open'],
      ['done', 'Done'],
    ]);
  });

  it('filters on the server: «Done» asks the query again with `status`, from the first page, and the funnel counts it; «All» drops it', async () => {
    const s = await setup();
    await s.show({ ...PAGE, total: 120 });
    await s.testid('demo-items-page-next').trigger('click');
    await flush();
    expect(s.params()).toEqual([{ limit: 50, offset: 50 }]);
    await s.filterBy('done');
    expect(s.params()).toEqual([{ status: 'done', limit: 50, offset: 0 }]);
    expect(s.prop('page')).toBe(0);
    expect(s.prop('filters')).toEqual({ status: 'done' });
    expect(s.testid('demo-items-filters-count').text()).toBe('1');
    await s.filterBy('all');
    expect(s.params()).toEqual([{ limit: 50, offset: 0 }]);
    expect(s.prop('filters')).toEqual({});
    expect(s.testid('demo-items-filters-count').exists()).toBe(false);
  });

  it('a value the query does not know is no filter at all', async () => {
    const s = await setup();
    await s.show(PAGE);
    s.table().vm.$emit('filtersChange', { status: 'archived' });
    await flush();
    expect(s.params()).toEqual([{ limit: 50, offset: 0 }]);
    expect(s.prop('filters')).toEqual({});
  });

  it('combines with the search', async () => {
    const s = await setup();
    await s.show(PAGE);
    await s.filterBy('open');
    const bar = s.testid('demo-items-search').element as HTMLElement & { value?: string };
    bar.value = 'terr';
    bar.dispatchEvent(new CustomEvent('ionInput', { detail: { value: 'terr' } }));
    await flush();
    expect(s.params()).toEqual([{ search: 'terr', status: 'open', limit: 50, offset: 0 }]);
  });

  it('an empty answer under the filter says «No results», not «No items yet»', async () => {
    const s = await setup();
    await s.show(PAGE);
    await s.filterBy('done');
    await s.showOnNewStream(EMPTY);
    const empty = s.wrapper.findComponent(EmptyState);
    expect([empty.props('heading'), empty.props('message')]).toEqual(['No results', 'No item matches your search or filter.']);
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.show(PAGE);
    const select = (await s.openFilters()).get('[data-testid="demo-items-filter-status"]');
    const el = select.element as HTMLElement & { label?: string };
    expect(el.label ?? select.attributes('label')).toBe('Estado');
    expect(options(select).map(([, text]) => text)).toEqual(['Todos', 'Abierto', 'Hecho']);
  });
});

describe('ItemListPage: the «Updated» column', () => {
  it('paints updated_at through the shared formatter, in the page language', async () => {
    const s = await setup();
    await s.show(PAGE);
    expect(s.prop<Array<{ key: string; cell?: string }>>('columns').at(-1)).toMatchObject({ key: 'updated_at', cell: 'updated' });
    const cells = s.wrapper.findAll('[data-testid="demo-item-updated"]').map((c) => c.text());
    expect(cells).toEqual([formatDateTime('2026-10-13T10:00:00Z', 'en'), formatDateTime('2026-10-13T10:00:00Z', 'en')]);
    expect(cells[0]).toMatch(/2026/);
  });

  it('in Spanish too', async () => {
    const s = await setup({ locale: 'es' });
    await s.show(PAGE);
    expect(s.wrapper.get('[data-testid="demo-item-updated"]').text()).toBe(formatDateTime('2026-10-13T10:00:00Z', 'es'));
  });

  it('the page formats nothing by hand (shared formatters live in @erplora/ui)', () => {
    expect(source).not.toMatch(/Intl\.|toLocale|new Date\(/);
  });
});

describe('ItemListPage: the figures above the table (managers only)', () => {
  it('a manager sees the live figures of demo.item.stats above the table', async () => {
    const s = await setup();
    expect(s.client.stream.subscriptions('demo.item.stats')).toHaveLength(1);
    await s.show(PAGE);
    await s.result(s.call, 'demo.item.stats', { total: 2, open: 1, done: 1, lines: 3 });
    const stats = s.wrapper.findComponent(ItemStats);
    expect(stats.exists()).toBe(true);
    expect(
      stats.element.compareDocumentPosition(s.table().element) & Node.DOCUMENT_POSITION_FOLLOWING,
      'the figures come before the table',
    ).toBeTruthy();
    expect(['open', 'done', 'lines'].map((k) => s.testid(`demo-stats-${k}`).attributes('data-value'))).toEqual(['1', '1', '3']);
  });

  it('whoever cannot manage sees no figures and does not even ask for them (DEMO-F06)', async () => {
    const s = await setup({ session: EMPLOYEE });
    await s.show(PAGE);
    expect(s.wrapper.findComponent(ItemStats).exists()).toBe(false);
    expect(s.client.stream.subscriptions('demo.item.stats')).toHaveLength(0);
  });

  it('when the app is not active the figures go with the table', async () => {
    const s = await setup();
    s.call.push(errorFrame(subId(s.client, 'demo.item.list'), 'app_inactive'));
    await flush();
    expect(s.testid('demo-stats').exists()).toBe(false);
  });
});

// PoC issue E: on a phone «Load more» must ADD the next rows below the ones shown. The page keeps one
// live window from the first row (a bigger `limit`, `offset` 0), so every row on screen stays live.
describe('ItemListPage on a phone: «Load more» grows the live window', () => {
  type MediaListener = (e: { matches: boolean }) => void;
  let listeners: MediaListener[] = [];
  /** happy-dom lays nothing out: the DataTable's phone breakpoint answers what this says. */
  function viewport(phone: boolean): void {
    listeners = [];
    vi.stubGlobal('matchMedia', (query: string) => ({
      media: query,
      matches: phone,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: (_type: string, listener: MediaListener) => listeners.push(listener),
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }));
  }
  async function cross(phone: boolean): Promise<void> {
    for (const listener of listeners) listener({ matches: phone });
    await flush();
  }

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('10 per page picked on a desk, then on a phone «Load more» asks for 20 from row 0 and shows both pages', async () => {
    viewport(false);
    const s = await setup();
    await s.show({ rows: many(12), total: 12, limit: 50, offset: 0 });
    s.wrapper.get('.data-table__page-size-select').element.dispatchEvent(new CustomEvent('ionChange', { detail: { value: 10 } }));
    await flush();
    expect(s.params()).toEqual([{ limit: 10, offset: 0 }]);
    await s.showOnNewStream({ rows: many(10), total: 12, limit: 10, offset: 0 });
    await cross(true);
    expect(s.params(), 'the first page alone is already a phone window').toEqual([{ limit: 10, offset: 0 }]);

    await s.testid('demo-items-load-more').trigger('click');
    await flush();
    expect(s.params()).toEqual([{ limit: 20, offset: 0 }]);
    expect(s.rows(), 'the shown rows stay while the bigger window loads').toHaveLength(10);
    await s.showOnNewStream({ rows: many(12), total: 12, limit: 20, offset: 0 });
    expect(s.rows().map((r) => r.attributes('data-id'))).toEqual(ids(12));
    expect(s.testid('demo-items-load-more').exists(), 'every row is shown').toBe(false);

    // A write elsewhere re-runs the same window: a row of the second page is updated in place.
    const renamed = many(12).map((r) => (r.id === 'i11' ? { ...r, name: 'Renamed 11' } : r));
    await s.result(s.net.lastStream(), 'demo.item.list', { rows: renamed, total: 12, limit: 20, offset: 0 }, 2);
    expect(s.rows()).toHaveLength(12);
    expect(s.wrapper.text()).toContain('Renamed 11');
  });

  it('back on a desk, or with a new search, the window starts again at one page', async () => {
    viewport(true);
    const s = await setup();
    expect(s.params()).toEqual([{ limit: 50, offset: 0 }]);
    await s.show({ rows: many(50), total: 120, limit: 50, offset: 0 });
    await s.testid('demo-items-load-more').trigger('click');
    await flush();
    expect(s.params()).toEqual([{ limit: 100, offset: 0 }]);
    await s.showOnNewStream({ rows: many(100), total: 120, limit: 100, offset: 0 });

    await cross(false);
    expect(s.params(), 'a desk pages one page at a time').toEqual([{ limit: 50, offset: 0 }]);
    await s.showOnNewStream({ rows: many(50), total: 120, limit: 50, offset: 0 });

    await cross(true);
    await s.testid('demo-items-load-more').trigger('click');
    await flush();
    expect(s.params()).toEqual([{ limit: 100, offset: 0 }]);
    const bar = s.testid('demo-items-search').element as HTMLElement & { value?: string };
    bar.value = 'item';
    bar.dispatchEvent(new CustomEvent('ionInput', { detail: { value: 'item' } }));
    await flush();
    expect(s.params()).toEqual([{ search: 'item', limit: 50, offset: 0 }]);

    // A new status filter starts the window again too.
    await s.showOnNewStream({ rows: many(50), total: 120, limit: 50, offset: 0 });
    await s.testid('demo-items-load-more').trigger('click');
    await flush();
    expect(s.params()).toEqual([{ search: 'item', limit: 100, offset: 0 }]);
    await s.filterBy('open');
    expect(s.params()).toEqual([{ search: 'item', status: 'open', limit: 50, offset: 0 }]);
  });
});

describe('ItemListPage: the list fills the page (FIX-DATATABLE-HUB)', () => {
  it('AppPage `fill` and its DataTable `fill`, only stacks between them: from the topbar to the bottom of the page', async () => {
    const s = await setup();
    expect(listFillProblems(s.wrapper)).toEqual([]);
  });

  it('declares no section tabs: the demo has a single list, like its create and detail pages', async () => {
    const s = await setup();
    expect(s.wrapper.findComponent(AppPage).props('tabs')).toEqual([]);
    expect(s.wrapper.find('ion-footer.section-tabbar').exists()).toBe(false);
  });
});
