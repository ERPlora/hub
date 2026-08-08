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
// The probe itself is on death row: with ADR-0196 the Bridge stops being a separate process and the
// printer stops being something a browser guesses at over localhost. This module is the shape that
// survives that: swap `probeFromBridge` for whatever the runtime ends up reporting and every
// sentence, every state and every silence above still holds.

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

/** What a probe of the printer host is allowed to conclude. */
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

/**
 * Reads the local probe into what we can honestly say.
 *
 * **No answer is not a "no".** `null`/`undefined` is the probe that has not come back yet (boot) or
 * that we never managed to run — which is `unknown`, not `not_connected`. Collapsing the two is the
 * exact move that produced a permanently alarming badge.
 */
export function probeFromBridge(status: { online: boolean } | null | undefined): PrinterProbe {
  if (!status) return 'unknown';
  return status.online ? 'ready' : 'not_connected';
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
