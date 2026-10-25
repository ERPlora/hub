// Employees › Approvals (BASE-G145; the old hub's HUB_SHELL-F93): the record of each action that needed a manager's PIN,
// live (`base.approval.list`), read only. Its explanation, then a row per approval: when, what in words (never the
// command's technical name), who approved it, who asked, how (PIN or badge) and whether it was used; search by person or
// action. Empty, it says nobody had to approve anything yet; a record that cannot be read says so with «Retry».
import { DataTable } from '@erplora/ui/components';
import { afterEach, describe, expect, it } from 'vitest';

import { errorFrame, flush, mountBase, subId } from '../__tests__/mount-base';
import type { ApprovalRow } from '../operations';
import ApprovalsExportButton from './ApprovalsExportButton.vue';
import ApprovalsList from './ApprovalsList.vue';

function approval(fields: Partial<ApprovalRow> = {}): ApprovalRow {
  return {
    id: '0199aaaa-0000-7000-8000-000000000001',
    at: '2026-10-24T09:30:00Z',
    action: 'Void a sale',
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
      'Cada acción que necesitó el PIN de un encargado: quién la pidió, quién la autorizó y para qué. Nadie, tampoco un administrador, puede editarlo ni borrarlo.',
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
    expect(rows[0].find('[data-testid="approvals-used"]').text()).toBe('Usada');
    expect(rows[1].find('[data-testid="approvals-used"]').text()).toBe('Sin usar');
  });

  // The old hub filtered the record by dates, action and level (HUB_SHELL-F93): here by day, action, how and whether it
  // was used, behind the funnel; the actions offered are the ones on the record, in words, each once.
  it('filters by day, action, how and whether it was used behind the funnel', async () => {
    const m = await open({ locale: 'es' });
    await m.result(m.call, 'base.approval.list', {
      approvals: [
        approval(),
        approval({ id: '0199aaaa-0000-7000-8000-000000000002', action: 'Refund a sale', operation: 'sale.sale.refund' }),
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
          ],
        },
      ],
      [
        'used',
        {
          type: 'select',
          options: [
            { value: 'true', label: 'Usada' },
            { value: 'false', label: 'Sin usar' },
          ],
        },
      ],
    ]);
  });

  // The old hub's record had its download (HUB_SHELL-F93): «Export CSV» in the table's bar asks for the file with what
  // the person has on screen, the search and the active filters, and nothing else.
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

  it('none yet says nobody had to approve anything', async () => {
    const m = await open({ locale: 'es' });
    await m.result(m.call, 'base.approval.list', { approvals: [] });
    expect(m.wrapper.text()).toContain('Todavía nadie ha tenido que autorizar nada en este negocio.');
  });

  it('a record that cannot be read says so with «Retry», never «nobody»', async () => {
    const m = await open();
    m.call.push(errorFrame(subId(m.client, 'base.approval.list'), 'internal_error'));
    await flush();
    expect(m.wrapper.text()).toContain('Could not load the record of approvals.');
    expect(m.wrapper.text()).not.toContain('Nobody has had to approve anything');
    expect(m.wrapper.find('[data-testid="approvals-retry"]').exists()).toBe(true);
  });
});
