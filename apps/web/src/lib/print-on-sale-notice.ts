// **What the till is told about the receipt of the sale it just charged** (hub#2210).
//
// `print-on-sale.ts` decides WHAT happened to the paper; this decides how it is said: which sentence
// of the catalogue (ADR-0055 — the caller owns i18n) and in which tone. It lives here and not in
// `main.ts` because the boot cannot be mounted in a test, and the tone is exactly what went wrong:
// the receipt waiting for a printer was painted in the error red, straight after a correct charge.
//
// - Waiting for a printer is NOT a fault (hub#1731): the job is safe in the queue and comes out on
//   its own once a printer is set up — informative tone, long enough to read the way out.
// - Lost on the way / never composed: the paper did not come out, and the cashier has to act — error.
//   The sentence says what to do (reprint from the receipt screen), never the machine's reason
//   (hub#2239): that one is logged by `print-on-sale.ts`.
// - Out before its VeriFactu QR (hub#1867): the paper is in the customer's hand — warning.
// - The till's own printer did not answer (hub#2494): error that STAYS until the cashier acts, with
//   a «Retry» button that prints the same receipt again (Square, Toast, Lightspeed).
//
// No sentence names the sale: these notices only reach the till that charged it (hub#1980), right
// after the charge, and its internal id (a uuid) told the cashier nothing about which sale it was.
// `saleId` is not passed as a parameter at all, so no catalogue sentence can put it back.
import { i18n } from '../i18n';
import type { SaleTicketFailure } from './print-on-sale';
import { toast, type ToastColor } from './toast';

/** A notice for the till: a catalogue key with its parameters, the tone and how long it stays up. */
export interface PrintNotice {
  messageKey: string;
  params?: Record<string, unknown>;
  color: ToastColor;
  /**
   * In ms — a sentence that tells the cashier what to do needs longer than a confirmation. `0` =
   * stays until closed: a paper with a Retry waits for the person to act (hub#2494).
   */
  duration: number;
  /** Prints that paper again — the notice's «Retry» button (hub#2494). */
  retry?: () => Promise<void>;
}

/** A failure that can be retried waits for the person: it stays up with its Retry (hub#2494). */
export function withRetry(n: PrintNotice, retry: (() => Promise<void>) | undefined): PrintNotice {
  return retry ? { ...n, duration: 0, retry } : n;
}

/** Long enough to read a sentence with an instruction in it (the same as the fiscal warning). */
export const READ_A_SENTENCE_MS = 6000;
/** `toastError`'s duration: the failures keep the time they always had. */
export const ERROR_MS = 4500;

export function saleTicketFailureNotice(f: SaleTicketFailure): PrintNotice {
  if (f.awaitingHost) {
    return { messageKey: 'print.ticketWaitingForPrinter', color: 'primary', duration: READ_A_SENTENCE_MS };
  }
  if (f.notComposed) return { messageKey: 'print.ticketNotComposed', color: 'danger', duration: ERROR_MS };
  // hub#2494: the till's own printer did not answer — what to check, and Retry right here.
  if (f.printerFailed) {
    return withRetry({ messageKey: 'print.ticketPrinterFailed', color: 'danger', duration: ERROR_MS }, f.retry);
  }
  // hub#2239: the door's reason (`f.error`) is for the log — it told the cashier nothing to act on.
  return { messageKey: 'print.ticketFailed', color: 'danger', duration: ERROR_MS };
}

/** hub#1867 — the receipt came out, but before its fiscal number or VeriFactu QR were ready. */
export function saleTicketWithoutFiscalNotice(): PrintNotice {
  return { messageKey: 'print.ticketWithoutFiscal', color: 'warning', duration: READ_A_SENTENCE_MS };
}

/**
 * Paints a print notice on the till: its sentence in the app's language (with its parameters), its
 * tone and its time, and — when the paper can be printed again — a «Retry» button (hub#2494). The
 * one place the shell's boot paints these, so the tone and the button are tested, not re-typed.
 */
export function presentPrintNotice(n: PrintNotice): Promise<void> {
  const t = i18n.global.t as unknown as (key: string, params?: Record<string, unknown>) => string;
  const retry = n.retry;
  const action = retry
    ? {
        text: t('print.retry'),
        handler: () => {
          retry().catch((e) => console.warn('[print] retry failed', e));
        },
      }
    : undefined;
  return toast(t(n.messageKey, n.params ?? {}), n.color, n.duration, undefined, action);
}
