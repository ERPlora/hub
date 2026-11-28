// A panel of the Home: its operation's result → what it paints.
import { formatMoney, type Money } from '@erplora/ui/components';

import type { WidgetDef } from '../operations/home';
import { DAY_MS, type DayStyle, formatDay, formatMoment, isoDay, type MomentOptions } from './home-dates';

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

function formatOptions(format: string): Intl.NumberFormatOptions {
  if (format === 'percent') return { style: 'percent', maximumFractionDigits: 1 };
  if (format === 'compact') return { notation: 'compact' };
  return {};
}

function numberFormat(locale: string, format: string): Intl.NumberFormat {
  const id = `${locale}|${format}`;
  let found = numberFormats.get(id);
  if (!found) {
    found = new Intl.NumberFormat(locale, formatOptions(format));
    numberFormats.set(id, found);
  }
  return found;
}

/** A value of a panel as text: money in the minor unit of its currency (the server's: 1250 is 12.50 €, ¥1,250 has no
 *  cents) in the business's currency (`money`; without it, a dash), a percentage as 0–100, else
 *  the number. */
export function formatValue(value: unknown, format: unknown, locale: string, money?: Money): string {
  const number = typeof value === 'number' ? value : typeof value === 'string' && value.trim() !== '' ? Number(value) : NaN;
  if (Number.isNaN(number)) return String(value);
  // Money as every screen writes it (`formatMoney`: the symbol a till of that country prints, «zł», «€»; until the
  // business is known, a dash).
  if (format === 'currency') return formatMoney(number, locale, money);
  if (format === 'percent') return numberFormat(locale, 'percent').format(number / 100);
  return numberFormat(locale, format === 'compact' ? 'compact' : 'number').format(number);
}

/** A bar of a bar-list: `share` is the size of its value against the biggest size of the list (0–1, either sign);
 *  `negative` marks a value below zero, the only one painted apart (red, as a report marks it); any other bar has none.
 *  `color` is its row's own colour, when the panel maps one (`map.color`) and it is a hex colour: a negative has none,
 *  its red wins. */
export interface Bar {
  label: string;
  value: number | null;
  text: string;
  share: number;
  negative?: true;
  color?: string;
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

/** A colour a row may give its bar: only a hex colour (#rgb, #rrggbb), since a person types it (a role's colour in
 *  Staff) and it goes into the bar's style. */
const HEX_COLOR = /^#(?:[0-9a-f]{3}){1,2}$/i;

/** The bars of a bar-list or a chart: a row without its value stays, as «—» with no share; one whose value is no
 *  number is left out. A bar measures the size of its value against the biggest size, so a shortfall of 0,40 € is a
 *  short bar beside a surplus of 5,50 €, and only a value below zero is marked `negative`. A bar takes its row's colour
 *  when the panel maps one (`map.color`), except a negative: red wins. */
function bars(widget: WidgetDef, rows: Row[], locale: string, format: unknown, money: Money | undefined): Bar[] {
  const colorField = widget.map.color;
  const read = rows
    .map((row) => {
      const value = row[widget.map.value];
      const color = colorField ? row[colorField] : undefined;
      return {
        label: text(row[widget.map.label]),
        value: missing(value) ? null : numeric(value),
        color: typeof color === 'string' && HEX_COLOR.test(color) ? color : undefined,
      };
    })
    .filter((bar) => bar.label !== '' && (bar.value === null || Number.isFinite(bar.value)));
  const max = Math.max(numeric(widget.options.max) || 0, ...read.map((bar) => Math.abs(bar.value ?? 0)), 0);
  return read.map(({ color, ...bar }): Bar => {
    if (bar.value === null) return { ...bar, text: NO_VALUE, share: 0 };
    const shown = { ...bar, text: formatValue(bar.value, format, locale, money), share: max > 0 ? Math.abs(bar.value) / max : 0 };
    if (bar.value < 0) return { ...shown, negative: true };
    return color ? { ...shown, color } : shown;
  });
}

/** A chart's bars, its days named in the person's language: a week by its weekdays, a
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
