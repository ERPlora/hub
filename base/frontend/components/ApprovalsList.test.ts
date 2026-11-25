import { DataTable } from '@erplora/ui/components';
import { afterEach, describe, expect, it } from 'vitest';

import { errorFrame, flush, mountBase, subId } from '../__tests__/mount-base';
import type { ApprovalRow } from '../operations/approvals';
import ApprovalsExportButton from './ApprovalsExportButton.vue';
import ApprovalsList from './ApprovalsList.vue';

function approval(fields: Partial<ApprovalRow> = {}): ApprovalRow {
  return {
    id: '0199aaaa-0000-7000-8000-000000000001',
    at: '2026-10-24T09:30:00Z',
    action: 'Void a sale',
    operation_label: 'Void a sale',
    operation: 'sale.sale.void',
    requested_by: 'Eva',
    approved_by: 'Adam',
    way: 'pin',
    used: true,
    used_at: '2026-10-24T09:30:05Z',
    ...fields,
  };
}

async function open(options: Parameters<typeof mountBase>[1] = {}) {
  const m = await mountBase(ApprovalsList, { path: '/employees#approvals', routes: ['/employees'], ...options });
  const call = await m.live();
  return { ...m, call };
}

afterEach(() => {
  document.body.innerHTML = '';
});

describe('ApprovalsList', () => {
  it('follows the record live and explains it', async () => {
    const m = await open({ locale: 'es' });
    expect(m.client.stream.subscriptions('base.approval.list').map((sub) => sub.params)).toEqual([{}]);
    expect(m.wrapper.text()).toContain(
      'Cada acción que puede necesitar la autorización de un encargado: quién la hizo, quién la autorizó y con qué. Nadie, tampoco un administrador, puede editarlo ni borrarlo.',
    );
  });

  it('a row per approval: what in words, who approved, who asked, how and whether it was used', async () => {
    const m = await open({ locale: 'es' });
    await m.result(m.call, 'base.approval.list', {
      approvals: [approval(), approval({ id: '0199aaaa-0000-7000-8000-000000000002', way: 'badge', used: false, used_at: null })],
    });
    const rows = m.wrapper.findAll('[data-testid="approvals-row"]');
    expect(rows).toHaveLength(2);
    expect(rows[0].text()).toContain('Void a sale');
    expect(rows[0].text()).not.toContain('sale.sale.void');
    expect(rows[0].text()).toContain('Adam');
    expect(rows[0].text()).toContain('Eva');
    expect(rows[0].find('[data-testid="approvals-way"]').text()).toBe('PIN');
    expect(rows[1].find('[data-testid="approvals-way"]').text()).toBe('Placa');
    expect(rows[0].find('[data-testid="approvals-used"]').text()).toBe('Hecha');
    expect(rows[1].find('[data-testid="approvals-used"]').text()).toBe('Sin hacer');
  });

  it.each([
    ['en', 'Their role', 'Done'],
    ['es', 'Su rol', 'Hecha'],
  ] as const)('what somebody did by their role names who did it and nobody who approved it (%s)', async (locale, way, state) => {
    const m = await open({ locale });
    await m.result(m.call, 'base.approval.list', {
      approvals: [approval({ requested_by: 'Mario', approved_by: '', way: 'role' })],
    });
    const row = m.wrapper.get('[data-testid="approvals-row"]');
    expect(row.text()).toContain('Mario');
    expect(row.text()).not.toContain('Adam');
    expect(row.get('[data-testid="approvals-way"]').text()).toBe(way);
    expect(row.get('[data-testid="approvals-used"]').text()).toBe(state);
  });

  it('is read by its columns: when, what, who approved it, who, how and whether it was done', async () => {
    const m = await open({ locale: 'es' });
    await m.result(m.call, 'base.approval.list', { approvals: [approval()] });
    // DataTable is generic: its props are read as a plain record.
    const props = m.wrapper.getComponent(DataTable).props() as Record<string, unknown>;
    expect((props.columns as { label: string }[]).map((column) => column.label)).toEqual([
      'Cuándo',
      'Acción',
      'Autorizado por',
      'Quién',
      'Con',
      'Estado',
    ]);
  });

  it('shows each row with its figure and offers each action once, without figures, behind the funnel', async () => {
    const m = await open({ locale: 'es' });
    const line = { operation: 'sale.order.set_line_discount_over_limit', operation_label: 'Descontar una línea por encima del máximo' };
    await m.result(m.call, 'base.approval.list', {
      approvals: [
        approval({ ...line, action: 'Descontar una línea un 50\u00a0%' }),
        approval({ ...line, id: '0199aaaa-0000-7000-8000-000000000002', action: 'Descontar una línea un 30\u00a0%' }),
      ],
    });
    expect(m.wrapper.findAll('[data-testid="approvals-row"]').map((row) => row.text())).toEqual([
      expect.stringContaining('Descontar una línea un 50\u00a0%'),
      expect.stringContaining('Descontar una línea un 30\u00a0%'),
    ]);
    const props = m.wrapper.getComponent(DataTable).props() as Record<string, unknown>;
    const action = (props.columns as { key: string; filter?: { options?: unknown } }[]).find((c) => c.key === 'action');
    expect(action?.filter?.options).toEqual([
      { value: 'sale.order.set_line_discount_over_limit', label: 'Descontar una línea por encima del máximo' },
    ]);
  });

  it('filters by day, action, how and whether it was used behind the funnel', async () => {
    const m = await open({ locale: 'es' });
    await m.result(m.call, 'base.approval.list', {
      approvals: [
        approval(),
        approval({
          id: '0199aaaa-0000-7000-8000-000000000002',
          action: 'Refund a sale',
          operation_label: 'Refund a sale',
          operation: 'sale.sale.refund',
        }),
        approval({ id: '0199aaaa-0000-7000-8000-000000000003', way: 'badge', used: false, used_at: null }),
      ],
    });
    // DataTable is generic: its props are read as a plain record.
    const props = m.wrapper.getComponent(DataTable).props() as Record<string, unknown>;
    expect(props.filterable).toBe(true);
    const columns = props.columns as { key: string; filter?: unknown }[];
    expect(columns.filter((c) => c.filter).map((c) => [c.key, c.filter])).toEqual([
      ['at', { type: 'daterange' }],
      [
        'action',
        {
          type: 'select',
          key: 'operation',
          options: [
            { value: 'sale.sale.refund', label: 'Refund a sale' },
            { value: 'sale.sale.void', label: 'Void a sale' },
          ],
        },
      ],
      [
        'way',
        {
          type: 'select',
          options: [
            { value: 'pin', label: 'PIN' },
            { value: 'badge', label: 'Placa' },
            { value: 'role', label: 'Su rol' },
          ],
        },
      ],
      [
        'used',
        {
          type: 'select',
          options: [
            { value: 'true', label: 'Hecha' },
            { value: 'false', label: 'Sin hacer' },
          ],
        },
      ],
    ]);
  });

  it('carries «Export CSV» in its bar, with the search and the filters on screen', async () => {
    const m = await open();
    await m.result(m.call, 'base.approval.list', { approvals: [approval()] });
    const table = m.wrapper.getComponent(DataTable);
    const exported = () => m.wrapper.getComponent(ApprovalsExportButton).props('query');
    expect(table.find('[data-testid="approvals-export"]').exists()).toBe(true);
    expect(exported()).toEqual({});
    table.vm.$emit('update:search', ' eva ');
    table.vm.$emit('update:filters', { at_from: '2026-10-01', way: 'pin', used: 'false' });
    await flush();
    expect(exported()).toEqual({ search: 'eva', at_from: '2026-10-01', way: 'pin', used: 'false' });
    // DataTable is generic: its props are read as a plain record.
    const props = table.props() as Record<string, unknown>;
    expect([props.search, props.filters]).toEqual([' eva ', { at_from: '2026-10-01', way: 'pin', used: 'false' }]);
  });

  it('none yet says nothing of the kind was done', async () => {
    const m = await open({ locale: 'es' });
    await m.result(m.call, 'base.approval.list', { approvals: [] });
    expect(m.wrapper.text()).toContain('Todavía no hay ninguna acción de este tipo en este negocio.');
  });

  it('a record that cannot be read says so with «Retry», never «nobody»', async () => {
    const m = await open();
    m.call.push(errorFrame(subId(m.client, 'base.approval.list'), 'internal_error'));
    await flush();
    expect(m.wrapper.text()).toContain('Could not load the record of approvals.');
    expect(m.wrapper.text()).not.toContain('There is no action of this kind');
    expect(m.wrapper.find('[data-testid="approvals-retry"]').exists()).toBe(true);
  });
});
