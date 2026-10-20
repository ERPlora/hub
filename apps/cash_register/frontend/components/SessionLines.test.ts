// The lines of a session (CASH_REGISTER-F11) — or those that fell in none (F17) — in a server-side
// DataTable, newest first, 50 a page, table or cards: When, Type, Amount with its sign, Method, Concept (a
// sale named by its document, a void «Void of …», a refund «Refund of …», a line by hand its concept).
// They re-run by themselves on a sale, a movement or a close: nothing here refetches.
import { DataTable } from '@erplora/ui/components';
import { describe, expect, it } from 'vitest';
import type { Component } from 'vue';

import { mountCash } from '../__tests__/mount-cash-register';
import { plain } from '../lib/money';
import type { MovementRow } from '../operations';
import SessionLines from './SessionLines.vue';

const OP = 'cash_register.movement.list';

const line = (key: string, over: Partial<MovementRow> = {}): MovementRow => ({
  key,
  session_id: 's1',
  type: 'sale',
  amount: 300,
  signed_amount: 300,
  method_type: 'cash',
  method_name: 'Cash',
  description: '',
  sale_id: 'v1',
  sale_number: '20261014-0007',
  document_type: 'ticket',
  gift_total: 0,
  created_at: '2026-10-14T10:05:00Z',
  created_by: 'ana',
  ...over,
});

async function setup(query: Record<string, unknown> = { session_id: 's1' }, locale: 'en' | 'es' = 'en') {
  const m = await mountCash(SessionLines, { props: { query, testid: 'lines', emptyMessage: 'Nothing here.' }, locale });
  await m.live();
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const cells = (i: number) =>
    m.wrapper.findAll('[data-testid="lines-row"]')[i].findAll('[role="cell"]').map((c) => plain(c.text()).replace(/\s+/g, ' ').trim());
  return { ...m, table, cells };
}

describe('SessionLines', () => {
  it('follows the session’s lines newest first, 50 a page', async () => {
    const s = await setup();
    expect(s.params(OP)).toEqual([{ session_id: 's1', sort: 'created_at', dir: 'desc', limit: 50, offset: 0 }]);
    expect(s.table().props()).toMatchObject({ serverSide: true, testid: 'lines', pageSize: 50, loading: true });
  });

  it('names each line: its type, its signed amount, its method and its document', async () => {
    const s = await setup();
    await s.result(OP, {
      rows: [
        line('sale-p1'),
        line('void-p1', { type: 'void', signed_amount: -300, method_type: 'card', method_name: 'Card' }),
        line('refund-r1', { type: 'refund', signed_amount: -150, method_name: 'Bizum', method_type: 'other', document_type: 'invoice' }),
        line('m1', { type: 'out', amount: 500, signed_amount: -500, method_name: '', description: 'Bread supplier', sale_id: null, sale_number: '' }),
      ],
      total: 4,
      limit: 50,
      offset: 0,
    });
    expect(s.cells(0).slice(1)).toEqual(['Sale', '+€3.00', 'Cash', 'Ticket 20261014-0007']);
    expect(s.cells(1).slice(1)).toEqual(['Void', '-€3.00', 'Card', 'Void of Ticket 20261014-0007']);
    expect(s.cells(2).slice(1)).toEqual(['Refund', '-€1.50', 'Bizum', 'Refund of Invoice 20261014-0007']);
    expect(s.cells(3).slice(1)).toEqual(['Cash out', '-€5.00', 'Cash', 'Bread supplier']);
  });

  it('no column a narrow box gives up hides the document a line is: a narrow table turns to cards (F11, F17)', async () => {
    const s = await setup({ unassigned: true });
    const columns = s.table().props('columns') as { key: string; priority?: string }[];
    expect(columns.filter((column) => column.priority === 'low').map((column) => column.key)).toEqual([]);
    expect(s.table().props('views')).toEqual(['table', 'cards']);
  });

  it('the unassigned lines are the same table over another query', async () => {
    const s = await setup({ unassigned: true });
    expect(s.params(OP)).toEqual([{ unassigned: true, sort: 'created_at', dir: 'desc', limit: 50, offset: 0 }]);
    await s.result(OP, { rows: [], total: 0, limit: 50, offset: 0 });
    expect(s.find('lines-empty').text()).toContain('Nothing here.');
  });

  it('speaks Spanish', async () => {
    const s = await setup({ session_id: 's1' }, 'es');
    await s.result(OP, { rows: [line('sale-p1')], total: 1, limit: 50, offset: 0 });
    expect(s.cells(0).slice(1)).toEqual(['Venta', '+3,00 €', 'Efectivo', 'Tique 20261014-0007']);
  });
});
