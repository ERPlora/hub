// hub#512 — the READ of the PIN approval record (`_elevation_audit`, ADR-0265).
// hub#884 — the read is PAGED: the runtime serves `{rows,total,limit,offset}` and the shell asks
// for one page at a time through the SDK's list controller — the same engine, the same contract,
// every other list of the product uses.
//
// The runtime has written a receipt per spent approval since system migration v26, and until this
// screen the only way to read it was a SQL session against the customer's own database. The query
// (`hub.approvals.list`, `crates/runtime/src/hub_users.rs`) resolves both ids to names with a LEFT
// JOIN and now paginates through the runtime's list engine; what is fixed here is how the shell
// reads it:
//
//   - one PAGE crosses the wire, never the trail. The audit grows forever by design, so «download
//     it all and filter in memory» stops being a screen and starts being megabytes per open;
//   - the order is the QUERY's (`created_at DESC` by default). An audit trail that a screen
//     re-sorts on a whim is one where two people see a different "last approval";
//   - a receipt whose person was deleted STILL has a row. The JOIN leaves the name empty on
//     purpose — losing the row would lose the audit, which is the one thing it may not do;
//   - a broken answer is NOT an empty record. `parseApprovals` returns nothing for a shape it does
//     not know, and a failed page lands in the controller's `error`, so the panel can say «could
//     not load» instead of «nobody has ever approved anything».
import { describe, expect, it, vi } from 'vitest';

import { APPROVALS_QUERY, createApprovalsController, parseApprovals } from './approvals';

/** Two receipts as the runtime emits them: newest first, snake_case, both names resolved. */
const ROWS = [
  {
    id: 'a2',
    command: 'sales.void_line',
    permission: 'sales.void',
    created_by: 'u-cashier',
    created_by_name: 'Marta',
    approved_by: 'u-manager',
    approved_by_name: 'Sofía',
    payload_fingerprint: 'ff01',
    created_at: '2026-08-11T20:15:00Z',
  },
  {
    id: 'a1',
    command: 'sales.open_drawer',
    permission: 'sales.drawer',
    created_by: 'u-cashier',
    created_by_name: 'Marta',
    approved_by: 'u-manager',
    approved_by_name: 'Sofía',
    payload_fingerprint: 'ff00',
    created_at: '2026-08-11T09:02:00Z',
  },
];

/** A client whose `queryPage` answers one page of the trail, the way the runtime does. */
function clientAnswering(rows: unknown[], total = rows.length) {
  return {
    queryPage: vi.fn().mockResolvedValue({ rows, total, limit: 10, offset: 0 }),
  };
}

describe('approvals · reading the record one page at a time', () => {
  it('asks the core query that owns the record, for a PAGE and newest first', async () => {
    const client = clientAnswering(ROWS, 41);
    const ctl = createApprovalsController(client as never, () => {});

    await ctl.load();

    expect(APPROVALS_QUERY).toBe('hub.approvals.list');
    expect(client.queryPage).toHaveBeenCalledWith(
      APPROVALS_QUERY,
      expect.objectContaining({ limit: 10, offset: 0, sort: 'created_at', dir: 'desc' }),
    );
  });

  it('hands back the page AND the real total: the pager must know 2 of 41', async () => {
    const ctl = createApprovalsController(clientAnswering(ROWS, 41) as never, () => {});

    await ctl.load();

    expect(ctl.rows.map((r) => r.id)).toEqual(['a2', 'a1']);
    expect(ctl.total).toBe(41);
  });

  it('carries the double attribution: who asked AND who approved, ids included', async () => {
    const ctl = createApprovalsController(clientAnswering(ROWS) as never, () => {});

    await ctl.load();
    const first = ctl.rows[0];

    expect(first.createdByName).toBe('Marta');
    expect(first.approvedByName).toBe('Sofía');
    // The ids travel too: two people can share a name, and the CSV of an audit needs the id.
    expect(first.createdBy).toBe('u-cashier');
    expect(first.approvedBy).toBe('u-manager');
    expect(first.command).toBe('sales.void_line');
    expect(first.permission).toBe('sales.void');
    expect(first.payloadFingerprint).toBe('ff01');
    expect(first.createdAt).toBe('2026-08-11T20:15:00Z');
  });

  it('a date range travels as the query’s range filter on `created_at`', async () => {
    const client = clientAnswering(ROWS);
    const ctl = createApprovalsController(client as never, () => {});

    ctl.setFilter('created_at', { from: '2026-08-01', to: '2026-08-11T23:59:59' });
    await vi.waitFor(() => expect(client.queryPage).toHaveBeenCalled());

    expect(client.queryPage).toHaveBeenCalledWith(
      APPROVALS_QUERY,
      expect.objectContaining({
        filters: { created_at: { from: '2026-08-01', to: '2026-08-11T23:59:59' } },
      }),
    );
  });
});

describe('approvals · what must never be lost', () => {
  it('a receipt whose person was DELETED still has a row', () => {
    // The LEFT JOIN leaves the name empty rather than dropping the row (identity has no
    // soft-delete). Dropping it here would undo that on the only screen that reads the record.
    const rows = parseApprovals([{ ...ROWS[0], approved_by_name: '', created_by_name: '' }]);

    expect(rows).toHaveLength(1);
    expect(rows[0].approvedBy).toBe('u-manager');
    expect(rows[0].approvedByName).toBe('');
  });

  it('a broken answer is not an empty record', () => {
    // Neither of these is «nobody ever approved anything», and a screen that shows them as such
    // hides exactly what somebody came looking for.
    expect(parseApprovals({ ok: false, error: 'nope' })).toEqual([]);
    expect(parseApprovals(null)).toEqual([]);
    expect(parseApprovals('boom')).toEqual([]);
  });

  it('a row that is not a row is dropped, and the rest of the record survives it', () => {
    const rows = parseApprovals([ROWS[0], 'junk', null, ROWS[1]]);

    expect(rows.map((r) => r.id)).toEqual(['a2', 'a1']);
  });

  it('a failed page lands in `error`: «could not load» is not «nothing to show»', async () => {
    const client = { queryPage: vi.fn().mockRejectedValue(new Error('Failed to fetch')) };
    const ctl = createApprovalsController(client as never, () => {});

    await ctl.load();

    expect(ctl.error).toBe('Failed to fetch');
    expect(ctl.rows).toEqual([]);
  });

  it('a field the runtime did not send reads as empty, never as «undefined» on screen', () => {
    const [row] = parseApprovals([{ id: 'a3' }]);

    expect(row).toEqual({
      id: 'a3',
      command: '',
      permission: '',
      createdBy: '',
      createdByName: '',
      approvedBy: '',
      approvedByName: '',
      payloadFingerprint: '',
      createdAt: '',
    });
  });
});
