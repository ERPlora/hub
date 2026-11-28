// The rules of the Home the browser applies (the server already ordered, filtered and counted): the heading,
// the fold of «Finish setting up your business», the steps that block invoicing, the panels this browser keeps on,
// and «My apps» in the order this browser opens them.
import type { SetupItem, SetupStatus, WidgetDef } from '../operations/home';

// ── Heading ─────────────────────────────────────────────────────────────────────────────────────────────────

export type GreetingSlot = 'morning' | 'afternoon' | 'evening';

export type Heading = { kind: 'business'; name: string } | { kind: 'greeting'; slot: GreetingSlot };

export function greetingSlot(hour: number): GreetingSlot {
  if (hour < 12) return 'morning';
  if (hour < 20) return 'afternoon';
  return 'evening';
}

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** The business's name; while it has none (or only an account address), a greeting by the hour. */
export function heading(name: string | null | undefined, hour: number): Heading {
  const trimmed = (name ?? '').trim();
  if (trimmed && !EMAIL.test(trimmed)) return { kind: 'business', name: trimmed };
  return { kind: 'greeting', slot: greetingSlot(hour) };
}

// ── «Finish setting up your business» ─────────────────────────────────────────────────────────────────────

/** Rows the card shows folded on a desk and on a phone. */
export const MAX_VISIBLE_ROWS = 5;
export const PHONE_MAX_VISIBLE_ROWS = 2;

export interface ChecklistOptions {
  expanded?: boolean;
  maxRows?: number;
  /** Keys another card of the same screen already offers («base.apps»: the «My apps» card). */
  alreadyOnScreen?: readonly string[];
}

export interface ChecklistView {
  total: number;
  done: number;
  rows: SetupItem[];
  /** Steps the fold keeps out of sight. */
  hidden: number;
  /** Nothing pending nor unavailable. */
  complete: boolean;
  /** Nothing to show: the card is not painted (an empty answer is silence, never «ready»). */
  empty: boolean;
}

/** The ⛔ before the rest; a stable sort, so each keeps the server's order among its own. */
const legalFirst = (a: SetupItem, b: SetupItem) => Number(b.level === 'legal') - Number(a.level === 'legal');

export function checklistView(status: SetupStatus | undefined, options: ChecklistOptions): ChecklistView {
  const all = status?.items ?? [];
  const duplicated = (item: SetupItem) => item.state !== 'unavailable' && !!options.alreadyOnScreen?.includes(item.key);
  const items = options.expanded ? all : all.filter((item) => !duplicated(item));
  const total = status?.total ?? 0;
  const done = total - (status?.pending ?? 0) - (status?.unavailable ?? 0);
  const empty = !status || items.length === 0;
  const complete = !empty && (status?.pending ?? 0) === 0 && (status?.unavailable ?? 0) === 0;
  let rows: SetupItem[] = [];
  if (options.expanded) rows = items;
  else if (!complete) {
    // ⛔ and 🔴 in sight, 🟡 folded — unless only 🟡 is left (the card would be a headline over nothing). The ⛔ go
    // first: the server orders by each step's `order`, and on a phone a ⛔ placed lower would not fit (hub#801).
    const left = items.filter((item) => item.state !== 'done');
    const upfront = left.filter((item) => item.level !== 'recommended').sort(legalFirst);
    rows = (upfront.length ? upfront : left).slice(0, options.maxRows ?? MAX_VISIBLE_ROWS);
  }
  return { total, done, rows, hidden: items.length - rows.length, complete, empty };
}

/** The ⛔ steps still pending, while the server counts some: what «You cannot issue invoices yet» names. */
export function blockingItems(status: SetupStatus | undefined): SetupItem[] {
  if (!status || status.blocking_pending <= 0) return [];
  return status.items.filter((item) => item.level === 'legal' && item.state === 'pending');
}

// ── Panels ──────────────────────────────────────────────────────────────────────────────────────────────────

/** Where this browser keeps the panels it shows: one board per device. */
export const BOARD_STORAGE_KEY = 'dashboard-hub';

/** The panels on: the stored choice (in its order, without the ones whose app is gone), else the defaults. */
export function activeWidgetKeys(stored: readonly string[] | null, catalogue: readonly WidgetDef[]): string[] {
  const known = new Set(catalogue.map((widget) => widget.key));
  if (stored === null) return catalogue.filter((widget) => widget.default).map((widget) => widget.key);
  return stored.filter((key) => known.has(key));
}

// ── «My apps» ───────────────────────────────────────────────────────────────────────────────────────────────

/** Where this browser counts how often each app is opened (only to order «My apps»). */
export const USAGE_STORAGE_KEY = 'hub-app-usage';

type Store = Pick<Storage, 'getItem' | 'setItem'>;

export function readUsage(storage: Pick<Storage, 'getItem'>): Record<string, number> {
  try {
    const parsed: unknown = JSON.parse(storage.getItem(USAGE_STORAGE_KEY) ?? '{}');
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? (parsed as Record<string, number>) : {};
  } catch {
    return {};
  }
}

/** Counts one opening of `app`; a store that cannot be read starts over. */
export function recordUse(app: string, storage: Store): Record<string, number> {
  const usage = readUsage(storage);
  const next = { ...usage, [app]: (Number(usage[app]) || 0) + 1 };
  storage.setItem(USAGE_STORAGE_KEY, JSON.stringify(next));
  return next;
}

/** The most opened first; equal counts keep the session's order (a stable sort). */
export function orderByUse<T extends { id: string }>(apps: readonly T[], usage: Record<string, number>): T[] {
  return [...apps].sort((a, b) => (Number(usage[b.id]) || 0) - (Number(usage[a.id]) || 0));
}

// ── Activity ────────────────────────────────────────────────────────────────────────────────────────────────

export type SaleTone = 'success' | 'danger' | 'warning' | 'neutral';

const SALE_STATUSES: Record<string, SaleTone> = { completed: 'success', voided: 'danger', refunded: 'warning' };

/** A sale's status as the sales history says it; one this screen does not know is «Other». */
export function saleStatus(status: string): { key: string; tone: SaleTone } {
  const tone = SALE_STATUSES[status];
  return tone ? { key: status, tone } : { key: 'other', tone: 'neutral' };
}
