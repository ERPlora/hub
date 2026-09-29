// hub#2303 — **the bell rang only for whoever was looking at it.**
//
// A WhatsApp customer the automation handed over to a person, or a booking waiting to be confirmed,
// raised a counter on the bell (hub#1678) and nothing else: with the tablet propped on the counter,
// the app in the background or the phone in a pocket, the business found out late and the customer
// kept waiting. Square, Shopify Inbox or Zendesk warn the device when the bot hands a conversation
// to a person; the shell already did it for a kitchen order and for appointments, so this is the
// same notice for any module that declares a counter — without the core knowing what WhatsApp is.
//
// What is pinned: one system notice per counter that goes UP (the trigger lives in
// `bell-counters.ts`), with the module's own label in the app's language and the new total; words
// by key (ADR-0055); never for a module the shell already announces on its own (appointments,
// hub#2168 — else a WhatsApp booking rings twice); and a notice that cannot be shown never escapes.
import { onBellCounterRise, type BellCounterRise } from './bell-counters';

export interface BellNoticeDeps {
  /**
   * Notification of the SYSTEM, the same door as the kitchen order's. `path` is the screen a tap
   * opens (hub#2305).
   */
  notify: (title: string, body: string, path?: string) => Promise<void>;
  /** The caller owns i18n (ADR-0055): this file only picks the key and its params. */
  t: (key: string, params?: Record<string, unknown>) => string;
  /** Modules whose events the shell already turns into their own notice. */
  ownNotice: ReadonlySet<string>;
}

/** The words of the notice: the counter's label with its new total. */
export function bellNoticeFor(rise: BellCounterRise, t: BellNoticeDeps['t']): { title: string; body: string } {
  return {
    title: t('bellNotice.title', { label: rise.label, count: rise.count }),
    body: t('bellNotice.body'),
  };
}

export async function onBellRise(rise: BellCounterRise, deps: BellNoticeDeps): Promise<void> {
  if (deps.ownNotice.has(rise.moduleId)) return;
  const { title, body } = bellNoticeFor(rise, deps.t);
  // Best-effort, like the kitchen order's: the bell already shows it either way. A tap opens the
  // same tab as the bell's row (hub#2305).
  await deps.notify(title, body, rise.path).catch(() => {});
}

/** Starts the notices at shell boot. Returns the function that stops them. */
export function bootBellNotices(
  deps: BellNoticeDeps,
  subscribe: (listener: (rise: BellCounterRise) => void) => () => void = onBellCounterRise,
): () => void {
  return subscribe((rise) => {
    void onBellRise(rise, deps).catch((e) => console.warn('[bell-notice]', e));
  });
}
