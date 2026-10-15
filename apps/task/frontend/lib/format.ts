// How the task screens paint days, moments, tones and tags (pages never format by hand), always with
// the page language's own format (Intl). A due date is a PURE day (`YYYY-MM-DD`): it is painted anchored
// to UTC, so it never moves a day across time zones (tasks#23). «Today» is the business's day: phase 1
// has one time zone, Europe/Madrid (the Hub's TIME_ZONE; WORKBOOK «Antes de empezar»).
import type { StatusPillTone } from '@erplora/ui/components';

import type { TaskPriority, TaskStatus } from '../operations';

export const BUSINESS_TIME_ZONE = 'Europe/Madrid';

const days = new Map<string, Intl.DateTimeFormat>();

function dayFormat(locale: string, options: Intl.DateTimeFormatOptions): Intl.DateTimeFormat {
  const key = `${locale}|${JSON.stringify(options)}`;
  let found = days.get(key);
  if (!found) {
    found = new Intl.DateTimeFormat(locale, options);
    days.set(key, found);
  }
  return found;
}

/** The date locale of the page language: English reads day first, as the old screens (`en-GB`). */
function dateLocale(locale: string): string {
  return locale.startsWith('en') ? 'en-GB' : 'es-ES';
}

/** Today in the business's time zone, `YYYY-MM-DD`. */
export function businessToday(now: Date = new Date()): string {
  return dayFormat('en-CA', { timeZone: BUSINESS_TIME_ZONE, year: 'numeric', month: '2-digit', day: '2-digit' }).format(now);
}

export function isClosed(status: TaskStatus): boolean {
  return status === 'done' || status === 'cancelled';
}

/** `overdue` | `today` | `none`. A closed task is never late: there is nothing left to do with it. */
export function dueTone(due: string | null | undefined, status: TaskStatus, now: Date = new Date()): 'overdue' | 'today' | 'none' {
  const day = /^(\d{4}-\d{2}-\d{2})/.exec(due ?? '')?.[1];
  if (!day || isClosed(status)) return 'none';
  const today = businessToday(now);
  if (day < today) return 'overdue';
  return day === today ? 'today' : 'none';
}

/** A pure day as `01/09/2026`, the same day in every time zone; `—` without one. */
export function formatDay(day: string | null | undefined, locale: string): string {
  const ymd = /^(\d{4})-(\d{2})-(\d{2})/.exec(day ?? '');
  if (!ymd) return '—';
  const utc = new Date(Date.UTC(Number(ymd[1]), Number(ymd[2]) - 1, Number(ymd[3])));
  return dayFormat(dateLocale(locale), { day: '2-digit', month: '2-digit', year: 'numeric', timeZone: 'UTC' }).format(utc);
}

/** A moment as `15/10/2026, 01:30` in the business's time zone; `—` without one. */
export function formatMoment(value: string | null | undefined, locale: string): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return dayFormat(dateLocale(locale), {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
    timeZone: BUSINESS_TIME_ZONE,
  }).format(date);
}

/** The colour of each status chip (the old badges: in progress blue, blocked amber, done green, cancelled red). */
export const STATUS_TONE: Readonly<Record<TaskStatus, StatusPillTone>> = Object.freeze({
  todo: 'neutral',
  in_progress: 'info',
  blocked: 'warning',
  done: 'success',
  cancelled: 'danger',
});

/** The standard escalation of priority (tasks#29): urgent is red and low steps back. */
export const PRIORITY_TONE: Readonly<Record<TaskPriority, StatusPillTone>> = Object.freeze({
  low: 'neutral',
  medium: 'info',
  high: 'warning',
  urgent: 'danger',
});

/** Tags typed as `stock, urgent`: trimmed, empty ones dropped, each once. */
export function parseTags(text: string): string[] {
  return [...new Set(text.split(',').map((tag) => tag.trim()).filter(Boolean))];
}

export function tagsText(tags: readonly string[]): string {
  return tags.join(', ');
}
