// The dashboard's activity feed — `sales`' last hundred tickets, newest first.
//
// `sales` is an OPTIONAL module, so the feed only asks for it when the hub's ACTIVE module set says
// it is there (hub#1211, found reviewing hub#1311): `DashboardPage` used to read `sales.list`
// unconditionally on every mount, and every hub without a till — every empty hub, every salon —
// logged a `404 POST /api/query` per dashboard load. Same defect hub#1211 fixes inside the SDK's
// `queryOptional`, one floor up. There is no `queryPageOptional`, and the shell already publishes
// the set the SDK reads (`activeModuleIds()`), so the gate lives here, in front of the read.
import type { ErploraClient } from '@erplora/module-sdk';

import { formatMoney, type FormatMoneyOptions } from './money';

/** The states a sale can be in (`sales`' `status` column: draft|pending|completed|voided|refunded),
 *  plus `other` for one this shell does not know yet — painted as its own neutral word, never
 *  borrowed from a known state (hub#2505). */
export type ActivityStatus = 'completed' | 'pending' | 'draft' | 'voided' | 'refunded' | 'other';

/** One row of the feed. `status` is a stable machine value; the view translates it (hub#863). */
export interface ActivityRow {
  date: string;
  sale: string;
  customer: string;
  method: string;
  /** The sale total in MINOR units (cents), exactly as `sales` stores and serves it (hub#2505). */
  amount: number;
  status: ActivityStatus;
  tone: 'success' | 'medium' | 'danger' | 'warning';
}

/** The i18n key of each state's badge. The words match the ones the sales history uses. */
export const ACTIVITY_STATUS_KEY: Record<ActivityStatus, string> = {
  completed: 'dashboard.activityStatusCompleted',
  pending: 'dashboard.activityStatusPending',
  draft: 'dashboard.activityStatusDraft',
  voided: 'dashboard.activityStatusVoided',
  refunded: 'dashboard.activityStatusRefunded',
  other: 'dashboard.activityStatusOther',
};

const STATUS_TONE: Record<ActivityStatus, ActivityRow['tone']> = {
  completed: 'success',
  pending: 'medium',
  draft: 'medium',
  voided: 'danger',
  refunded: 'warning',
  other: 'medium',
};

function activityStatus(raw: unknown): ActivityStatus {
  return typeof raw === 'string' && raw !== 'other' && Object.hasOwn(STATUS_TONE, raw)
    ? (raw as ActivityStatus)
    : 'other';
}

/**
 * The «Amount» cell. `amount` is in cents, so it goes through `formatMoney` — the formatter every
 * other screen that paints a sale uses. `formatAmount` (for amounts already in euros) painted a
 * 12,50 € ticket as «1.250,00 €» (hub#2505).
 */
export function formatActivityAmount(row: Pick<ActivityRow, 'amount'>, opts?: FormatMoneyOptions): string {
  return formatMoney(row.amount, opts);
}

/** The module the feed belongs to — the owner segment of every query it makes. */
export const FEED_MODULE = 'sales';

/**
 * The factory payment methods `sales` seeds (`seed/install.*.sql`, canonical English per ADR-0055)
 * → the key of their word in `sales`' own catalogue (`locales/<lang>.json` → `ui`). The same pair
 * `sales` reads in `payMethodDisplayName` (`ui/lib/pay-icons.ts`, `SEED_NAME_TO_KEY`): the words
 * are NOT duplicated here, only which stored names are the factory ones.
 */
const SEEDED_METHOD_KEY: Readonly<Record<string, string>> = { Cash: 'cash', Card: 'card' };

/**
 * The «Method» cell, named the way the Sales history names it (hub#2590): a factory method is
 * translated from `sales`' catalogue in the language on screen; a method the owner created or
 * renamed («BBVA TPV») keeps the name they typed. Without the catalogue (not read yet, or failed),
 * the stored name — never a blank or a key.
 */
export function activityMethodName(name: string, salesUi: Readonly<Record<string, unknown>> | undefined): string {
  const key = SEEDED_METHOD_KEY[name.trim()];
  const word = key ? salesUi?.[key] : undefined;
  return typeof word === 'string' && word.trim() ? word : name;
}

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
  return page.rows.map((r) => {
    const status = activityStatus(r.status);
    return {
      date: String(r.created_at ?? ''),
      sale: String(r.sale_number ?? `#${r.id}`),
      customer: String(r.customer_name ?? '—'),
      method: String(r.payment_method_name ?? '—'),
      amount: Number(r.total) || 0,
      status,
      tone: STATUS_TONE[status],
    };
  });
}
