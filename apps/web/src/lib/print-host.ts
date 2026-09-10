// **The link that was missing** (hub#501, ADR-0196 §6): a job drained from the hub's queue becoming
// paper on a real printer.
//
// hub#341/#342/#343 built the queue, the host registry and the channel that hands a job to the
// device that owns the printer — and then stopped, because the two halves spoke different languages:
// the queue stored HTML, and `crates/peripherals` renders **structured** documents
// (`erplora_print(printer_id, document_type, data, job_id)`). There was nothing to wire the drain's
// `printJob` to, so it shipped injected and unconnected. With the queue carrying the document
// structured, this is the wire.
//
// ## Why this is NOT `print.ts`
//
// `erplora.print` (the global door every module uses) falls back to the browser's print dialog when
// there is no printer. That is right for a cashier who just pressed "print" — the ticket still comes
// out, by hand — and **wrong here**. This path runs *unattended*: the kitchen order arrives at a
// tablet propped on a shelf, and a dialog waiting for somebody to click "Print" is a ticket that
// never prints while the hub is told it did. So there is no fallback at all in this file.
//
// Everything that goes wrong is **thrown**, on purpose: `print-drain.ts` turns a rejection into a
// `failed` frame, the hub puts the ticket back for the next host and keeps the reason in
// `_print_queue.last_error`. A swallowed error here would be a lost ticket nobody could see.
import { createPrintDrain, type DrainDiagnostic, type DrainSocket, type DrainJob } from './print-drain';
import { printerIdForRole, type PrintDevice } from './print';
import { createPrintHostRegistration } from './print-host-registration';
import { getHubSession } from './session';
import { resolveDeviceId } from './device';
import { RUNTIME_URL, runtimeHeaders } from './runtime';

/** The minimum of the client this needs. Injected so the tests need no hardware. */
export interface PrintHostClient {
  peripherals: {
    /** Can this environment reach hardware at all? `{ online: false }` in a plain browser. */
    detect(timeoutMs?: number): Promise<{ online: boolean }>;
    getDevices(): Promise<PrintDevice[]>;
    print(
      printerId: string,
      documentType: string,
      data: Record<string, unknown>,
      jobId?: string,
    ): Promise<void>;
    /**
     * Gives a device in the registry a role (by `key` or MAC). Optional here: only the safety net
     * below uses it, and a transport without it (an older test double) still boots.
     */
    setDeviceRole?(keyOrMac: string, role: string): Promise<PrintDevice[]>;
  };
}

/**
 * **The first printer found is the RECEIPT printer** — and without that, nothing prints and nobody
 * says so (hub#862).
 *
 * A freshly discovered printer is born with NO ROLE, and somebody has to give it one by hand in the
 * `printing` module. Until they do, two silences add up: the `receipt` role resolves to no printer
 * (the ticket cannot go out through hardware) AND this device registers as a print host for ZERO
 * roles (nobody drains the queue), so what got queued does not come out either. The symptom is
 * "the printer is online, the switch is on, and nothing happens".
 *
 * Returns the key of the device that should get `receipt`, or `undefined` when nothing should be
 * touched. It acts only on the unambiguous case: **one** reachable printer and **no** role anywhere
 * in the registry. With two there is a routing decision to guess (which one is the label printer?)
 * and with any role already set the install is configured — hands off in both.
 */
export function printerNeedingDefaultRole(devices: PrintDevice[]): string | undefined {
  const list = devices ?? [];
  if (list.some((d) => d?.role?.trim())) return undefined;
  // `ip` is what makes it reachable: an entry with no address cannot take a job.
  const reachable = list.filter((d) => d?.ip);
  if (reachable.length !== 1) return undefined;
  const only = reachable[0]!;
  // `key` is the registry's key; a MAC works too (the registry resolves both), and on Android there
  // is no MAC at all — so the key comes first.
  return only.key ?? only.mac ?? undefined;
}

/**
 * Builds the `printJob` that `createPrintDrain` takes: role → printer → hardware.
 *
 * The role→printer resolution is **the same one** the global print door uses
 * (`printerIdForRole`), so "which box is the kitchen printer" has one definition in the shell and
 * not two that can disagree.
 */
export function createJobPrinter(client: PrintHostClient): (job: DrainJob) => Promise<void> {
  return async function printJob(job: DrainJob): Promise<void> {
    // Read every time, never cached: printers get unplugged, re-addressed and re-roled while the
    // app stays open, and a cached address prints to nowhere.
    const devices = await client.peripherals.getDevices();
    const printerId = printerIdForRole(devices, job.role);
    if (!printerId) {
      // Named with the role because that is the actionable half: the owner has to give some printer
      // that role, on this device or on another one. The hub keeps the ticket meanwhile.
      throw new Error(`no printer on this device holds the "${job.role}" role`);
    }
    // Straight through, untouched: `documentType` picks the renderer and `document` is what it
    // reads. The `jobId` goes with it so the device's own retry queue dedupes the same way the hub
    // does — one job, one piece of paper, however many times it is handed out.
    await client.peripherals.print(printerId, job.documentType, job.document, job.jobId);
  };
}

/** Enough of `window.location` to build the channel URL, so a test can hand one over. */
export interface PageLocation {
  protocol: string;
  host: string;
}

/**
 * Where `GET /ws/print` lives, **on the same origin and the same scheme as the page**.
 *
 * The scheme is not cosmetic: a hub served over https refuses a `ws://` socket as mixed content, so
 * a hard-coded one would work all through local development and then never connect on a single
 * deployed hub.
 */
export function printChannelUrl(loc: PageLocation): string {
  const scheme = loc.protocol === 'https:' ? 'wss' : 'ws';
  return `${scheme}://${loc.host}/ws/print`;
}

/** Seams for the boot, so the test drives it without a socket, a session or a device. */
interface BootOptions {
  url?: string;
  session?: () => string | null;
  deviceId?: () => Promise<string | null>;
  openSocket?: (url: string) => DrainSocket;
  onDiagnostic?: (event: DrainDiagnostic) => void;
  /** `POST /api/print/hosts` (hub#749). Injected so the test needs no fetch. */
  registerHost?: (role: string, deviceId: string) => Promise<{ heartbeatSeconds: number }>;
  /** `POST /api/print/hosts/heartbeat`. */
  heartbeatHost?: (deviceId: string) => Promise<{ refreshed: number; heartbeatSeconds: number }>;
  /**
   * Called ONCE, the first time the hub confirms this device holds a printer role (hub#1732).
   *
   * This is the moment the device becomes the one that gets **told** an order came in, and the
   * moment somebody is standing at the till configuring it — so it is where the shell asks for the
   * notification permission. Waiting for the first order instead means popping a dialog at a
   * tablet propped on a shelf with nobody in front of it: the ask goes unanswered and the notice
   * that prompted it is the one that gets lost.
   *
   * Best-effort and never load-bearing: the drain is already running before this is called.
   */
  onRegistered?: () => void;
  setTimer?: (fn: () => void, ms: number) => unknown;
  clearTimer?: (handle: unknown) => void;
}

/**
 * The printer roles this device can actually print: the roles of the printers **it can reach**,
 * without duplicates. A box with no role assigned yet is not a role — the owner has not said what
 * it prints, and claiming a nameless queue would be inventing the answer.
 */
export function printerRolesOfDevices(devices: PrintDevice[]): string[] {
  const roles = new Set<string>();
  for (const device of devices ?? []) {
    const role = device?.role?.trim();
    // `ip` is what makes it reachable: a registry entry without one cannot take a job.
    if (role && device?.ip) roles.add(role);
  }
  return [...roles];
}

/** `POST` to the runtime with the device identity the print host registry keys on. */
async function postToRuntime(path: string, deviceId: string, body?: unknown): Promise<unknown> {
  const res = await fetch(`${RUNTIME_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...runtimeHeaders(), 'X-Device-Id': deviceId },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  const payload = (await res.json().catch(() => null)) as { ok?: boolean; error?: { message?: string } } | null;
  // A refusal must THROW, never resolve: a swallowed one would leave this device believing it
  // drains a role the hub never gave it, and the queue with nobody taking its paper out.
  if (!res.ok || payload?.ok !== true) {
    throw new Error(payload?.error?.message || `${path} → HTTP ${res.status}`);
  }
  return payload;
}

/** The one drain of this shell. Module-level because a second one would be a second print host. */
let running: { stop(): void } | null = null;

/**
 * Starts draining the hub's print queue on this device (hub#343 + hub#501).
 *
 * **It is safe to call on every boot, on every device.** A device nobody registered as a print host
 * is refused with `print.host_not_registered`, and the drain treats that as a fact rather than
 * weather: it stops instead of reconnecting for ever. So a phone running the PWA costs one refused
 * socket and nothing else, while the till by the printer starts taking tickets out.
 *
 * Diagnostics go to the console on purpose, for now. The screen the owner reads — "nothing is
 * printing the kitchen's tickets", with its English string and its `es` translation — belongs with
 * the coverage view, which is already built (`print-coverage.ts`, hub#800/#1107). `sdk.print`
 * already produces the jobs this drain takes out (hub#344).
 */
export async function bootPrintHost(
  client: PrintHostClient,
  options: BootOptions = {},
): Promise<() => void> {
  // Idempotent: a hot reload, or any future second caller, must not put two loops on one device.
  if (running) {
    const already = running;
    return () => already.stop();
  }
  const deviceId = await (options.deviceId ?? (() => resolveDeviceId().catch(() => null)))();
  if (!deviceId) {
    // A browser with no device identity is not a print host and never will be until it has one.
    // Opening a socket to be told so would only be noise.
    return () => {};
  }
  // **A device that cannot reach hardware must not drain, even if it IS registered.** In a plain
  // browser the SDK answers every peripherals call with `hardware_unavailable` (hub#339), so a
  // phone somebody once registered as a print host would claim ticket after ticket and fail every
  // one — burning all five hand-outs and dead-lettering work a real till was about to print. The
  // hub's guards cannot catch this: as far as the hub is concerned that device is a legitimate
  // host. `detect()` asks "can this environment reach hardware at all", which is a property of the
  // environment and does not change while the process lives, so asking once here is enough.
  const hardware = await client.peripherals.detect().catch(() => ({ online: false }));
  if (!hardware.online) return () => {};
  // **Safety net BEFORE the registration** (hub#862): if the only printer on this device has no role,
  // it gets `receipt` here, so the alta below already counts it and the till's ticket finds its
  // printer. Best-effort: if the registry refuses, the boot carries on — without a role less gets
  // printed, but not booting prints nothing at all.
  await ensureDefaultPrinterRole(client);
  const session = options.session ?? getHubSession;
  const drain = createPrintDrain({
    url: options.url ?? printChannelUrl(globalThis.location),
    printJob: createJobPrinter(client),
    session: options.session ?? getHubSession,
    deviceId: () => deviceId,
    openSocket: options.openSocket ?? ((url) => new WebSocket(url) as unknown as DrainSocket),
    onDiagnostic:
      options.onDiagnostic ??
      ((event) => {
        if (event.kind === 'refused' || event.kind === 'print_failed') {
          console.warn('[print-host]', event.kind, event.code ?? '', event.message ?? '');
        }
      }),
  });
  // **The alta comes first, and it is what starts the drain** (hub#749). The drain does not retry a
  // configuration refusal, so a socket opened before this device is a registered host spends its one
  // attempt on `print.host_not_registered` and never drains again until the app is restarted.
  const registration = createPrintHostRegistration({
    rolesOnThisDevice: async () => printerRolesOfDevices(await client.peripherals.getDevices()),
    register:
      options.registerHost
        ? (role) => options.registerHost!(role, deviceId)
        : async (role) => {
            const body = (await postToRuntime('/api/print/hosts', deviceId, { role })) as {
              heartbeatSeconds?: number;
            };
            return { heartbeatSeconds: Number(body?.heartbeatSeconds) || 0 };
          },
    heartbeat:
      options.heartbeatHost
        ? () => options.heartbeatHost!(deviceId)
        : async () => {
            const body = (await postToRuntime('/api/print/hosts/heartbeat', deviceId)) as {
              refreshed?: number;
              heartbeatSeconds?: number;
            };
            return {
              refreshed: Number(body?.refreshed) || 0,
              heartbeatSeconds: Number(body?.heartbeatSeconds) || 0,
            };
          },
    session,
    onRegistered: () => {
      // The drain first, always: it is what takes the paper out, and a caller that throws must
      // not be able to leave this device registered as a host that never drains (hub#1732).
      drain.start();
      try {
        options.onRegistered?.();
      } catch (e) {
        console.warn('[print-host] the registration hook failed', e);
      }
    },
    onDiagnostic: (event) => console.warn('[print-host]', event.kind, event.role ?? '', event.message),
    setTimer: options.setTimer,
    clearTimer: options.clearTimer,
  });
  running = { stop: () => { registration.stop(); drain.stop(); } };
  // The first pass is AWAITED before the loop starts: the boot is over once this device either is a
  // print host or is not one, instead of leaving the answer in flight.
  await registration.tick();
  registration.start();
  const stop = running;
  return () => {
    stop.stop();
    running = null;
  };
}

/** Applies {@link printerNeedingDefaultRole} when there is something to apply. Never propagates. */
async function ensureDefaultPrinterRole(client: PrintHostClient): Promise<void> {
  const setRole = client.peripherals.setDeviceRole;
  if (!setRole) return;
  try {
    const target = printerNeedingDefaultRole(await client.peripherals.getDevices());
    if (!target) return;
    await setRole.call(client.peripherals, target, 'receipt');
    console.warn('[print-host] the only printer had no role — it is now the receipt one:', target);
  } catch (e) {
    console.warn('[print-host] could not assign the default receipt role', e);
  }
}

/** Forgets the running drain. For tests only — production has exactly one shell boot. */
bootPrintHost.reset = (): void => {
  running?.stop();
  running = null;
};
