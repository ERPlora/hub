// The dashboard's activity feed is `sales`' data, and `sales` is an OPTIONAL module (hub#1211,
// found while reviewing hub#1311): `DashboardPage` read `sales.list` unconditionally on every
// mount, so a hub without `sales` — every empty hub, every salon that never installed a till —
// logged a `404 POST /api/query` on every dashboard load. It is the same defect hub#1211 fixes in
// the SDK's `queryOptional`, one floor up: the shell itself asking the transport to learn a module
// is absent. This pins the feed's read as one that COUNTS requests (the value alone — `[]` — passed
// before the fix and would keep passing after a fix that fixes nothing).
import { describe, expect, it } from 'vitest';

import { loadRecentSales } from './dashboard-activity';

/** A `queryPage` door that records every call and answers a fixed page. */
function countingClient(rows: Record<string, unknown>[] = []) {
  const calls: Array<{ name: string; params: unknown }> = [];
  return {
    calls,
    client: {
      queryPage: async <T = unknown>(name: string, params?: unknown) => {
        calls.push({ name, params });
        return { rows: rows as T[], total: rows.length, limit: 100, offset: 0 };
      },
    },
  };
}

describe('the activity feed only asks `sales` when `sales` is there (hub#1211)', () => {
  it('does not travel when the ACTIVE set proves `sales` is absent', async () => {
    const { client, calls } = countingClient();

    const rows = await loadRecentSales(client, new Set(['inventory', 'services']));

    expect(rows).toEqual([]);
    expect(calls, 'a hub without a till must not ask the till for its sales').toHaveLength(0);
  });

  it('asks `sales.list` — newest first, one page of 100 — when `sales` is active', async () => {
    const { client, calls } = countingClient([
      { id: 's1', created_at: '2026-08-29T10:00:00Z', sale_number: 'T-1', total: 1250, status: 'completed' },
      { id: 's2', created_at: '2026-08-29T09:00:00Z', customer_name: 'Ana', payment_method_name: 'Card', total: 300, status: 'pending' },
    ]);

    const rows = await loadRecentSales(client, new Set(['sales']));

    expect(calls).toEqual([{ name: 'sales.list', params: { limit: 100, sort: 'created_at', dir: 'desc' } }]);
    expect(rows).toEqual([
      { date: '2026-08-29T10:00:00Z', sale: 'T-1', customer: '—', method: '—', amount: 1250, status: 'completed', tone: 'success' },
      { date: '2026-08-29T09:00:00Z', sale: '#s2', customer: 'Ana', method: 'Card', amount: 300, status: 'pending', tone: 'medium' },
    ]);
  });

  it('still travels when the active set is not known yet: unknown is not absent', async () => {
    // Same rule as the SDK's short-circuit: guessing "absent" while the set is unresolved would
    // silently blank the feed of a hub that DOES have a till.
    const { client, calls } = countingClient();

    await loadRecentSales(client, undefined);

    expect(calls).toHaveLength(1);
  });
});
