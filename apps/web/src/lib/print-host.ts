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
import { getHubSession } from './session';
import { resolveDeviceId } from './device';

/** The minimum of the client this needs. Injected so the tests need no hardware. */
export interface PrintHostClient {
  peripherals: {
    getDevices(): Promise<PrintDevice[]>;
    print(
      printerId: string,
      documentType: string,
      data: Record<string, unknown>,
      jobId?: string,
    ): Promise<void>;
  };
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
 * the coverage view in hub#344, which is also where `sdk.print` starts producing jobs.
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
  running = drain;
  drain.start();
  return () => {
    drain.stop();
    running = null;
  };
}

/** Forgets the running drain. For tests only — production has exactly one shell boot. */
bootPrintHost.reset = (): void => {
  running?.stop();
  running = null;
};
