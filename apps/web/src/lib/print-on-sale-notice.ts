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
// - Out before its VeriFactu QR (hub#1867): the paper is in the customer's hand — warning.
//
// No sentence names the sale: these notices only reach the till that charged it (hub#1980), right
// after the charge, and its internal id (a uuid) told the cashier nothing about which sale it was.
// `saleId` is not passed as a parameter at all, so no catalogue sentence can put it back.
import type { SaleTicketFailure } from './print-on-sale';
import type { ToastColor } from './toast';

/** A notice for the till: a catalogue key with its parameters, the tone and how long it stays up. */
export interface PrintNotice {
  messageKey: string;
  params?: Record<string, unknown>;
  color: ToastColor;
  /** In ms — a sentence that tells the cashier what to do needs longer than a confirmation. */
  duration: number;
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
  return { messageKey: 'print.ticketFailed', params: { error: f.error }, color: 'danger', duration: ERROR_MS };
}

/** hub#1867 — the receipt came out, but before its fiscal number or VeriFactu QR were ready. */
export function saleTicketWithoutFiscalNotice(): PrintNotice {
  return { messageKey: 'print.ticketWithoutFiscal', color: 'warning', duration: READ_A_SENTENCE_MS };
}
