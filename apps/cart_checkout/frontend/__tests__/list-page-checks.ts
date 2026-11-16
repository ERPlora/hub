// What the tests of Cart & Checkout's two lists, Carts and Orders, check alike: their table's funnel, the order they
// ask for, and their Total column, typed as an amount in the business's currency. Each list's test passes its own setup.
import { AppPage } from '@erplora/ui/shell';
import type { DOMWrapper, VueWrapper } from '@vue/test-utils';
import { expect, it } from 'vitest';

import { business, flush, JAPANESE, POLISH, type TotalFilterPage } from './mount-cart-checkout';

/** A list page as its test sets it up. */
export interface ListPage extends TotalFilterPage {
  wrapper: VueWrapper;
  find: (testid: string) => DOMWrapper<Element>;
  rows: () => unknown[];
  cells: (index: number) => string[];
}

type Field = HTMLElement & { errorText?: string };

/** The funnel of the table whose test ids start with `id`: its panel, a field of it by name, a value typed in one,
 *  and opening and applying it. */
export function tableFunnel(id: string) {
  const panel = (s: ListPage) => s.find(`${id}-filters-panel`);
  const field = (s: ListPage, name: string) => panel(s).get(`[data-testid="${id}-filter-${name}"]`).element as Field;
  const set = (s: ListPage, name: string, event: string, value: string) =>
    field(s, name).dispatchEvent(new CustomEvent(event, { detail: { value } }));
  async function openFunnel(s: ListPage): Promise<void> {
    await s.find(`${id}-filters-toggle`).trigger('click');
    await flush();
  }
  async function applyFunnel(s: ListPage): Promise<void> {
    await panel(s).get(`[data-testid="${id}-filters-apply"]`).trigger('click');
    await flush();
  }
  return { panel, field, set, openFunnel, applyFunnel };
}

/** The list asks for its newest rows first, 50 a page; once `firstPage` shows, the topbar names the app (the tabbar
 *  says which section). */
export async function expectNewestFirstInTheApp(s: ListPage, firstPage: unknown): Promise<void> {
  expect(s.list()).toEqual([{ sort: '-created_at', limit: 50, offset: 0 }]);
  await s.show(firstPage);
  expect(s.wrapper.findComponent(AppPage).props('title')).toBe('Cart & Checkout');
}

/** The Total of each row as painted, with the narrow spaces of a formatted amount made plain. */
export function totals(s: ListPage): string[] {
  return s.rows().map((_, i) => s.cells(i)[4].replace(/[  ]/g, ' '));
}

/** The table's filters changed to `filters`, as its funnel applies them. */
export async function filterTable(s: ListPage, filters: Record<string, string>): Promise<void> {
  s.table().vm.$emit('filtersChange', filters);
  await flush();
}

export function itReadsThePastedTotal(setup: () => Promise<ListPage>, firstPage: unknown): void {
  it('the total is typed as an amount, read as it is pasted, and one it cannot read says so under its box', async () => {
    const s = await setup();
    await s.result('base.business.get', business());
    await s.show(firstPage);
    const total = s.prop<Array<{ key: string; filter?: unknown }>>('columns').find((c) => c.key === 'total_amount');
    expect(total?.filter).toEqual({ type: 'range', amount: true });
    await filterTable(s, { total_amount_from: '1.250,50', total_amount_to: '1.250' });
    // «1.250» is 1.250 € or 1,25 €: it filters nothing and says both, as every amount filter of the Hub.
    expect(s.list()).toEqual([{ total_amount_min: 125050, sort: '-created_at', limit: 50, offset: 0 }]);
    expect(s.prop('filterErrors')).toEqual({ total_amount_to: 'This amount can be read in two ways: «1.250» could be €1,250.00 or €1.25. Write the decimals so there is no doubt.' });
    await filterTable(s, { total_amount_from: '12' });
    expect(s.prop('filterErrors')).toEqual({});
  });
}

/** The funnel's panel with `status` chosen and `typed` in the Total's `end`: the list asks for `asks` only on «Apply»,
 *  and the funnel counts the two filters. */
export function itFiltersOnApply(
  setup: () => Promise<ListPage>,
  firstPage: unknown,
  { id, status, end, typed, asks }: { id: string; status: string; end: string; typed: string; asks: Record<string, unknown> },
): void {
  const { set, openFunnel, applyFunnel } = tableFunnel(id);
  it('the panel filters on «Apply», by status and by the total, and the funnel counts them', async () => {
    const s = await setup();
    await s.show(firstPage);
    await openFunnel(s);
    set(s, 'status', 'ionChange', status);
    set(s, end, 'ionInput', typed);
    await flush();
    expect(s.list(), 'the panel edits a draft: nothing is asked before «Apply»').toEqual([{ sort: '-created_at', limit: 50, offset: 0 }]);
    await applyFunnel(s);
    expect(s.list()).toEqual([{ ...asks, sort: '-created_at', limit: 50, offset: 0 }]);
    expect(s.find(`${id}-filters-count`).text()).toBe('2');
  });
}

/** A Total typed in the funnel's panel (`end`, as `typed`) that is no amount: it says `says` under its box. */
export function itSaysAnUnreadableTotalInThePanel(
  setup: () => Promise<ListPage>,
  firstPage: unknown,
  { id, end, typed, says }: { id: string; end: string; typed: string; says: string },
): void {
  const { field, set, openFunnel, applyFunnel } = tableFunnel(id);
  it('a Total it cannot read filters nothing, marks the funnel and is said under its box in the panel', async () => {
    const s = await setup();
    await s.result('base.business.get', business());
    await s.show(firstPage);
    await openFunnel(s);
    set(s, end, 'ionInput', typed);
    await applyFunnel(s);
    expect(s.list()).toEqual([{ sort: '-created_at', limit: 50, offset: 0 }]);
    expect(s.find(`${id}-filters-toggle`).attributes('data-invalid')).toBe('true');
    await openFunnel(s);
    expect(field(s, end).errorText).toBe(says);
  });
}

/** `longList` holds more than one page of rows. */
export function itTypesTheTotalInTheBusinessCurrency(setup: () => Promise<ListPage>, longList: unknown): void {
  it('the Total filter is typed in the business’s currency: złoty with its symbol, yen without decimals', async () => {
    const s = await setup();
    await s.result('base.business.get', business(POLISH));
    await filterTable(s, { total_amount_from: '12,50 zł', total_amount_to: 'PLN 100' });
    expect(s.list()).toEqual([{ total_amount_min: 1250, total_amount_max: 10000, sort: '-created_at', limit: 50, offset: 0 }]);

    const yen = await setup();
    await yen.result('base.business.get', business(JAPANESE));
    await filterTable(yen, { total_amount_from: '12', total_amount_to: '12,5' });
    expect(yen.list()).toEqual([{ total_amount_min: 12, sort: '-created_at', limit: 50, offset: 0 }]);
    expect(yen.prop('filterErrors')).toEqual({ total_amount_to: 'This is not an amount. Type a figure, for example 12.' });
  });

  it('an amount typed before the business answers is read again in its currency when it does, from the first page', async () => {
    const s = await setup();
    await s.show(longList);
    await filterTable(s, { total_amount_from: '12' });
    expect(s.list()).toEqual([{ total_amount_min: 1200, sort: '-created_at', limit: 50, offset: 0 }]);
    s.table().vm.$emit('pageChange', 2);
    await flush();
    expect(s.list()).toEqual([{ total_amount_min: 1200, sort: '-created_at', limit: 50, offset: 100 }]);
    await s.result('base.business.get', business(JAPANESE));
    expect(s.list()).toEqual([{ total_amount_min: 12, sort: '-created_at', limit: 50, offset: 0 }]);
  });
}
