// What the printing screens paint from the server's rows: how long a job has waited, a job's name and
// its detail line, a printer's address and paper, and the tone of each state and status. Texts come from
// the app's catalogues (`t`); dates through the shared formatter.
import { formatDateTime, type StatusPillTone } from '@erplora/ui/components';

import type { JobOut, JobStatus, PrinterOut, PrinterState } from '../operations';

/** A printer whose oldest job has waited longer than this is «Waiting» (the server's minute). */
export const WAITING_AFTER_MS = 60_000;

export type Translate = (key: string, named?: Record<string, unknown>) => string;

/** How long since `from` («25 s», «3 min», «3 h»), rounded down; never negative. */
export function waited(from: string, now: Date, t: Translate): string {
  const seconds = Math.max(0, Math.floor((now.getTime() - new Date(from).getTime()) / 1000));
  if (seconds < 60) return t('printing.units.s', { n: seconds });
  if (seconds < 3600) return t('printing.units.min', { n: Math.floor(seconds / 60) });
  return t('printing.units.h', { n: Math.floor(seconds / 3600) });
}

/** «Receipt T-000123»; without a number, «Receipt · <when it was asked for>». */
export function jobTitle(job: JobOut, t: Translate, locale: string): string {
  const what = job.kind === 'document' ? job.document_type : job.kind;
  const document = t(`printing.documents.${what}`);
  if (job.reference) return t('printing.jobs.named', { document, reference: job.reference });
  return t('printing.jobs.namedAt', { document, when: formatDateTime(job.created_at, locale) });
}

/** What a job allows now, read from the clock: a sent job past its lease is «stale» (no answer). */
export function jobFlags(job: JobOut, now: Date): { stale: boolean; retryable: boolean; cancellable: boolean } {
  const stale = job.status === 'sent' && !!job.leased_until && new Date(job.leased_until).getTime() < now.getTime();
  const open = job.status === 'pending' || job.status === 'failed';
  return { stale, retryable: open || stale, cancellable: open || stale };
}

/** A printer's state by the clock: inactive; failing; waiting (its oldest job, over a minute); ready. */
export function printerState(printer: PrinterOut, now: Date): PrinterState {
  if (!printer.is_active) return 'inactive';
  const failed = printer.last_failed_at ? new Date(printer.last_failed_at).getTime() : null;
  const printed = printer.last_printed_at ? new Date(printer.last_printed_at).getTime() : null;
  if (failed !== null && (printed === null || failed > printed)) return 'failing';
  if (printer.oldest_pending_at && now.getTime() - new Date(printer.oldest_pending_at).getTime() > WAITING_AFTER_MS) return 'waiting';
  return 'ready';
}

/** Why a job is where it is: who cancelled it and why, who sent it again, no answer, its last error. */
export function jobDetail(job: JobOut, t: Translate, now: Date): string {
  const parts: string[] = [];
  if (job.status === 'cancelled') {
    if (job.cancelled_by) parts.push(t('printing.jobs.cancelledBy', { who: job.cancelled_by }));
    if (job.cancel_reason) parts.push(t('printing.jobs.reason', { reason: job.cancel_reason }));
    return parts.join(' · ');
  }
  if (job.retried_by) parts.push(t('printing.jobs.retriedBy', { who: job.retried_by }));
  if (jobFlags(job, now).stale) parts.push(t('printing.jobs.stale'));
  else if (job.last_error) parts.push(t('printing.jobs.lastError', { error: job.last_error }));
  return parts.join(' · ');
}

/** A printer's address as the app reaches it: `ip:port`, the MAC, the queue; none for the system one. */
export function printerAddress(printer: PrinterOut): string {
  if (printer.kind === 'system') return '—';
  if (printer.kind === 'network') return `${printer.address}:${printer.port}`;
  return printer.address;
}

/** Its paper: «80 mm», «58 mm», or A4 for the computer's printer. */
export function printerPaper(printer: PrinterOut, t: Translate): string {
  return printer.kind === 'system' ? t('printing.printers.a4') : t('printing.printers.paper', { n: printer.paper_width });
}

export const STATE_TONE: Readonly<Record<PrinterState, StatusPillTone>> = Object.freeze({
  ready: 'success',
  waiting: 'warning',
  failing: 'danger',
  inactive: 'neutral',
});

export const JOB_TONE: Readonly<Record<JobStatus, StatusPillTone>> = Object.freeze({
  pending: 'warning',
  sent: 'info',
  done: 'success',
  failed: 'danger',
  cancelled: 'neutral',
});
