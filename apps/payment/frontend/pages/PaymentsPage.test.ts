// Payments → Payments (WORKBOOK «Pantallas · Pagos»; PAYMENT-F02 to F06): «Outgoing payments», the live
// `payment.payment.list` with the old table's Reference, Date, Beneficiary, Amount and Status (and
// Method in the column chooser), «Search reference or beneficiary…», filters per column (the
// reference and the beneficiary by fragment, the date by day, the amount from / to in euros, the
// status by list), newest payment date first, 50 a page. Each row offers the step it can take, named
// by what it does (Approve, Mark as sent, Mark as completed), and «Cancel payment» while not finished;
// none on a finished one, and only what the person may do. «New payment» opens the form; a payment
// recorded from a later page brings the list back to the first one (the old payments#40).
import { DataTable, type DataTableAction, EmptyState, InlineFeedback, StatusPill } from '@erplora/ui/components';
import { AppPage } from '@erplora/ui/shell';
import { describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import type { PaymentOut, PaymentStatus } from '../operations';
import { EMPLOYEE, flush, type MountOptions, mountPayment, page, RECORDER } from '../__tests__/mount-payment';
import CancelPaymentModal from '../components/CancelPaymentModal.vue';
import PaymentFormModal from '../components/PaymentFormModal.vue';
import PaymentsPage from './PaymentsPage.vue';
import { listFillProblems } from '../../../../frontend/testing/list-fill';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const OP = 'payment.payment.list';
const payment = (id: string, status: PaymentStatus, over: Partial<PaymentOut> = {}): PaymentOut => ({
  id,
  reference: `PAY-20261014-000${id}`,
  method_id: 'm1',
  method_name: 'BBVA account',
  payment_date: '2026-07-13',
  amount: 25000,
  currency: 'EUR',
  beneficiary_name: 'Proveedor Norte SL',
  beneficiary_iban: '',
  concept: '',
  status,
  supplier_invoice_ref: '',
  cancel_reason: '',
  approved_by: '',
  approved_at: null,
  sent_at: null,
  completed_at: null,
  cancelled_by: '',
  cancelled_at: null,
  created_by: 'Ana',
  updated_by: 'Ana',
  created_at: '2026-10-14T10:00:00Z',
  updated_at: '2026-10-14T10:00:00Z',
  ...over,
});
const DRAFT = payment('1', 'draft');
const APPROVED = payment('2', 'approved', { approved_by: 'Boss', approved_at: '2026-10-14T11:00:00Z' });
const SENT = payment('3', 'sent');
const COMPLETED = payment('4', 'completed', { amount: 1999, currency: 'JPY' });
const CANCELLED = payment('5', 'cancelled', { cancel_reason: 'Duplicated' });
const ROWS = [DRAFT, APPROVED, SENT, COMPLETED, CANCELLED];

async function setup(options: MountOptions = {}) {
  const m = await mountPayment(PaymentsPage, { path: '/payment/payments', ...options });
  await m.live();
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const rows = () => m.wrapper.findAll('[data-testid="payment-payments-row"]');
  const cells = (i: number) => rows()[i].findAll('[role="cell"]').map((c) => c.text().trim());
  const action = (id: string) => prop<DataTableAction<PaymentOut>[]>('actions').find((a) => a.id === id)!;
  /** The actions a row offers, by their label. */
  const offered = (row: PaymentOut) =>
    prop<DataTableAction<PaymentOut>[]>('actions')
      .filter((a) => !a.hidden?.(row))
      .map((a) => (typeof a.label === 'function' ? a.label(row) : a.label));
  return { ...m, table, prop, rows, cells, action, offered, list: () => m.params(OP), show: (data: unknown) => m.result(OP, data) };
}

describe('PaymentsPage', () => {
  it('follows the payments newest payment date first, with the old table’s columns', async () => {
    const s = await setup();
    expect(s.list()).toEqual([{ sort: '-payment_date', limit: 50, offset: 0 }]);
    await s.show(page(ROWS));
    expect(s.wrapper.findComponent(AppPage).props('title')).toBe('Outgoing payments');
    expect(s.prop('searchPlaceholder')).toBe('Search reference or beneficiary…');
    expect(s.prop<{ add: string }>('labels').add).toBe('New payment');
    expect(s.prop<Array<{ key: string; label: string; hidden?: boolean }>>('columns').map((c) => [c.key, c.label, !!c.hidden])).toEqual([
      ['reference', 'Reference', false],
      ['payment_date', 'Date', false],
      ['beneficiary_name', 'Beneficiary', false],
      ['amount', 'Amount', false],
      ['status', 'Status', false],
      ['method_name', 'Method', true],
    ]);
    expect(s.cells(0).slice(0, 5)).toEqual(['PAY-20261014-0001', '07/13/2026', 'Proveedor Norte SL', '€250.00', 'Draft']);
    // A payment stored in another currency keeps painting in its own.
    expect(s.cells(3)[3]).toBe('¥1,999');
  });

  it('a cancelled payment shows its reason under the status', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    const pills = s.wrapper.findAllComponents(StatusPill).map((p) => [p.props('label'), p.props('tone')]);
    expect(pills).toEqual([
      ['Draft', 'neutral'],
      ['Approved', 'info'],
      ['Sent', 'warning'],
      ['Completed', 'success'],
      ['Cancelled', 'danger'],
    ]);
    expect(s.cells(4)[4]).toContain('Reason: Duplicated');
  });

  it('filters on the server: the reference and the beneficiary by fragment, the day, the amount in euros, the status', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    const columns = s.prop<Array<{ key: string; filter?: { type: string; options?: Array<{ value: string; label: string }> } }>>('columns');
    expect(columns.map((c) => [c.key, c.filter?.type ?? null])).toEqual([
      ['reference', 'text'],
      ['payment_date', 'date'],
      ['beneficiary_name', 'text'],
      ['amount', 'range'],
      ['status', 'select'],
      ['method_name', null],
    ]);
    expect(columns[4].filter?.options?.map((o) => o.label)).toEqual(['Draft', 'Approved', 'Sent', 'Completed', 'Cancelled']);
    s.table().vm.$emit('filtersChange', {
      reference: '0003',
      payment_date: '2026-08-21',
      beneficiary_name: 'norte',
      amount_from: '12',
      amount_to: '12,5',
      status: 'approved',
    });
    await flush();
    expect(s.list()).toEqual([
      {
        reference: '0003',
        payment_date_from: '2026-08-21',
        payment_date_to: '2026-08-21',
        beneficiary_name: 'norte',
        amount_min: 1200,
        amount_max: 1250,
        status: 'approved',
        sort: '-payment_date',
        limit: 50,
        offset: 0,
      },
    ]);
  });

  it('an amount bound that is not an amount is left out, never «from 0»', async () => {
    const s = await setup();
    s.table().vm.$emit('filtersChange', { amount_from: 'abc' });
    await flush();
    expect(s.list()).toEqual([{ sort: '-payment_date', limit: 50, offset: 0 }]);
  });

  it('searches and sorts on the server; none at all says «No payments.», a search without rows «No results»', async () => {
    const s = await setup();
    await s.show(page([]));
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No payments.');
    s.table().vm.$emit('sortChange', { sort: 'amount', dir: 'asc' });
    s.table().vm.$emit('update:search', 'norte');
    await flush();
    expect(s.list()).toEqual([{ search: 'norte', sort: 'amount', limit: 50, offset: 0 }]);
    await s.reopen();
    await s.show(page([]));
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No results');
  });

  it('each row offers the step it can take, named by what it does, and Cancel while not finished', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    expect(ROWS.map((row) => s.offered(row))).toEqual([
      ['Approve', 'Cancel payment'],
      ['Mark as sent', 'Cancel payment'],
      ['Mark as completed', 'Cancel payment'],
      [],
      [],
    ]);
  });

  it('a step sends its command; a refusal shows above the table', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    s.answer(200, { ...DRAFT, status: 'approved' });
    s.table().vm.$emit('action', { actionId: 'advance', row: DRAFT });
    await flush();
    s.table().vm.$emit('action', { actionId: 'advance', row: APPROVED });
    await flush();
    s.table().vm.$emit('action', { actionId: 'advance', row: SENT });
    await flush();
    expect(s.sent().map((c) => [c.path, c.body])).toEqual([
      ['/api/payment/payments/approve', { id: '1' }],
      ['/api/payment/payments/mark_sent', { id: '2' }],
      ['/api/payment/payments/mark_completed', { id: '3' }],
    ]);
    const message = 'Only a draft payment can be approved; this one is Approved.';
    s.answer(409, { error: { code: 'payment.invalid_transition', message } });
    s.table().vm.$emit('action', { actionId: 'advance', row: DRAFT });
    await flush();
    const banner = s.wrapper.findAllComponents(InlineFeedback).find((b) => b.attributes('data-testid') === 'payment-payments-row-error');
    expect([banner?.props('heading'), banner?.text()]).toEqual(['The payment could not be changed', expect.stringContaining(message)]);
  });

  it('a payment that went past Draft shows who approved it under its status', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    expect(s.cells(1)[4]).toContain('Approved by Boss');
    expect(s.cells(0)[4]).not.toContain('Approved by');
  });

  it('a double tap on a step sends it once, and the row says it is running', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    s.answer(200, { ...DRAFT, status: 'approved' });
    s.table().vm.$emit('action', { actionId: 'advance', row: DRAFT });
    s.table().vm.$emit('action', { actionId: 'advance', row: DRAFT });
    expect(s.action('advance').loading?.(DRAFT)).toBe(true);
    expect(s.action('advance').loading?.(APPROVED)).toBe(false);
    await flush();
    expect(s.sent().map((c) => c.path)).toEqual(['/api/payment/payments/approve']);
    expect(s.action('advance').loading?.(DRAFT)).toBe(false);
  });

  it('Cancel payment opens its form with the row', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    s.table().vm.$emit('action', { actionId: 'cancel', row: APPROVED });
    await flush();
    const modal = s.wrapper.findComponent(CancelPaymentModal);
    expect([modal.props('open'), modal.props('payment')]).toEqual([true, APPROVED]);
  });

  it('«New payment» opens the form; a payment recorded from a later page brings the list back to the first one', async () => {
    const s = await setup();
    await s.show(page(ROWS, 120));
    s.table().vm.$emit('pageChange', 2);
    await flush();
    expect(s.list()).toEqual([{ sort: '-payment_date', limit: 50, offset: 100 }]);
    s.table().vm.$emit('add');
    await flush();
    const modal = s.wrapper.findComponent(PaymentFormModal);
    expect(modal.props('open')).toBe(true);
    modal.vm.$emit('created', DRAFT);
    await flush();
    expect(s.list()).toEqual([{ sort: '-payment_date', limit: 50, offset: 0 }]);
  });

  it('who records but does not approve sends and completes, but neither approves nor cancels', async () => {
    const s = await setup({ session: RECORDER });
    await s.show(page(ROWS));
    expect(s.prop('addable')).toBe(true);
    expect(ROWS.slice(0, 3).map((row) => s.offered(row))).toEqual([[], ['Mark as sent'], ['Mark as completed']]);
  });

  it('an employee only looks', async () => {
    const s = await setup({ session: EMPLOYEE });
    await s.show(page(ROWS));
    expect(s.prop('addable')).toBe(false);
    expect(ROWS.map((row) => s.offered(row))).toEqual([[], [], [], [], []]);
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.show(page(ROWS));
    expect(s.wrapper.findComponent(AppPage).props('title')).toBe('Pagos salientes');
    expect([s.prop('searchPlaceholder'), s.prop<{ add: string }>('labels').add]).toEqual(['Buscar referencia o beneficiario…', 'Nuevo pago']);
    expect(s.cells(0).slice(1, 5).map((cell) => cell.replace(/[\u00a0\u202f]/g, ' '))).toEqual(['13/07/2026', 'Proveedor Norte SL', '250,00 €', 'Borrador']);
    expect(s.cells(1)[4]).toContain('Aprobado por Boss');
    expect(s.offered(APPROVED)).toEqual(['Marcar como enviado', 'Cancelar pago']);
  });
});

describe('PaymentsPage: the list fills the page (FIX-DATATABLE-HUB)', () => {
  it('AppPage `fill` and its DataTable `fill`, only stacks between them: from the topbar to the tabbar', async () => {
    const s = await setup();
    expect(listFillProblems(s.wrapper)).toEqual([]);
  });
});
