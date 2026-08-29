// The dashboard's activity feed — `sales`' last hundred tickets, newest first.
//
// `sales` is an OPTIONAL module, so the feed only asks for it when the hub's ACTIVE module set says
// it is there (hub#1211, found reviewing hub#1311): `DashboardPage` used to read `sales.list`
// unconditionally on every mount, and every hub without a till — every empty hub, every salon —
// logged a `404 POST /api/query` per dashboard load. Same defect hub#1211 fixes inside the SDK's
// `queryOptional`, one floor up. There is no `queryPageOptional`, and the shell already publishes
// the set the SDK reads (`activeModuleIds()`), so the gate lives here, in front of the read.
import type { ErploraClient } from '@erplora/module-sdk';

/** One row of the feed. `status` is a stable machine value; the view translates it (hub#863). */
export interface ActivityRow {
  date: string;
  sale: string;
  customer: string;
  method: string;
  amount: number;
  status: 'completed' | 'pending';
  tone: 'success' | 'medium';
}

/** The module the feed belongs to — the owner segment of every query it makes. */
const FEED_MODULE = 'sales';

/**
 * Reads the feed, or answers `[]` WITHOUT a request when `active` proves `sales` is absent.
 *
 * `active === undefined` means the set is not known yet (the shell's first `GET /api/modules` has
 * not resolved, or failed): that is not evidence of absence, so the read travels exactly as it did
 * before the gate existed — guessing "absent" there would silently blank the feed of a hub that
 * does have a till. Errors from the read propagate: the caller owns the degradation.
 */
export async function loadRecentSales(
  client: Pick<ErploraClient, 'queryPage'>,
  active: ReadonlySet<string> | undefined,
): Promise<ActivityRow[]> {
  if (active && !active.has(FEED_MODULE)) return [];
  const page = await client.queryPage<Record<string, unknown>>(`${FEED_MODULE}.list`, {
    limit: 100,
    sort: 'created_at',
    dir: 'desc',
  });
  return page.rows.map((r) => ({
    date: String(r.created_at ?? ''),
    sale: String(r.sale_number ?? `#${r.id}`),
    customer: String(r.customer_name ?? '—'),
    method: String(r.payment_method_name ?? '—'),
    amount: Number(r.total) || 0,
    status: r.status === 'completed' ? 'completed' : 'pending',
    tone: r.status === 'completed' ? 'success' : 'medium',
  }));
}
