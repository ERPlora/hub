// Payments → Methods (WORKBOOK «Pantallas · Métodos»; PAYMENT-F01, F08): the live `payment.method.list`
// — Name, Type, Account and Status (Active, Deactivated) —, «Search method…», filters by type and
// state, by name, 50 a page. «New method» and a row (whoever records payments) open the form; a row
// offers Edit and Deactivate, or Activate when it is deactivated. A method is never deleted.
import { DataTable, type DataTableAction, EmptyState, StatusPill } from '@erplora/ui/components';
import { AppPage } from '@erplora/ui/shell';
import { describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import type { MethodOut } from '../operations';
import { EMPLOYEE, flush, type MountOptions, mountPayment, page } from '../__tests__/mount-payment';
import MethodFormModal from '../components/MethodFormModal.vue';
import MethodsPage from './MethodsPage.vue';
import { listFillProblems } from '../../../../frontend/testing/list-fill';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const OP = 'payment.method.list';
const method = (id: string, over: Partial<MethodOut> = {}): MethodOut => ({
  id,
  name: 'BBVA account',
  method_type: 'transfer',
  bank_account_ref: '*1332',
  is_active: true,
  created_at: '2026-10-01T10:00:00Z',
  updated_at: '2026-10-01T10:00:00Z',
  ...over,
});
const BANK = method('m1');
const CASH = method('m2', { name: 'Cash drawer', method_type: 'cash', bank_account_ref: '', is_active: false });
const ROWS = [BANK, CASH];

async function setup(options: MountOptions = {}) {
  const m = await mountPayment(MethodsPage, { path: '/payment/methods', ...options });
  await m.live();
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const rows = () => m.wrapper.findAll('[data-testid="payment-methods-row"]');
  const cells = (i: number) => rows()[i].findAll('[role="cell"]').map((c) => c.text().trim());
  const offered = (row: MethodOut) =>
    prop<DataTableAction<MethodOut>[]>('actions')
      .filter((a) => !a.hidden?.(row))
      .map((a) => a.id);
  return { ...m, table, prop, rows, cells, offered, list: () => m.params(OP), show: (data: unknown) => m.result(OP, data) };
}

describe('MethodsPage', () => {
  it('follows the methods by name, with Name, Type, Account and Status', async () => {
    const s = await setup();
    expect(s.wrapper.findComponent(AppPage).props('title')).toBe('Outgoing payments');
    expect(s.list()).toEqual([{ sort: 'name', limit: 50, offset: 0 }]);
    await s.show(page(ROWS));
    expect(s.prop('searchPlaceholder')).toBe('Search method…');
    expect(s.prop<{ add: string }>('labels').add).toBe('New method');
    expect(s.prop<Array<{ key: string; label: string }>>('columns').map((c) => [c.key, c.label])).toEqual([
      ['name', 'Name'],
      ['method_type', 'Type'],
      ['bank_account_ref', 'Account'],
      ['is_active', 'Status'],
    ]);
    expect(s.cells(0).slice(0, 4)).toEqual(['BBVA account', 'Bank transfer', '*1332', 'Active']);
    expect(s.cells(1).slice(0, 4)).toEqual(['Cash drawer', 'Cash', '', 'Deactivated']);
    expect(s.wrapper.findAllComponents(StatusPill).map((p) => p.props('tone'))).toEqual(['success', 'neutral']);
  });

  it('filters by type and state on the server; none at all says «No payment methods.»', async () => {
    const s = await setup();
    await s.show(page([]));
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No payment methods.');
    const columns = s.prop<Array<{ key: string; filter?: { type: string; key?: string; options?: Array<{ value: string; label: string }> } }>>('columns');
    expect(columns.map((c) => [c.key, c.filter?.type ?? null])).toEqual([
      ['name', null],
      ['method_type', 'select'],
      ['bank_account_ref', null],
      ['is_active', 'select'],
    ]);
    expect(columns[3].filter?.options).toEqual([
      { value: 'true', label: 'Active' },
      { value: 'false', label: 'Deactivated' },
    ]);
    s.table().vm.$emit('filtersChange', { method_type: 'cash', is_active: 'false' });
    s.table().vm.$emit('update:search', 'caja');
    await flush();
    expect(s.list()).toEqual([{ method_type: 'cash', is_active: false, search: 'caja', sort: 'name', limit: 50, offset: 0 }]);
  });

  it('a row offers Edit and Deactivate, or Activate when deactivated, and runs them', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    expect([s.offered(BANK), s.offered(CASH)]).toEqual([
      ['edit', 'deactivate'],
      ['edit', 'activate'],
    ]);
    s.answer(200, { ...BANK, is_active: false });
    s.table().vm.$emit('action', { actionId: 'deactivate', row: BANK });
    await flush();
    s.table().vm.$emit('action', { actionId: 'activate', row: CASH });
    await flush();
    expect(s.sent().map((c) => [c.path, c.body])).toEqual([
      ['/api/payment/methods/deactivate', { id: 'm1' }],
      ['/api/payment/methods/activate', { id: 'm2' }],
    ]);
  });

  it('a double tap on Deactivate sends it once, and the row says it is running', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    s.answer(200, { ...BANK, is_active: false });
    s.table().vm.$emit('action', { actionId: 'deactivate', row: BANK });
    s.table().vm.$emit('action', { actionId: 'deactivate', row: BANK });
    const deactivate = s.prop<DataTableAction<MethodOut>[]>('actions').find((a) => a.id === 'deactivate')!;
    expect([deactivate.loading?.(BANK), deactivate.loading?.(CASH)]).toEqual([true, false]);
    await flush();
    expect(s.sent().map((c) => c.path)).toEqual(['/api/payment/methods/deactivate']);
    const activate = s.prop<DataTableAction<MethodOut>[]>('actions').find((a) => a.id === 'activate')!;
    expect([deactivate.loading?.(BANK), activate.loading?.(CASH)]).toEqual([false, false]);
  });

  it('«New method», a row and its Edit open the form', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    const modal = () => s.wrapper.findComponent(MethodFormModal);
    s.table().vm.$emit('add');
    await flush();
    expect([modal().props('open'), modal().props('method')]).toEqual([true, null]);
    modal().vm.$emit('update:open', false);
    // Editing reads the whole method (`payment.method.get`): the list masks the account.
    s.answerBy({ '/api/payment/methods/detail': [200, CASH] });
    s.table().vm.$emit('rowClick', CASH);
    await flush();
    expect([modal().props('open'), modal().props('method')]).toEqual([true, CASH]);
    modal().vm.$emit('update:open', false);
    s.answerBy({ '/api/payment/methods/detail': [200, { ...BANK, bank_account_ref: 'ES91 2100 0418 4502 0005 1332' }] });
    s.table().vm.$emit('action', { actionId: 'edit', row: BANK });
    await flush();
    expect([modal().props('open'), modal().props('method')]).toEqual([true, BANK]);
    expect(s.sent().map((c) => [c.path, c.query])).toEqual([
      ['/api/payment/methods/detail', { id: 'm2' }],
      ['/api/payment/methods/detail', { id: 'm1' }],
    ]);
  });

  it('an employee only looks', async () => {
    const s = await setup({ session: EMPLOYEE });
    await s.show(page(ROWS));
    expect([s.prop('addable'), s.prop('rowClickable'), s.offered(BANK), s.offered(CASH)]).toEqual([false, false, [], []]);
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.show(page(ROWS));
    expect([s.prop('searchPlaceholder'), s.prop<{ add: string }>('labels').add]).toEqual(['Buscar método…', 'Nuevo método']);
    expect(s.cells(1).slice(0, 4)).toEqual(['Cash drawer', 'Efectivo', '', 'Desactivado']);
  });
});

describe('MethodsPage: the list fills the page (FIX-DATATABLE-HUB)', () => {
  it('AppPage `fill` and its DataTable `fill`, only stacks between them: from the topbar to the tabbar', async () => {
    const s = await setup();
    expect(listFillProblems(s.wrapper)).toEqual([]);
  });
});
