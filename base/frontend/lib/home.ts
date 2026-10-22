// The rules of the Home the browser applies (the server already ordered, filtered and counted): the heading,
// the fold of «Finish setting up your business», the blocking strip's steps, a panel's data → what it paints,
// the panels this browser keeps on, and «My apps» in the order this browser opens them. Ported from the old
// hub's `dashboard-heading.ts`, `setup-status.ts` and `dashboard-widgets.ts`.
import type { SetupItem, SetupStatus, WidgetDef } from '../operations';

// ── Heading (BASE-G127) ─────────────────────────────────────────────────────────────────────────────────────

export type GreetingSlot = 'morning' | 'afternoon' | 'evening';

export type Heading = { kind: 'business'; name: string } | { kind: 'greeting'; slot: GreetingSlot };

export function greetingSlot(hour: number): GreetingSlot {
  if (hour < 12) return 'morning';
  if (hour < 20) return 'afternoon';
  return 'evening';
}

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** The business's name; while it has none (or only an account address), a greeting by the hour (hub#366). */
export function heading(name: string | null | undefined, hour: number): Heading {
  const trimmed = (name ?? '').trim();
  if (trimmed && !EMAIL.test(trimmed)) return { kind: 'business', name: trimmed };
  return { kind: 'greeting', slot: greetingSlot(hour) };
}

/** A `<script type="application/json">` block Django embedded (`base/spa.py`); none when missing or broken. */
export function readJsonBlock<T>(id: string, doc: Document = document): T | undefined {
  const text = doc.getElementById(id)?.textContent;
  if (!text) return undefined;
  try {
    return JSON.parse(text) as T;
  } catch {
    return undefined;
  }
}

/** What `base/spa.py` embeds as `hub-home`. */
export interface HubHome {
  name: string;
  plan_url: string;
}

// ── «Finish setting up your business» (BASE-G22, BASE-G130, BASE-G164) ────────────────────────────────────

/** Rows the card shows folded on a desk and on a phone (hub#1197). */
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
    // ⛔ and 🔴 in sight, 🟡 folded — unless only 🟡 is left (the card would be a headline over nothing).
    const left = items.filter((item) => item.state !== 'done');
    const upfront = left.filter((item) => item.level !== 'recommended');
    rows = (upfront.length ? upfront : left).slice(0, options.maxRows ?? MAX_VISIBLE_ROWS);
  }
  return { total, done, rows, hidden: items.length - rows.length, complete, empty };
}

/** The ⛔ steps still pending, while the server counts some: what the blocking strip names (hub#374). */
export function blockingItems(status: SetupStatus | undefined): SetupItem[] {
  if (!status || status.blocking_pending <= 0) return [];
  return status.items.filter((item) => item.level === 'legal' && item.state === 'pending');
}

// ── Panels (BASE-G166, BASE-G167) ───────────────────────────────────────────────────────────────────────────

type Row = Record<string, unknown>;

/** The rows of a result: `rows`/`items` of a page, a list, or the object itself (as the server's first row). */
export function rowsOf(result: unknown): Row[] {
  if (Array.isArray(result)) return result as Row[];
  if (result === null || typeof result !== 'object') return [];
  for (const name of ['rows', 'items']) {
    const rows = (result as Row)[name];
    if (Array.isArray(rows)) return rows as Row[];
  }
  return [result as Row];
}

const numberFormats = new Map<string, Intl.NumberFormat>();

function numberFormat(locale: string, format: string): Intl.NumberFormat {
  const id = `${locale}|${format}`;
  let found = numberFormats.get(id);
  if (!found) {
    const options: Intl.NumberFormatOptions =
      format === 'currency'
        ? { style: 'currency', currency: 'EUR' }
        : format === 'percent'
          ? { style: 'percent', maximumFractionDigits: 1 }
          : format === 'compact'
            ? { notation: 'compact' }
            : {};
    found = new Intl.NumberFormat(locale, options);
    numberFormats.set(id, found);
  }
  return found;
}

/** A value of a panel as text: money in cents (the server's), a percentage as 0–100, else the number. */
export function formatValue(value: unknown, format: unknown, locale: string): string {
  const number = typeof value === 'number' ? value : typeof value === 'string' && value.trim() !== '' ? Number(value) : NaN;
  if (Number.isNaN(number)) return String(value);
  if (format === 'currency') return numberFormat(locale, 'currency').format(number / 100);
  if (format === 'percent') return numberFormat(locale, 'percent').format(number / 100);
  return numberFormat(locale, format === 'compact' ? 'compact' : 'number').format(number);
}

export type WidgetView =
  | { kind: 'empty' }
  | { kind: 'kpi'; value: string; label: string | undefined }
  | { kind: 'stat'; value: string; label: string | undefined; severity: string }
  | { kind: 'sparkline'; series: number[]; value: string | undefined }
  | { kind: 'bar-list'; bars: { label: string; value: number; text: string; share: number }[] }
  | { kind: 'timeline'; entries: { title: string; time: string; description: string }[] }
  | { kind: 'chart'; bars: { label: string; value: number; text: string; share: number }[] };

const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
const numeric = (value: unknown): number => (typeof value === 'number' ? value : Number(value));

function bars(widget: WidgetDef, rows: Row[], locale: string, format: unknown) {
  const read = rows
    .map((row) => ({ label: text(row[widget.map.label]), value: numeric(row[widget.map.value]) }))
    .filter((bar) => bar.label !== '' && Number.isFinite(bar.value));
  const max = Math.max(numeric(widget.options.max) || 0, ...read.map((bar) => bar.value), 0);
  return read.map((bar) => ({ ...bar, text: formatValue(bar.value, format, locale), share: max > 0 ? bar.value / max : 0 }));
}

/** What a declarative panel paints from its operation's result; `empty` = «No data», never a made-up 0. */
export function widgetView(widget: WidgetDef, result: unknown, locale: string): WidgetView {
  const rows = rowsOf(result);
  const first = rows[0];
  const format = widget.options.format;
  const label = typeof widget.options.label === 'string' ? widget.options.label : undefined;
  switch (widget.kind) {
    case 'kpi':
    case 'stat': {
      const value = first?.[widget.map.value];
      if (value === undefined || value === null) return { kind: 'empty' };
      const shown = formatValue(value, format, locale);
      if (widget.kind === 'kpi') return { kind: 'kpi', value: shown, label: undefined };
      const severity = text(first?.[widget.map.severity ?? ''] ?? widget.options.severity) || 'normal';
      return { kind: 'stat', value: shown, label: text(first?.[widget.map.label ?? '']) || label, severity };
    }
    case 'sparkline': {
      const series = rows.map((row) => numeric(row[widget.map.series])).filter(Number.isFinite);
      if (series.length === 0) return { kind: 'empty' };
      const last = widget.map.value ? first?.[widget.map.value] : series.at(-1);
      return { kind: 'sparkline', series, value: last === undefined ? undefined : formatValue(last, format, locale) };
    }
    case 'bar-list':
    case 'chart': {
      const read = bars(widget, rows, locale, widget.kind === 'bar-list' ? (widget.options.valueFormat ?? format) : format);
      if (read.length === 0) return { kind: 'empty' };
      return { kind: widget.kind, bars: read };
    }
    case 'timeline': {
      const entries = rows
        .map((row) => ({
          title: text(row[widget.map.title]),
          time: text(row[widget.map.time ?? '']),
          description: text(row[widget.map.description ?? '']),
        }))
        .filter((entry) => entry.title !== '');
      return entries.length ? { kind: 'timeline', entries } : { kind: 'empty' };
    }
    default:
      return { kind: 'empty' };
  }
}

/** Where this browser keeps the panels it shows (the old hub's key: one board per device). */
export const BOARD_STORAGE_KEY = 'dashboard-hub';

/** The panels on: the stored choice (in its order, without the ones whose app is gone), else the defaults. */
export function activeWidgetKeys(stored: readonly string[] | null, catalogue: readonly WidgetDef[]): string[] {
  const known = new Set(catalogue.map((widget) => widget.key));
  if (stored === null) return catalogue.filter((widget) => widget.default).map((widget) => widget.key);
  return stored.filter((key) => known.has(key));
}

// ── «My apps» (BASE-G165) ───────────────────────────────────────────────────────────────────────────────────

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

// ── Activity (BASE-G129) ────────────────────────────────────────────────────────────────────────────────────

export type SaleTone = 'success' | 'danger' | 'warning' | 'neutral';

const SALE_STATUSES: Record<string, SaleTone> = { completed: 'success', voided: 'danger', refunded: 'warning' };

/** A sale's status as the sales history says it; one this screen does not know is «Other». */
export function saleStatus(status: string): { key: string; tone: SaleTone } {
  const tone = SALE_STATUSES[status];
  return tone ? { key: status, tone } : { key: 'other', tone: 'neutral' };
}
