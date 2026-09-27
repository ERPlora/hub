// **What the floor is told when a kitchen order's docket does not come out** (hub#2238).
//
// `print-comanda.ts` decides WHAT happened to the paper; this decides how it is said, with the same
// pattern as the receipt's (`print-on-sale-notice.ts`, hub#2210) and for the same reason: the boot
// cannot be mounted in a test, and the tone is exactly what went wrong.
//
// - Waiting for a printer (hub#1731): the docket is safe in the queue and comes out on its own once
//   that station's printer is set up — but until then nobody in the kitchen picks it up, so the dish
//   is not started. Not a fault, yet someone has to act: warning, long enough to read.
// - Lost on the way: the docket did not come out — error (reprint from the KDS).
import type { ComandaPrintFailure } from './print-comanda';
import { ERROR_MS, READ_A_SENTENCE_MS, type PrintNotice } from './print-on-sale-notice';

/**
 * `defaultLabel` names a docket with no label of its own (takeaway, no table plan) — the caller
 * owns i18n (ADR-0055), so it comes already translated.
 */
export function comandaFailureNotice(f: ComandaPrintFailure, defaultLabel: string): PrintNotice {
  const label = f.label || defaultLabel;
  if (f.awaitingHost) {
    return {
      messageKey: 'print.comandaWaitingForPrinter',
      params: { label, role: f.role },
      color: 'warning',
      duration: READ_A_SENTENCE_MS,
    };
  }
  return {
    messageKey: 'print.comandaFailed',
    params: { label, role: f.role, error: f.error },
    color: 'danger',
    duration: ERROR_MS,
  };
}
