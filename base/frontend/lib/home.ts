// The rules of the Home the browser applies (the server already ordered, filtered and counted): the heading,
// the fold of «Finish setting up your business», the blocking strip's steps, a panel's data → what it paints,
// the panels this browser keeps on, and «My apps» in the order this browser opens them. Ported from the old
// hub's `dashboard-heading.ts`, `setup-status.ts` and `dashboard-widgets.ts`.
import { formatDateTime } from '@erplora/ui/components';

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
  /** The person's account on erplora.com (the user menu's «My account»). */
  account_url: string;
  /** erplora.com's form to report a problem to support (the user menu's «Report a problem», PLAN-SAAS §1.1). */
  report_url: string;
  /** «Members» of this business on erplora.com, where people are invited, given a role and removed (APP-BASE-5). */
  members_url?: string;
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

/** A business's currency (ISO 4217) and its decimals, as `base.business.get` says them (BASE-G98). */
export interface Money {
  currency: string;
  decimals: number;
}

const numberFormats = new Map<string, Intl.NumberFormat>();

function formatOptions(format: string, money: Money | undefined): Intl.NumberFormatOptions {
  if (format === 'currency') {
    // The symbol a till of that country prints («zł», «€»); until the business is known, the amount alone.
    const digits = { minimumFractionDigits: money?.decimals ?? 2, maximumFractionDigits: money?.decimals ?? 2 };
    return money ? { style: 'currency', currency: money.currency, currencyDisplay: 'narrowSymbol', ...digits } : digits;
  }
  if (format === 'percent') return { style: 'percent', maximumFractionDigits: 1 };
  if (format === 'compact') return { notation: 'compact' };
  return {};
}

function numberFormat(locale: string, format: string, money?: Money): Intl.NumberFormat {
  const id = format === 'currency' ? `${locale}|${format}|${money?.currency ?? ''}|${money?.decimals ?? ''}` : `${locale}|${format}`;
  let found = numberFormats.get(id);
  if (!found) {
    found = new Intl.NumberFormat(locale, formatOptions(format, money));
    numberFormats.set(id, found);
  }
  return found;
}

/** A value of a panel as text: money in cents (the server's) in the business's currency (`money`; without it, the
 *  amount alone), a percentage as 0–100, else the number. */
export function formatValue(value: unknown, format: unknown, locale: string, money?: Money): string {
  const number = typeof value === 'number' ? value : typeof value === 'string' && value.trim() !== '' ? Number(value) : NaN;
  if (Number.isNaN(number)) return String(value);
  if (format === 'currency') return numberFormat(locale, 'currency', money).format(number / 100);
  if (format === 'percent') return numberFormat(locale, 'percent').format(number / 100);
  return numberFormat(locale, format === 'compact' ? 'compact' : 'number').format(number);
}

/** A bar of a bar-list: `share` is the size of its value against the biggest size of the list (0–1, either sign);
 *  `negative` marks a value below zero, the only one painted apart (red, as a report marks it); any other bar has none. */
export interface Bar {
  label: string;
  value: number | null;
  text: string;
  share: number;
  negative?: true;
}

export type WidgetView =
  | { kind: 'empty' }
  | { kind: 'kpi'; value: string; label: string | undefined }
  | { kind: 'stat'; value: string; label: string | undefined; severity: string }
  | { kind: 'sparkline'; series: number[]; value: string | undefined }
  | { kind: 'bar-list'; bars: Bar[] }
  | { kind: 'timeline'; entries: TimelineEntry[] }
  | { kind: 'chart'; bars: ChartBar[] };

/** An entry of a timeline: `time` as the person reads it and, when it is a date, `datetime` = the instant (or day) as
 *  the server sent it and `detail` = it whole in the person's language («23 oct 2026, 4:23», «22 oct 2026»). */
export interface TimelineEntry {
  title: string;
  time: string;
  datetime: string | undefined;
  detail: string | undefined;
  description: string;
}

/** A bar of a chart: `key` is its row's label as the server sent it; `label` goes under the bar and `detail` says
 *  it whole (a day: «vie» and «vie, 23 oct»); `value` is `null` when its row has none (`text` is then «—»). */
export interface ChartBar extends Bar {
  key: string;
  detail: string;
}

const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
const numeric = (value: unknown): number => (typeof value === 'number' ? value : Number(value));
/** A value the row does not have — none, absent or blank (a cash session closed without a count has no difference). */
const missing = (value: unknown): boolean => value === null || value === undefined || (typeof value === 'string' && value.trim() === '');

/** What a panel says for a value a row does not have, as Square, Shopify or Odoo leave an empty cell: never a 0. */
const NO_VALUE = '—';

/** The bars of a bar-list or a chart: a row without its value stays, as «—» with no share (BASE-F06); one whose value is
 *  no number is left out. A bar measures the size of its value against the biggest size, so a shortfall of 0,40 € is
 *  a short bar beside a surplus of 5,50 €, and only a value below zero is marked `negative` (BASE-F06). */
function bars(widget: WidgetDef, rows: Row[], locale: string, format: unknown, money: Money | undefined): Bar[] {
  const read = rows
    .map((row) => {
      const value = row[widget.map.value];
      return { label: text(row[widget.map.label]), value: missing(value) ? null : numeric(value) };
    })
    .filter((bar) => bar.label !== '' && (bar.value === null || Number.isFinite(bar.value)));
  const max = Math.max(numeric(widget.options.max) || 0, ...read.map((bar) => Math.abs(bar.value ?? 0)), 0);
  return read.map((bar): Bar => {
    if (bar.value === null) return { ...bar, text: NO_VALUE, share: 0 };
    const shown = { ...bar, text: formatValue(bar.value, format, locale, money), share: max > 0 ? Math.abs(bar.value) / max : 0 };
    return bar.value < 0 ? { ...shown, negative: true } : shown;
  });
}

const ISO_DAY = /^(\d{4})-(\d{2})-(\d{2})$/;
const DAY_MS = 86_400_000;

/** A civil day `YYYY-MM-DD` (a business day has no zone) as its UTC midnight, always formatted in UTC so it never
 *  moves to the day before or after; an instant or a day the calendar does not have is no day. */
export function isoDay(value: string): Date | undefined {
  const match = ISO_DAY.exec(value);
  if (!match) return undefined;
  const [year, month, day] = match.slice(1).map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  const same = date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day;
  return same ? date : undefined;
}

export type DayStyle = 'weekday' | 'date' | 'full';

const DAY_STYLES: Record<DayStyle, Intl.DateTimeFormatOptions> = {
  weekday: { weekday: 'short' },
  date: { day: 'numeric', month: 'short' },
  full: { weekday: 'short', day: 'numeric', month: 'short' },
};

const dayFormats = new Map<string, Intl.DateTimeFormat>();

/** A day of `isoDay` in the person's language: «vie» / «Fri», «23 oct» / «Oct 23», «vie, 23 oct» / «Fri, Oct 23». */
export function formatDay(day: Date, style: DayStyle, locale: string): string {
  const id = `${locale}|${style}`;
  let found = dayFormats.get(id);
  if (!found) {
    found = new Intl.DateTimeFormat(locale, { ...DAY_STYLES[style], timeZone: 'UTC' });
    dayFormats.set(id, found);
  }
  return found.format(day);
}

/** When a moment is read: «now» and the IANA time zone (the device's when omitted; tests pin both). */
export interface MomentOptions {
  now?: Date;
  timeZone?: string;
}

/** An instant as ISO 8601 sends it: a day, `T`, hours and minutes, optional seconds and fraction, optional offset. */
const ISO_INSTANT = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?$/;

type MomentStyle = 'time' | 'date-time' | 'year-date-time' | 'date' | 'year-date' | 'whole-date' | 'day-key';

const MOMENT_STYLES: Record<MomentStyle, Intl.DateTimeFormatOptions> = {
  time: { timeStyle: 'short' },
  'date-time': { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' },
  'year-date-time': { day: 'numeric', month: 'short', year: 'numeric', hour: 'numeric', minute: '2-digit' },
  date: { day: 'numeric', month: 'short' },
  'year-date': { day: 'numeric', month: 'short', year: 'numeric' },
  'whole-date': { dateStyle: 'medium' },
  'day-key': { year: 'numeric', month: 'numeric', day: 'numeric' },
};

const momentFormats = new Map<string, Intl.DateTimeFormat>();

function momentFormat(locale: string, style: MomentStyle, timeZone: string): Intl.DateTimeFormat {
  const id = `${locale}|${style}|${timeZone}`;
  let found = momentFormats.get(id);
  if (!found) {
    found = new Intl.DateTimeFormat(locale, { ...MOMENT_STYLES[style], timeZone });
    momentFormats.set(id, found);
  }
  return found;
}

/** The civil day an instant falls on in `timeZone`, as that day's UTC midnight (what `isoDay` gives). */
function dayIn(instant: Date, timeZone: string): Date {
  const parts = momentFormat('en', 'day-key', timeZone).formatToParts(instant);
  const part = (type: Intl.DateTimeFormatPartTypes) => Number(parts.find((found) => found.type === type)?.value);
  return new Date(Date.UTC(part('year'), part('month') - 1, part('day')));
}

/** «Today» / «hoy», «Yesterday» / «ayer»: the language's own word, capitalised to open the line. */
function relativeDay(offset: 0 | -1, locale: string): string {
  const word = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' }).format(offset, 'day');
  return word.charAt(0).toLocaleUpperCase(locale) + word.slice(1);
}

/** When something happened, as a day's list says it (Square, Shopify, a phone's call log): the local time alone if it
 *  was today («4:23»), «Ayer 18:10» if yesterday, else the short date and the time («20 oct, 18:10»; the year only
 *  when it is another); `detail` says it whole («23 oct 2026, 4:23»). A civil day `YYYY-MM-DD` says «Hoy», «Ayer» or
 *  its date, in no zone. Not a date: `undefined`. */
export function formatMoment(value: string, locale: string, options: MomentOptions = {}): { text: string; detail: string } | undefined {
  const timeZone = options.timeZone ?? new Intl.DateTimeFormat().resolvedOptions().timeZone;
  const now = options.now ?? new Date();
  const civil = isoDay(value);
  const instant = civil || !ISO_INSTANT.test(value) ? undefined : new Date(value);
  if (instant && Number.isNaN(instant.getTime())) return undefined;
  const day = civil ?? (instant ? dayIn(instant, timeZone) : undefined);
  if (!day) return undefined;
  const today = dayIn(now, timeZone);
  const back = Math.round((today.getTime() - day.getTime()) / DAY_MS);
  const sameYear = day.getUTCFullYear() === today.getUTCFullYear();
  if (!instant) {
    const detail = momentFormat(locale, 'whole-date', 'UTC').format(day);
    if (back === 0 || back === 1) return { text: relativeDay(back === 0 ? 0 : -1, locale), detail };
    return { text: momentFormat(locale, sameYear ? 'date' : 'year-date', 'UTC').format(day), detail };
  }
  const detail = formatDateTime(instant, locale, { timeZone });
  const time = () => momentFormat(locale, 'time', timeZone).format(instant);
  if (back === 0) return { text: time(), detail };
  if (back === 1) return { text: `${relativeDay(-1, locale)} ${time()}`, detail };
  return { text: momentFormat(locale, sameYear ? 'date-time' : 'year-date-time', timeZone).format(instant), detail };
}

/** A chart's bars, its days named in the person's language (the old hub's gh:hub#2392): a week by its weekdays, a
 *  longer series by its dates (its weekdays would repeat); a label that is no day stays as it is. */
function chartBars(widget: WidgetDef, rows: Row[], locale: string, format: unknown, money: Money | undefined): ChartBar[] {
  const read = bars(widget, rows, locale, format, money);
  const days = read.map((bar) => isoDay(bar.label));
  const times = days.filter((day) => day !== undefined).map((day) => day.getTime());
  const style: DayStyle = times.length && Math.max(...times) - Math.min(...times) < 7 * DAY_MS ? 'weekday' : 'date';
  return read.map((bar, index) => {
    const day = days[index];
    return {
      ...bar,
      key: bar.label,
      label: day ? formatDay(day, style, locale) : bar.label,
      detail: day ? formatDay(day, 'full', locale) : bar.label,
    };
  });
}

/** How a panel is read: its timeline's moments (`MomentOptions`) and its amounts' currency, the business's. */
export interface ViewOptions extends MomentOptions {
  money?: Money;
}

/** What a declarative panel paints from its operation's result; `empty` = «No data», never a made-up 0. A timeline's
 *  moments are read at `moment.now` in `moment.timeZone`; an amount, in `moment.money`. */
export function widgetView(widget: WidgetDef, result: unknown, locale: string, moment: ViewOptions = {}): WidgetView {
  const { money } = moment;
  const rows = rowsOf(result);
  const first = rows[0];
  const format = widget.options.format;
  const label = typeof widget.options.label === 'string' ? widget.options.label : undefined;
  switch (widget.kind) {
    case 'kpi':
    case 'stat': {
      const value = first?.[widget.map.value];
      if (value === undefined || value === null) return { kind: 'empty' };
      const shown = formatValue(value, format, locale, money);
      if (widget.kind === 'kpi') return { kind: 'kpi', value: shown, label: undefined };
      const severity = text(first?.[widget.map.severity ?? ''] ?? widget.options.severity) || 'normal';
      return { kind: 'stat', value: shown, label: text(first?.[widget.map.label ?? '']) || label, severity };
    }
    case 'sparkline': {
      // A point without its value is skipped, never drawn as a 0.
      const series = rows
        .map((row) => row[widget.map.series])
        .filter((value) => !missing(value))
        .map(numeric)
        .filter(Number.isFinite);
      if (series.length === 0) return { kind: 'empty' };
      const last = widget.map.value ? first?.[widget.map.value] : series.at(-1);
      return { kind: 'sparkline', series, value: missing(last) ? undefined : formatValue(last, format, locale, money) };
    }
    case 'bar-list': {
      const read = bars(widget, rows, locale, widget.options.valueFormat ?? format, money);
      return read.length ? { kind: 'bar-list', bars: read } : { kind: 'empty' };
    }
    case 'chart': {
      const read = chartBars(widget, rows, locale, format, money);
      return read.length ? { kind: 'chart', bars: read } : { kind: 'empty' };
    }
    case 'timeline': {
      const entries = rows
        .map((row): TimelineEntry => {
          const time = row[widget.map.time ?? ''];
          const said = typeof time === 'string' ? formatMoment(time, locale, moment) : undefined;
          return {
            title: text(row[widget.map.title]),
            time: said?.text ?? text(time),
            datetime: said && (time as string),
            detail: said?.detail,
            description: text(row[widget.map.description ?? '']),
          };
        })
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
