// What the tests of Pricing's two tables, price lists and discount rules, check alike: they open on the active rows,
// and a load that fails says so with «Retry». Each table's test passes its own setup.
import { DataTable } from '@erplora/ui/components';
import type { OpName } from '@erplora/ui/sdk';
import { expect, it } from 'vitest';
import type { Component } from 'vue';

import { errorFrame, flush, type mountPricing } from './mount-pricing';

/** A table of Pricing as its test sets it up: mounted, live, with its DataTable's props and its first page to show. */
export type PricingTable = Awaited<ReturnType<typeof mountPricing>> & {
  table: () => { vm: { $emit: (event: string, ...args: unknown[]) => void } };
  prop: <T = unknown>(name: string) => T;
  show: (data: unknown) => Promise<void>;
};

type Mounted = Awaited<ReturnType<typeof mountPricing>>;
type RowAction = { id: string; hidden?: (row: unknown) => boolean };

/** What a test reads of the mounted table `testid` of a Pricing screen: its DataTable and its props, its rows and their
 *  cells, the actions a row offers, and how it shows a page of `op`. */
export function tableOf(m: Mounted, testid: string, op: OpName) {
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const rows = () => m.wrapper.findAll(`[data-testid="${testid}-row"]`);
  const cells = (i: number) => rows()[i].findAll('[role="cell"]').map((c) => c.text().trim());
  const shownFor = (row: unknown) => prop<RowAction[]>('actions').filter((a) => !a.hidden?.(row)).map((a) => a.id);
  return { ...m, table, prop, rows, cells, shownFor, show: (data: unknown) => m.result(op, data) };
}

/** The table of `op`, whose blank Status option is every `noun`. */
export function itStartsOnTheActiveOnes(setup: () => Promise<PricingTable>, op: OpName, noun: string): void {
  it(`starts on the active ones, its Status filter says so, and its blank option is every ${noun}`, async () => {
    const s = await setup();
    expect(s.prop('filters')).toEqual({ status: 'active' });
    const status = s.prop<Array<{ key: string; filter?: { options?: Array<{ value: string; label: string }> } }>>('columns').find(
      (c) => c.key === 'status',
    );
    // The table's own blank option is «All»: no second «All» beside it that means something else.
    expect(status?.filter?.options).toEqual([
      { value: 'active', label: 'Active' },
      { value: 'inactive', label: 'Inactive' },
    ]);
    s.table().vm.$emit('filtersChange', { status: '' });
    await flush();
    expect(s.params(op)).toEqual([{ status: 'all', sort: 'name', dir: 'asc', limit: 50, offset: 0 }]);
    s.table().vm.$emit('filtersChange', { status: 'inactive' });
    await flush();
    expect(s.params(op)).toEqual([{ status: 'inactive', sort: 'name', dir: 'asc', limit: 50, offset: 0 }]);
  });
}

/** The table of `op`, whose failed load says `loadError`, and whose retried load answers `firstPage`. */
export function itRetriesAFailedLoad(setup: () => Promise<PricingTable>, op: OpName, loadError: string, firstPage: unknown): void {
  it('says it is loading until the first answer, and a load that fails says so with «Retry»', async () => {
    const s = await setup();
    expect(s.prop('loading')).toBe(true);
    expect(s.prop('error')).toBeUndefined();
    s.net.lastStream().push(errorFrame(s.subId(op), 'internal_error'));
    await flush();
    expect(s.prop('loading')).toBe(false);
    expect(s.prop('error')).toBe(loadError);
    expect(s.prop<{ retry: string; loadError: string }>('labels')).toMatchObject({ retry: 'Retry', loadError });
    // «Retry» asks again (the stream reopens and the server runs the query anew); its answer clears the error.
    const streams = s.net.streams.length;
    s.table().vm.$emit('retry');
    await flush();
    expect(s.net.streams.length).toBe(streams + 1);
    await s.show(firstPage);
    expect(s.prop('error')).toBeUndefined();
    expect(s.prop('loading')).toBe(false);
  });
}
