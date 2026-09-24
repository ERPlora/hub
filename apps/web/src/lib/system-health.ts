// What the hub says about itself, in the words of the person who owns the bar (hub#375).
//
// Until this file, the panel's health badge read **«System disconnected»** on a hub that was
// working perfectly. The only thing behind it was `GET localhost:12321/status` — the Bridge probe —
// and in a browser that port is *supposed* to be silent, so the badge was permanently alarming, it
// was actually about the printer host, and it was wrong on all three counts at once. **A status
// that lies is worse than no status at all**: an owner who believes the wrong sentence spends the
// morning on a problem that does not exist, and stops reading the real ones.
//
// The rules this module encodes, and why each one is a rule and not a preference:
//
// * **Name the thing, not «the system».** The hub is up — the person is reading its screen. A probe
//   that only ever knew about the printer host cannot be promoted into a verdict about everything.
// * **Say nothing about a printer nobody has.** The sentence only exists when a printing module is
//   installed *and* running. A hairdresser who never prints does not need a badge about a printer,
//   and a badge that is noise on most hubs stops being read on the ones where it matters.
// * **«I could not check» is its own state.** Not green, not the alarm: `unknown`. It is the same
//   distinction the checklist earned with `unavailable` (hub#371) — evaluated, not done, and *not
//   the user's to fix*. So it carries **no** call to action: sending someone to a screen where
//   there may be nothing wrong is the dead end that state exists to avoid.
// * **A number nobody reported is not zero.** `null` fraction drawn as a green 0% gauge is how a
//   memory metric read from the wrong cgroup shipped as «64 MB» and nobody blinked (hub#229). An
//   unread metric says so, in words, where the number would have been.
//
// The strings are i18n **keys**, resolved by whoever paints them (`system.health.*`). The copy is
// the feature here, so it is asserted against the real English and Spanish catalogues in the tests.
//
// The Bridge probe it was born with is GONE (hub#1731), and the swap the paragraph above predicted
// is the one that happened: the sentence now comes from what the RUNTIME reports — per-role print
// coverage — and every state and every silence above still holds unchanged.
//
// Why the probe had to go, and not just be corrected: it asked `GET localhost:12321/status`, i.e.
// «is the print host process up?», and inside the installed app that is unconditionally yes. So on
// a hub where nobody had ever registered a printer the badge read **«Printer ready»** while the
// receipts piled up unread in the queue — the worst version of the rule at the top of this file,
// because it is the green one. «Somebody is draining the receipt station» is a different question
// from «this process is alive», and it is the only one the owner is actually asking.

// Type only: this module stays pure logic (no `fetch` pulled in by importing it) while the shape
// of a coverage row keeps ONE definition — the one `fetchPrintHosts` actually returns.
import type { PrintRoleCoverage } from './print-coverage';

/** What we could learn about one thing the owner cares about. */
export type HealthState =
  /** Checked, and it works. */
  | 'ok'
  /** Checked, and it needs the owner to do something. */
  | 'attention'
  /** We could **not** check it. Never painted as `ok`. */
  | 'unknown';

export const STATE_OK: HealthState = 'ok';
export const STATE_ATTENTION: HealthState = 'attention';
export const STATE_UNKNOWN: HealthState = 'unknown';

/** `ok-status-pill` tones. `danger` is deliberately absent: nothing here stops the till. */
export type HealthTone = 'success' | 'warning' | 'neutral';

/** The module that owns printer setup; without it, nothing in this hub prints by itself. */
export const PRINTING_MODULE_ID = 'printing';
/** Where the owner goes to fix printing — the printing module's own screen (`module.json` `setup.route`). */
export const PRINTING_ROUTE = '/m/printing/printing';

/** What we are allowed to conclude about the receipt printer: somebody is on it, nobody is, or we could not check. */
export type PrinterProbe = 'ready' | 'not_connected' | 'unknown';

/** Something the owner can do about it, right now. */
export interface HealthAction {
  /** i18n key of the button. */
  labelKey: string;
  route: string;
}

/** One sentence the hub is willing to say about itself. */
export interface HealthLine {
  /** What it is about — `printer`. Never `system`: nothing here speaks for the whole hub. */
  key: string;
  state: HealthState;
  tone: HealthTone;
  /** i18n key — the short sentence (pill label, card headline). */
  titleKey: string;
  /** i18n key — what it means for the till, in one sentence. */
  detailKey: string;
  /** `null` when there is nothing for the owner to do, which includes every `unknown`. */
  action: HealthAction | null;
}

/** The minimum we need of an installed module (`InstalledModule` of `runtime.ts` fits). */
export interface InstalledModuleRef {
  id: string;
  status: string;
}

/** A number the runtime either reported or did not. `known: false` is **not** `value: 0`. */
export interface Reading {
  known: boolean;
  value: number | null;
}

/**
 * Does this hub print by itself?
 *
 * `false` also covers *we could not read the list* (`null`) and *installed but switched off*
 * (`inactive`, or `inactive_auto` dragged by a dependency cascade, ADR-0128). All three mean the
 * same thing for the badge — **say nothing** — and staying quiet on a maybe is the only answer that
 * cannot be wrong.
 */
export function isPrintingInstalled(modules: readonly InstalledModuleRef[] | null | undefined): boolean {
  return (modules ?? []).some((m) => m.id === PRINTING_MODULE_ID && m.status === 'active');
}

/** The station the badge speaks for: the receipt roll, which is what a till asks about. */
export const RECEIPT_ROLE = 'receipt';

/**
 * Reads the runtime's print coverage into what we can honestly say about the receipt printer.
 *
 * **No answer is not a "no".** `null`/`undefined` is coverage we could not read (boot, or the call
 * failed) — which is `unknown`, not `not_connected`. Collapsing the two is the exact move that
 * produced a permanently alarming badge (hub#375).
 *
 * **But an EMPTY list is an answer, and it is `not_connected`.** That is the hub#1731 case itself:
 * a hub whose printing module is on and where nobody ever registered a printer reports no rows at
 * all, and reading that as «I could not check» would put the failure back into the neutral state
 * where nobody acts on it. We read it fine; there is nobody there.
 *
 * Only `receipt` counts. A kitchen printer draining kitchen orders says nothing about the roll the
 * ticket comes out of, and letting any live host anywhere turn the badge green is how a
 * half-set-up restaurant would have kept it.
 */
export function probeFromCoverage(
  coverage: readonly PrintRoleCoverage[] | null | undefined,
): PrinterProbe {
  if (!coverage) return 'unknown';
  const receipts = coverage.find((c) => c.role === RECEIPT_ROLE);
  return (receipts?.liveHosts ?? 0) > 0 ? 'ready' : 'not_connected';
}

/**
 * The one sentence about the printer, or `null` when there is nothing to say.
 *
 * `null` — no printing module, or a module list we could not read — is a real answer, and it is the
 * common one: most hubs should show no printer badge at all.
 */
export function printerLine(
  probe: PrinterProbe,
  modules: readonly InstalledModuleRef[] | null | undefined,
): HealthLine | null {
  if (!isPrintingInstalled(modules)) return null;

  if (probe === 'ready') {
    return {
      key: 'printer',
      state: STATE_OK,
      tone: 'success',
      titleKey: 'system.health.printerReady',
      detailKey: 'system.health.printerReadyDetail',
      // Working needs no button. An action offered where nothing is wrong trains people to ignore
      // the ones that appear where something is.
      action: null,
    };
  }

  if (probe === 'not_connected') {
    return {
      key: 'printer',
      state: STATE_ATTENTION,
      tone: 'warning',
      titleKey: 'system.health.printerOffline',
      detailKey: 'system.health.printerOfflineDetail',
      action: { labelKey: 'system.health.printerAction', route: PRINTING_ROUTE },
    };
  }

  return {
    key: 'printer',
    state: STATE_UNKNOWN,
    // Neutral, never `success`: we did not check it, so we do not get to call it fine.
    tone: 'neutral',
    titleKey: 'system.health.printerUnknown',
    detailKey: 'system.health.printerUnknownDetail',
    // Our failed probe is not the owner's homework.
    action: null,
  };
}

/** The module that owns the WhatsApp channel; without it, this hub has no WhatsApp to speak of. */
export const WHATSAPP_MODULE_ID = 'whatsapp_inbox';
/** Where «Connect again» lives — the module's settings screen (hub#1626). */
export const WHATSAPP_ROUTE = '/m/whatsapp_inbox/settings';

/** The minimum we need of a connected number (`WhatsAppNumber` of `whatsapp-connect.ts` fits). */
export interface WhatsAppNumberRef {
  phone_number_id: string;
  needs_reconnect?: boolean;
}

/** Is the WhatsApp module installed and running? Same «say nothing on a maybe» as the printer. */
export function isWhatsAppInstalled(modules: readonly InstalledModuleRef[] | null | undefined): boolean {
  return (modules ?? []).some((m) => m.id === WHATSAPP_MODULE_ID && m.status === 'active');
}

/**
 * The sentence about a WhatsApp channel that stopped on its own (hub#1629), or `null`.
 *
 * Unlike the printer, WhatsApp only ever speaks up to raise its hand. The only verdict anybody
 * gives is `needs_reconnect === true` (saas#1887): the permission expired, Meta revoked it, the
 * owner unlinked the number. Everything else is silence, and on purpose:
 *
 * * `null`/`undefined` numbers — the call failed. «I could not check» is not «it is down».
 * * a number with no `needs_reconnect` — a SaaS from before the field. Not asked is not broken, and
 *   not fine either: a green «WhatsApp connected» on a key nobody sent is the lie of hub#375.
 * * no numbers at all — never connected. That is setup, not an outage, and not this strip's news.
 */
export function whatsappLine(
  numbers: readonly WhatsAppNumberRef[] | null | undefined,
  modules: readonly InstalledModuleRef[] | null | undefined,
): HealthLine | null {
  if (!isWhatsAppInstalled(modules)) return null;
  if (!(numbers ?? []).some((n) => n.needs_reconnect === true)) return null;
  return {
    key: 'whatsapp',
    state: STATE_ATTENTION,
    tone: 'warning',
    titleKey: 'system.health.whatsappDown',
    detailKey: 'system.health.whatsappDownDetail',
    action: { labelKey: 'system.health.whatsappAction', route: WHATSAPP_ROUTE },
  };
}

/**
 * The steps to get a printer answering, in the order the user takes them, for the surface they are
 * standing on (hub#480).
 *
 * Inside the installed app the first two are already done: that app **is** the print host
 * (ADR-0196), so "download it" and "install it" describe something the user finished before they
 * could read the sentence. And the three buttons that offered the installer were `window.open`
 * calls, which open nothing inside a webview — so the step could not even be taken by mistake.
 *
 * A step nobody can take is a dead end with a number in front of it, which is worse than no list.
 */
export function printerSetupStepKeys(inInstalledApp: boolean): string[] {
  const onThisDevice = ['system.stepPair', 'system.stepConfigure'];
  return inInstalledApp
    ? onThisDevice
    : ['system.stepDownload', 'system.stepInstall', ...onThisDevice];
}

/**
 * A usage fraction as whole percent — or the statement that nobody reported it.
 *
 * A missing `fraction` is **not** 0%: the gauge would sit green at zero and read as "measured, and
 * all is well". A negative fraction cannot be true either, so it is not repeated. **Over 100% is
 * kept**, clamped: being over the limit is news the owner needs, not an unreadable metric.
 */
export function usagePercent(metric: { fraction?: number | null } | null | undefined): Reading {
  const fraction = metric?.fraction;
  if (typeof fraction !== 'number' || !Number.isFinite(fraction) || fraction < 0) {
    return { known: false, value: null };
  }
  return { known: true, value: Math.min(100, Math.round(fraction * 100)) };
}

/** A plain count the runtime reported — or the statement that it did not. Zero is a count; absent is not. */
export function reportedCount(value: number | null | undefined): Reading {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) {
    return { known: false, value: null };
  }
  return { known: true, value };
}
