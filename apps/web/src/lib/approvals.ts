// The PIN approval record, read from the ONE query that owns it (hub#512), one PAGE at a time
// (hub#884).
//
// The runtime writes a receipt for every **spent** step-up approval into the system table
// `_elevation_audit` (system migration **v26**, [ADR-0265]): who asked (`created_by`, the cashier),
// who approved (`approved_by`, the manager), what was run, at what level it was raised, the
// fingerprint of the exact payload, and when. That is the double attribution — and until this file
// nothing in the product could read it: the only answer to «who authorised that refund on Tuesday»
// was a SQL session against the customer's own database, which for a hub that lives in Hetzner
// means ERPlora support reading a business's data to answer a question its owner should be able to
// look up themselves.
//
// The reading is deliberately thin, because the query is the authority:
//
//   - **one page crosses the wire, never the trail.** The audit grows forever by design (nothing
//     deletes it), so the query runs through the runtime's list engine and this file reads it with
//     the SDK's `ListController` — the same `{rows,total,limit,offset}` contract every list of the
//     product speaks. Filters (`command`, `permission`, `created_by`, `approved_by` exact;
//     `created_at` range) and the search over names/command are answered BY THE QUERY: filtering
//     in the client only worked while the whole record was in memory, which was the bug (hub#884);
//   - **the order is the query's** (`created_at DESC` by default). Re-sorting here would mean two
//     people looking at the same hub disagree about which approval was the last one;
//   - **the names come resolved.** The query LEFT JOINs `hub_user` twice; a row whose person was
//     deleted arrives with an empty name and it still is a row. Dropping it here would undo, on
//     the only screen that reads the record, the care the SQL took not to lose it;
//   - **a broken answer is not an empty record.** A shape we do not know parses to nothing and a
//     failed page lands in the controller's `error`, so the caller can say «could not load»
//     instead of «nobody ever approved anything» — a silent false negative on an audit trail is
//     worse than no screen at all.
//
// [ADR-0265]: architecture/00-overview/decision-log.md#adr-0265
import {
  createListController,
  type ErploraClient,
  type ListClient,
  type ListController,
  type ListParams,
  type Page,
} from '@erplora/module-sdk';

/** The one query. A core query of the reserved `hub.` namespace (`crates/runtime/src/hub_users.rs`). */
export const APPROVALS_QUERY = 'hub.approvals.list';

/** One receipt: one approval that was spent on one action. */
export interface Approval {
  id: string;
  /** The command that ran with the approval, e.g. `sales.void_line`. */
  command: string;
  /** The permission it was raised to — at what level the action was, not who holds it. */
  permission: string;
  /** The cashier who asked. Their id, which outlives their name. */
  createdBy: string;
  /** Their name, or `''` if the person is no longer in `hub_user`. */
  createdByName: string;
  /** The manager who approved. */
  approvedBy: string;
  /** Their name, or `''` if the person is no longer in `hub_user`. */
  approvedByName: string;
  /**
   * Canonical fingerprint of the payload the approval was bound to: it says WHICH €4 ticket was
   * voided, not merely that «a void» was approved (ADR-0265).
   */
  payloadFingerprint: string;
  /** ISO instant. Kept raw: it is what the date filter and the sort read. */
  createdAt: string;
}

/** The controller a screen holds: one page of parsed receipts + the real total, SDK contract. */
export type ApprovalsController = ListController<Approval>;

/**
 * The list controller over the record: page, sort, search and filters all re-ask the RUNTIME
 * (`hub.approvals.list` runs through the runtime's list engine since hub#884). Ten per page —
 * the table's own default — newest first; the rows come parsed, so a shape the runtime never
 * promised parses to nothing instead of reaching the screen.
 *
 * A failed page lands in the controller's `error` (never thrown): the caller has to be able to
 * tell a hub with no approvals from a hub that could not be asked.
 */
export function createApprovalsController(
  client: ErploraClient,
  onChange: () => void,
): ApprovalsController {
  const parsing: ListClient = {
    async queryPage<R>(name: string, params: ListParams): Promise<Page<R>> {
      const page = await client.queryPage<unknown>(name, params);
      return { ...page, rows: parseApprovals(page.rows) as R[] };
    },
  };
  return createListController<Approval>(parsing, APPROVALS_QUERY, onChange, {
    pageSize: 10,
    sort: 'created_at',
    dir: 'desc',
  });
}

/** Reads the runtime's payload. Anything that is not a list of rows parses to nothing. */
export function parseApprovals(raw: unknown): Approval[] {
  if (!Array.isArray(raw)) return [];
  return raw.filter(isRecord).map(toApproval);
}

function toApproval(raw: Record<string, unknown>): Approval {
  return {
    id: str(raw.id),
    command: str(raw.command),
    permission: str(raw.permission),
    createdBy: str(raw.created_by),
    createdByName: str(raw.created_by_name),
    approvedBy: str(raw.approved_by),
    approvedByName: str(raw.approved_by_name),
    payloadFingerprint: str(raw.payload_fingerprint),
    createdAt: str(raw.created_at),
  };
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

function str(v: unknown): string {
  return typeof v === 'string' ? v : '';
}
