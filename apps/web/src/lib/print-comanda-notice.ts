// **What the floor is told when a kitchen order's docket does not come out** (hub#2238).
//
// `print-comanda.ts` decides WHAT happened to the paper; this decides how it is said, with the same
// pattern as the receipt's (`print-on-sale-notice.ts`, hub#2210) and for the same reason: the boot
// cannot be mounted in a test, and the tone is exactly what went wrong.
//
// - Waiting for a printer (hub#1731): the docket is safe in the queue and comes out on its own once
//   that station's printer is set up — but until then nobody in the kitchen picks it up, so the dish
//   is not started. Not a fault, yet someone has to act: warning, long enough to read.
// - Lost on the way: the docket did not come out — error, as long as a sentence with an instruction;
//   it says what to do, never the machine's reason (hub#2257): that one is logged by `print-comanda.ts`.
//
// Both name the station in the app's language (hub#2257), not in the code's word («kitchen»).
import type { ComandaPrintFailure } from './print-comanda';
import { READ_A_SENTENCE_MS, type PrintNotice } from './print-on-sale-notice';

/** The slice of the app's catalogue the notice reads: the words that fill its sentence. */
export interface NoticeWords {
  t: (key: string) => string;
}

// The stations with a word of their own in the catalogue (pinned en + es by the notice's test).
const STATION_KEY: Record<string, string> = {
  kitchen: 'print.stationKitchen',
  bar: 'print.stationBar',
};

/** A station the catalogue does not know is named as it is, never as a broken key. */
function stationName(role: string, words: NoticeWords): string {
  const key = STATION_KEY[role];
  return key ? words.t(key) : role;
}

/**
 * `words` is the app's catalogue (the caller owns the language, ADR-0055): it names the station and
 * a docket with no label of its own (takeaway, no table plan).
 */
export function comandaFailureNotice(f: ComandaPrintFailure, words: NoticeWords): PrintNotice {
  const params = { label: f.label || words.t('print.comandaDefaultLabel'), station: stationName(f.role, words) };
  if (f.awaitingHost) {
    return { messageKey: 'print.comandaWaitingForPrinter', params, color: 'warning', duration: READ_A_SENTENCE_MS };
  }
  // hub#2257: the door's reason (`f.error`) is for the log — it told the floor nothing to act on.
  // Its sentence carries the way out, so it stays up as long as the waiting one, not toastError's.
  return { messageKey: 'print.comandaFailed', params, color: 'danger', duration: READ_A_SENTENCE_MS };
}

/**
 * The VOID slip of a cancelled round did not come out, or is waiting for a printer (kitchen#168).
 * Same tones as the comanda's, other sentences: the card has just left the kitchen screen, so the
 * way out is to tell the station out loud that the dish is no longer to be made.
 */
export function voidFailureNotice(f: ComandaPrintFailure, words: NoticeWords): PrintNotice {
  const params = { label: f.label || words.t('print.comandaDefaultLabel'), station: stationName(f.role, words) };
  // ONE dish voided (hub#2640): «that order is no longer to be made» would stop the whole table.
  if (f.dish) {
    const dishParams = { ...params, dish: f.dish };
    if (f.awaitingHost) {
      return {
        messageKey: 'print.voidDishWaitingForPrinter',
        params: dishParams,
        color: 'warning',
        duration: READ_A_SENTENCE_MS,
      };
    }
    return { messageKey: 'print.voidDishFailed', params: dishParams, color: 'danger', duration: READ_A_SENTENCE_MS };
  }
  if (f.awaitingHost) {
    return { messageKey: 'print.voidWaitingForPrinter', params, color: 'warning', duration: READ_A_SENTENCE_MS };
  }
  return { messageKey: 'print.voidFailed', params, color: 'danger', duration: READ_A_SENTENCE_MS };
}
