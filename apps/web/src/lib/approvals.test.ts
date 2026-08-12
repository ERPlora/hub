// hub#512 — the READ of the PIN approval record (`_elevation_audit`, ADR-0265).
//
// The runtime has written a receipt per spent approval since system migration v26, and until this
// screen the only way to read it was a SQL session against the customer's own database. The query
// (`hub.approvals.list`, `crates/runtime/src/hub_users.rs`) already exists and already resolves both
// ids to names with a LEFT JOIN; what is fixed here is how the shell reads it:
//
//   - the order is the QUERY's (`created_at DESC`). An audit trail that a screen re-sorts on a
//     whim is one where two people looking at the same hub see a different "last approval";
//   - a receipt whose person was deleted STILL has a row. The JOIN leaves the name empty on
//     purpose — losing the row would lose the audit, which is the one thing it may not do;
//   - a broken answer is NOT an empty record. `parseApprovals` returns nothing for a shape it does
//     not know, and the read itself throws, so the panel can say «could not load» instead of
//     «nobody has ever approved anything» — the false negative this issue exists to end.
import { describe, expect, it, vi } from 'vitest';

import { APPROVALS_QUERY, listApprovals, parseApprovals, type Approval } from './approvals';

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

function clientAnswering(rows: unknown): { query: ReturnType<typeof vi.fn> } {
  return { query: vi.fn().mockResolvedValue(rows) };
}

describe('approvals · reading the record', () => {
  it('asks the core query that owns the record', async () => {
    const client = clientAnswering(ROWS);

    await listApprovals(client as never);

    expect(client.query).toHaveBeenCalledWith(APPROVALS_QUERY, {});
    expect(APPROVALS_QUERY).toBe('hub.approvals.list');
  });

  it('carries the double attribution: who asked AND who approved', async () => {
    const [first] = await listApprovals(clientAnswering(ROWS) as never);

    expect(first.createdByName).toBe('Marta');
    expect(first.approvedByName).toBe('Sofía');
    // The ids travel too: two people can share a name, and the CSV of an audit needs the id.
    expect(first.createdBy).toBe('u-cashier');
    expect(first.approvedBy).toBe('u-manager');
  });

  it('says WHAT was approved and at what level, and WHICH one it was', async () => {
    const [first] = await listApprovals(clientAnswering(ROWS) as never);

    expect(first.command).toBe('sales.void_line');
    expect(first.permission).toBe('sales.void');
    // The fingerprint is what tells the €4 ticket from the other €4 ticket (ADR-0265).
    expect(first.payloadFingerprint).toBe('ff01');
    expect(first.createdAt).toBe('2026-08-11T20:15:00Z');
  });

  it('keeps the order the query gave: newest first, never re-sorted here', async () => {
    const rows = await listApprovals(clientAnswering(ROWS) as never);

    expect(rows.map((r: Approval) => r.id)).toEqual(['a2', 'a1']);
  });

  it('passes the filters through, so the same query can answer «what did Sofía approve»', async () => {
    const client = clientAnswering(ROWS);

    await listApprovals(client as never, { approved_by: 'u-manager' });

    expect(client.query).toHaveBeenCalledWith(APPROVALS_QUERY, { approved_by: 'u-manager' });
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

  it('a failed read THROWS: the caller has to tell «could not load» from «nothing to show»', async () => {
    const client = { query: vi.fn().mockRejectedValue(new Error('Failed to fetch')) };

    await expect(listApprovals(client as never)).rejects.toThrow('Failed to fetch');
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
