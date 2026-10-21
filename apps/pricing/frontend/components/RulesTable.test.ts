// The «Discount rules» table of Price Lists (PRICING-F09 to F12): the live `pricing.rule.list` in a
// server-side DataTable — Code, Name, Type, Value (with its unit), Applies to, Validity, Priority and
// Status —, «Search code or name…», column filters, 50 a page by name. Whoever manages gets «+», Edit,
// Deactivate (asking first) and Activate.
import { DataTable, EmptyState } from '@erplora/ui/components';
import { describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import { rule } from '../__tests__/fixtures';
import { click, EMPLOYEE, errorFrame, flush, mountPricing, type MountOptions, page, settle } from '../__tests__/mount-pricing';
import RuleFormModal from './RuleFormModal.vue';
import RulesTable from './RulesTable.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const OP = 'pricing.rule.list';
const TEN = rule();
const FIX = rule({ id: 'r2', code: 'FIX', name: 'Fifty off', rule_type: 'fixed', percent: null, amount: 50, applies_to: 'product', product_id: 'p1', product_name: 'Shampoo', priority: 5 });
const OFF = rule({ id: 'r3', code: 'OFF', name: 'Old', rule_type: 'buy_x_get_y', percent: null, buy_quantity: 2, get_quantity: 1, is_active: false, customer_group_id: 'g1', customer_group_name: 'VIP', valid_until: '2026-06-30' });

type Action = { id: string; hidden?: (row: unknown) => boolean };

async function setup(options: MountOptions = {}) {
  const m = await mountPricing(RulesTable, options);
  await m.live();
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const rows = () => m.wrapper.findAll('[data-testid="pricing-rules-row"]');
  const cells = (i: number) => rows()[i].findAll('[role="cell"]').map((c) => c.text().trim());
  const shownFor = (row: unknown) => prop<Action[]>('actions').filter((a) => !a.hidden?.(row)).map((a) => a.id);
  return { ...m, table, prop, rows, cells, shownFor, show: (data: unknown) => m.result(OP, data) };
}

describe('RulesTable', () => {
  it('follows the rules by name, 50 from the first', async () => {
    const s = await setup();
    expect(s.params(OP)).toEqual([{ status: 'active', sort: 'name', dir: 'asc', limit: 50, offset: 0 }]);
    await s.show(page([TEN, FIX]));
    expect(s.table().props()).toMatchObject({ serverSide: true, searchable: true, testid: 'pricing-rules', total: 2 });
    // The column filters wait behind the toolbar's funnel, as in the old table (PLAN-MIGRATIONS §13).
    expect(s.prop('filterable')).toBe(true);
    expect(s.prop<{ add: string }>('labels').add).toBe('New discount rule');
  });

  it('paints Code, Name, Type, Value with its unit, Applies to, Validity, Priority and Status', async () => {
    const s = await setup();
    await s.show(page([TEN, FIX, OFF]));
    expect(s.prop<Array<{ key: string; label: string; sortable?: boolean }>>('columns').map((c) => [c.key, c.label, !!c.sortable])).toEqual([
      ['code', 'Code', true],
      ['name', 'Name', true],
      ['rule_type', 'Type', true],
      ['value', 'Value', false],
      ['applies_to', 'Applies to', false],
      ['validity', 'Validity', false],
      ['priority', 'Priority', true],
      ['status', 'Status', false],
    ]);
    expect(s.cells(0).slice(0, 8)).toEqual(['TEN', 'Ten off', 'Percentage', '10%', 'Everything', 'Always', '100', 'Active']);
    expect(s.cells(1).slice(2, 5)).toEqual(['Amount per unit', '€0.50 per unit', 'Shampoo']);
    expect(s.cells(2).slice(2, 8)).toEqual(['Buy X, get Y', 'Buy 2, get 1', 'Everything · VIP', 'Until Jun 30, 2026', '100', 'Inactive']);
  });

  it('filters by column and searches and sorts on the server', async () => {
    const s = await setup();
    s.table().vm.$emit('filtersChange', { code: 't', rule_type: 'percent', applies_to: 'all', status: 'inactive' });
    s.table().vm.$emit('sortChange', { sort: 'priority', dir: 'asc' });
    s.table().vm.$emit('update:search', 'ten');
    await flush();
    expect(s.params(OP)).toEqual([
      { code: 't', rule_type: 'percent', applies_to: 'all', status: 'inactive', search: 'ten', sort: 'priority', dir: 'asc', limit: 50, offset: 0 },
    ]);
  });

  it('starts on the active ones, its Status filter says so, and its blank option is every rule (pm#254)', async () => {
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
    expect(s.params(OP)).toEqual([{ status: 'all', sort: 'name', dir: 'asc', limit: 50, offset: 0 }]);
    s.table().vm.$emit('filtersChange', { status: 'inactive' });
    await flush();
    expect(s.params(OP)).toEqual([{ status: 'inactive', sort: 'name', dir: 'asc', limit: 50, offset: 0 }]);
  });

  it('with only the default filter, an empty answer is «No discount rules.», not a search without results', async () => {
    const s = await setup();
    await s.show(page([]));
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No discount rules.');
    s.table().vm.$emit('filtersChange', { status: 'active' });
    await flush();
    await s.show(page([]));
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No discount rules.');
  });

  it('says it is loading until the first answer, and a load that fails says so with «Retry» (pm#611, pm#533)', async () => {
    const s = await setup();
    expect(s.prop('loading')).toBe(true);
    expect(s.prop('error')).toBeUndefined();
    s.net.lastStream().push(errorFrame(s.subId(OP), 'internal_error'));
    await flush();
    expect(s.prop('loading')).toBe(false);
    expect(s.prop('error')).toBe('The discount rules could not be loaded.');
    expect(s.prop<{ retry: string; loadError: string }>('labels')).toMatchObject({ retry: 'Retry', loadError: 'The discount rules could not be loaded.' });
    // «Retry» asks again (the stream reopens and the server runs the query anew); its answer clears the error.
    const streams = s.net.streams.length;
    s.table().vm.$emit('retry');
    await flush();
    expect(s.net.streams.length).toBe(streams + 1);
    await s.show(page([TEN]));
    expect(s.prop('error')).toBeUndefined();
    expect(s.prop('loading')).toBe(false);
  });

  it('no rule at all says «No discount rules.»', async () => {
    const s = await setup();
    await s.show(page([]));
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No discount rules.');
  });

  it('«+» and Edit open the form; Deactivate asks first; Activate runs at once', async () => {
    const s = await setup();
    await s.show(page([TEN, OFF]));
    expect(s.shownFor(TEN)).toEqual(['edit', 'deactivate']);
    expect(s.shownFor(OFF)).toEqual(['edit', 'activate']);
    s.table().vm.$emit('add');
    await flush();
    expect(s.wrapper.findComponent(RuleFormModal).props()).toMatchObject({ open: true, rule: null });
    s.table().vm.$emit('action', { actionId: 'edit', row: TEN });
    await flush();
    expect(s.wrapper.findComponent(RuleFormModal).props('rule')).toEqual(TEN);
    s.table().vm.$emit('action', { actionId: 'deactivate', row: TEN });
    await settle();
    expect(s.inDoc('pricing-rules-deactivate')?.textContent).toContain('Ten off will stop applying to new sales.');
    s.answer(200, { ...TEN, is_active: false });
    await click(s.inDoc('pricing-rules-deactivate-submit'));
    s.table().vm.$emit('action', { actionId: 'activate', row: OFF });
    await flush();
    expect(s.sent().map((call) => [call.path, call.body])).toEqual([
      ['/api/pricing/rules/deactivate', { id: 'r1' }],
      ['/api/pricing/rules/activate', { id: 'r3' }],
    ]);
  });

  it('an employee reads the rules without acting on them', async () => {
    const s = await setup({ session: EMPLOYEE });
    await s.show(page([TEN]));
    expect([s.prop('addable'), s.shownFor(TEN)]).toEqual([false, []]);
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.show(page([FIX]));
    expect(s.cells(0).slice(2, 4)).toEqual(['Importe por unidad', '0,50 € por unidad']);
  });
});
