// **The link that turns the print queue on** (hub#749, ADR-0196 §6).
//
// The queue (hub#341), the host registry (hub#342) and the drain channel (hub#343) were built
// end to end, and the whole thing was **unreachable from the product**: `POST /api/print/hosts` had
// no caller anywhere — not the shell, not the installed app, not a module. Without that
// registration the hub answers every drain with `print.host_not_registered`, and the drain treats
// that as a fact of configuration rather than weather: it stops. So everything `sdk.print` queued
// stayed queued for ever and nobody found out.
//
// ## Why it registers itself instead of asking
//
// hub#342 imagined a screen — "this device prints: receipts / kitchen / bar" — and that screen was
// never built. But the gesture it would collect is one this device can already answer on its own:
// **which printer roles it can actually reach**. The hub's own drain guard says the same thing from
// the other side (`bootPrintHost` refuses to drain where `peripherals.detect()` is offline), so a
// button would be asking the owner to confirm a fact the app already knows. What a screen is still
// needed for is the OTHER direction — showing the owner that nobody is printing the kitchen's
// tickets — and that is coverage (`GET /api/print/hosts`), not registration.
//
// ## The rule that keeps it honest
//
// **A device registers for the roles it can print, and only those.** A phone registered for
// `kitchen` would claim ticket after ticket and fail every one, burning the job's five hand-outs
// and dead-lettering work a real till was about to print. The hub cannot catch that: as far as it
// knows, that device is a legitimate host. So the list comes from the hardware, every tick, and a
// device with no printer registers nothing at all.

/** Seams: no fetch, no timers and no hardware in here, so the contract is testable. */
export interface PrintHostRegistrationOptions {
  /**
   * The printer roles this device can actually print right now, read from the hardware registry.
   * Read **every tick**, never cached: printers get plugged in and re-roled while the app stays
   * open, and the owner who assigns a role in Settings must not have to restart the app for it.
   */
  rolesOnThisDevice(): Promise<string[]>;
  /** `POST /api/print/hosts` for one role. Resolves with the cadence the hub dictates. */
  register(role: string): Promise<{ heartbeatSeconds: number }>;
  /** `POST /api/print/hosts/heartbeat` — "still here", for every role of this device at once. */
  heartbeat(): Promise<{ refreshed: number; heartbeatSeconds: number }>;
  /** The hub session, read lazily. The boot can happen on the login screen. */
  session(): string | null;
  /**
   * Called the first time this device holds at least one role. It is what starts the drain: the
   * drain does not retry a configuration refusal, so connecting before the registration would cost
   * its single attempt and stop it for good.
   */
  onRegistered?(): void;
  /** Anything a human would want to know (an alta the hub refused). */
  onDiagnostic?(event: { kind: 'register_failed' | 'heartbeat_failed'; role?: string; message: string }): void;
  /** Timer seams, so the tests do not wait in real seconds. */
  setTimer?(fn: () => void, ms: number): unknown;
  clearTimer?(handle: unknown): void;
}

export interface PrintHostRegistration {
  /** One pass: register what is new, then say "still here". Public so the tests drive it by hand. */
  tick(): Promise<void>;
  /** The cadence, **as the hub dictates it**. */
  heartbeatSeconds(): number;
  /** Starts ticking on the hub's cadence. Idempotent. */
  start(): void;
  stop(): void;
}

/**
 * Fallback cadence, used only until the hub has answered once. The hub publishes its own
 * (`heartbeatSeconds`) precisely so the client cannot drift away from the window it uses to decide
 * who is alive, so this number is a bootstrap value and never the authority.
 */
const DEFAULT_HEARTBEAT_SECONDS = 30;

export function createPrintHostRegistration(
  options: PrintHostRegistrationOptions,
): PrintHostRegistration {
  const setTimer = options.setTimer ?? ((fn: () => void, ms: number) => setInterval(fn, ms));
  const clearTimer = options.clearTimer ?? ((h: unknown) => clearInterval(h as never));
  /** Roles the hub has confirmed for this device. Empty again whenever the hub forgets us. */
  const held = new Set<string>();
  let cadence = DEFAULT_HEARTBEAT_SECONDS;
  let announced = false;
  let timer: unknown = null;
  /**
   * One pass at a time. Two overlapping passes both read `held` before either had written to it and
   * registered the same role twice; and in production a slow network would let the interval stack
   * passes on top of each other for ever. Skipping is right: the next tick is `cadence` away.
   */
  let inFlight = false;

  async function tick(): Promise<void> {
    if (inFlight) return;
    inFlight = true;
    try {
      await pass();
    } finally {
      inFlight = false;
    }
  }

  async function pass(): Promise<void> {
    // No session yet (the shell booted on the login screen): there is nothing to present, and
    // hammering the hub with a 401 every cadence registers nobody while hiding the real problem.
    if (!options.session()) return;

    const roles = await options.rolesOnThisDevice().catch(() => [] as string[]);
    // No printer on this device → not a print host, and saying otherwise would be a lie the hub
    // has no way to check.
    if (roles.length === 0) return;

    for (const role of roles) {
      if (held.has(role)) continue;
      try {
        const { heartbeatSeconds } = await options.register(role);
        held.add(role);
        if (heartbeatSeconds > 0) cadence = heartbeatSeconds;
      } catch (e) {
        // Not held: the next tick tries again. Recording it as held would leave this device
        // believing it drains a role the hub never gave it.
        options.onDiagnostic?.({
          kind: 'register_failed',
          role,
          message: e instanceof Error ? e.message : String(e),
        });
      }
    }

    if (held.size === 0) return;
    if (!announced) {
      announced = true;
      options.onRegistered?.();
    }

    try {
      const { refreshed, heartbeatSeconds } = await options.heartbeat();
      if (heartbeatSeconds > 0) cadence = heartbeatSeconds;
      // `refreshed: 0` is a success with a meaning: this device hosts nothing here any more (its
      // rows went with a reset or a retirement). Beating against nothing for ever would leave the
      // queue with nobody to drain it, so we forget what we thought we held and register again.
      if (refreshed === 0) held.clear();
    } catch (e) {
      options.onDiagnostic?.({
        kind: 'heartbeat_failed',
        message: e instanceof Error ? e.message : String(e),
      });
    }
  }

  return {
    tick,
    heartbeatSeconds: () => cadence,
    start() {
      if (timer !== null) return;
      void tick();
      timer = setTimer(() => void tick(), cadence * 1000);
    },
    stop() {
      if (timer !== null) clearTimer(timer);
      timer = null;
    },
  };
}
