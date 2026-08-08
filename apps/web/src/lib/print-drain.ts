// **The print host, client side** (hub#343, ADR-0196 §6) — the shell end of `GET /ws/print`.
//
// The queue lives in the hub (hub#341) and the hub knows which device drains which role (hub#342).
// This is the loop that actually takes the paper out: connect, say who we are, claim, print,
// confirm. It is deliberately transport-only — **how** a document becomes paper is injected
// (`printJob`), because that is the part that touches hardware and the only part this file cannot
// test. The implementation that closes the circle lives in `print-host.ts` (hub#501).
//
// ## The one decision worth reading
//
// **A ticket that was printed but whose confirmation never arrived is confirmed again on
// reconnect.** The hub's rule is that an unconfirmed job goes back to the queue when its lease
// expires, and the next host prints it a second time — losing a ticket is worse than duplicating
// one, so that is the right way round. But "right way round" is not "free": every socket blip would
// cost the business a duplicate ticket if the client simply forgot. So printed-but-unconfirmed jobs
// are remembered and re-sent as soon as there is a socket again. The duplicate then costs only what
// it must — a device that actually died — instead of every dropped connection.
//
// Re-sending is safe precisely because `jobId` is the idempotency key on both doors: confirming
// twice is one confirmation, and confirming a job that already came back and was reprinted is a
// plain `no`.
//
// ## What this file will not do
//
// It never reconnects into a refusal. `unauthenticated`, `print.host_not_registered` and
// `print.device_required` are facts about how this device is set up, not weather: retrying them in
// a loop would hammer the hub and hide the problem from whoever has to fix it.

/** A job as it arrives from the hub. Mirror of the `job` frame. */
export interface DrainJob {
  jobId: string;
  role: string;
  /**
   * Which renderer turns this into paper (`receipt`, `kitchen_order`, …). The hub only ever queues
   * one of the names `escpos::DocumentType` knows, so this is safe to hand straight to the hardware.
   */
  documentType: string;
  /**
   * **The document, structured** (hub#501). This is what has to become paper — the object
   * `escpos::render_document` reads, not a rendering of it. It used to be self-contained HTML, and
   * that could not become paper at all: there is no HTML→ESC/POS entry, and by decision there never
   * will be. Structured, the same ticket goes to 58mm, to 80mm, to a PDF or to a screen, and can be
   * rendered again the day the business changes printer.
   */
  document: Record<string, unknown>;
  format: 'receipt' | 'a4';
  /** How many times the hub has handed this job out. `> 1` means somebody already had a go. */
  attempts: number;
}

/** The minimum of a WebSocket this loop uses. Injected so the tests do not need a server. */
export interface DrainSocket {
  send(data: string): void;
  close(): void;
  onopen: (() => void) | null;
  onmessage: ((event: { data: string }) => void) | null;
  onclose: (() => void) | null;
  onerror: ((event?: unknown) => void) | null;
}

/** Something worth surfacing. Facts, not sentences: the UI writes the words (and translates them). */
export interface DrainDiagnostic {
  kind: 'refused' | 'print_failed' | 'connected' | 'disconnected';
  code?: string;
  message?: string;
  role?: string;
  jobId?: string;
}

export interface PrintDrainOptions {
  /** Where the channel lives (`ws(s)://…/ws/print`). */
  url: string;
  /** Turns a document into paper. Resolving = it came out; throwing = it did not, with a reason. */
  printJob(job: DrainJob): Promise<void>;
  /** The hub session, read lazily: it rotates, and a stale copy would fail every reconnect. */
  session(): string | null;
  /** This device's identity (`X-Device-Id`). */
  deviceId(): string | null;
  /** Opens the socket. Injected so the tests drive one by hand. */
  openSocket(url: string): DrainSocket;
  /** Timer seam, so the tests do not wait in real seconds. */
  setTimer?(fn: () => void, ms: number): unknown;
  clearTimer?(handle: unknown): void;
  /** Told about anything a human would want to know (a refusal, a printer that will not print). */
  onDiagnostic?(event: DrainDiagnostic): void;
}

/**
 * Refusals that will not get better by trying again. Every one is a fact about how this device is
 * set up, so the loop stops and says so rather than reconnecting for ever.
 *
 * `print.role_not_hosted` is deliberately **not** here: that one is about a single role, and a bar
 * till that asked for the kitchen by mistake must keep printing the bar's own tickets.
 */
const FATAL_CODES = new Set([
  'unauthenticated',
  'print.device_required',
  'print.host_not_registered',
  'print.not_ready',
  'print.frame_too_large',
]);

/** Wait before reconnecting, doubling up to a ceiling: a hub that is redeploying does come back. */
const RECONNECT_MIN_MS = 1_000;
const RECONNECT_MAX_MS = 30_000;

/** Beat cadence used until the hub says otherwise — which it does, in `ready`. */
const FALLBACK_HEARTBEAT_SECONDS = 30;

export interface PrintDrain {
  start(): void;
  stop(): void;
  /** Roles the hub said this device drains, once connected. */
  roles(): string[];
  /** Printed but not yet acknowledged — what a reconnect re-sends. */
  pendingConfirmations(): string[];
  /** `true` while the loop is meant to be running (it may be between reconnects). */
  running(): boolean;
}

export function createPrintDrain(options: PrintDrainOptions): PrintDrain {
  const setTimer = options.setTimer ?? ((fn: () => void, ms: number) => setTimeout(fn, ms));
  const clearTimer =
    options.clearTimer ?? ((h: unknown) => clearTimeout(h as ReturnType<typeof setTimeout>));
  const diagnose = (event: DrainDiagnostic) => options.onDiagnostic?.(event);

  let socket: DrainSocket | null = null;
  let wanted = false;
  let stoppedForGood = false;
  let hostRoles: string[] = [];
  let backoffMs = RECONNECT_MIN_MS;
  let beatHandle: unknown = null;
  let reconnectHandle: unknown = null;
  /** Printed, not yet acknowledged by the hub. Insertion order = the order they were printed. */
  const unconfirmed = new Set<string>();
  /** Roles a print is in flight for, so a `wake` does not start a second claim in parallel. */
  const busy = new Set<string>();

  function send(frame: Record<string, unknown>): void {
    try {
      socket?.send(JSON.stringify(frame));
    } catch {
      // A send into a socket that just died is not worth reporting: `onclose` is about to run and
      // will reconnect. What matters — an unconfirmed ticket — is already remembered.
    }
  }

  function stopBeat(): void {
    if (beatHandle !== null) {
      clearTimer(beatHandle);
      beatHandle = null;
    }
  }

  function scheduleBeat(seconds: number): void {
    stopBeat();
    const ms = Math.max(1, seconds) * 1000;
    beatHandle = setTimer(() => {
      send({ type: 'beat' });
      scheduleBeat(seconds);
    }, ms);
  }

  function teardown(): void {
    stopBeat();
    const dying = socket;
    socket = null;
    try {
      dying?.close();
    } catch {
      /* already gone */
    }
  }

  function scheduleReconnect(): void {
    if (!wanted || stoppedForGood || reconnectHandle !== null) return;
    const wait = backoffMs;
    backoffMs = Math.min(backoffMs * 2, RECONNECT_MAX_MS);
    reconnectHandle = setTimer(() => {
      reconnectHandle = null;
      connect();
    }, wait);
  }

  function onRefusal(code: string, message: string): void {
    diagnose({ kind: 'refused', code, message });
    if (!FATAL_CODES.has(code)) return;
    // Stop, loudly. A device that is not registered will not become registered by asking again.
    stoppedForGood = true;
    wanted = false;
    teardown();
  }

  async function handleJob(job: DrainJob): Promise<void> {
    busy.add(job.role);
    try {
      await options.printJob(job);
    } catch (e) {
      busy.delete(job.role);
      const message = e instanceof Error ? e.message : String(e);
      diagnose({ kind: 'print_failed', jobId: job.jobId, role: job.role, message });
      // Say so: the hub puts the ticket back for another host instead of waiting out the lease.
      send({ type: 'failed', jobId: job.jobId, error: message });
      // And **stop pulling this role**. A printer that is out of paper is out of paper for the next
      // ticket too, so claiming again immediately would spin claim→fail→claim and burn all five
      // hand-outs in a few milliseconds — dead-lettering a ticket whose only problem was a roll
      // somebody was about to change. The next `wake` (or the next reconnect) tries again.
      return;
    }
    // The paper is out. From here the ONLY thing that matters is that the hub finds out — if it
    // does not, the lease expires and somebody prints this ticket a second time.
    unconfirmed.add(job.jobId);
    send({ type: 'done', jobId: job.jobId });
    busy.delete(job.role);
    // There may be more behind it; keep pulling until the hub answers `idle`.
    send({ type: 'claim', role: job.role });
  }

  function onFrame(raw: string): void {
    let frame: Record<string, unknown>;
    try {
      frame = JSON.parse(raw) as Record<string, unknown>;
    } catch {
      return; // not our protocol: ignore rather than tear down a working socket
    }
    switch (String(frame.type ?? '')) {
      case 'ready': {
        backoffMs = RECONNECT_MIN_MS;
        hostRoles = Array.isArray(frame.roles) ? (frame.roles as unknown[]).map(String) : [];
        scheduleBeat(Number(frame.heartbeatSeconds) || FALLBACK_HEARTBEAT_SECONDS);
        diagnose({ kind: 'connected' });
        // Pay the debt FIRST: anything printed whose confirmation never landed. Before claiming,
        // deliberately — a reconnect that pulled first could be handed the very ticket it is about
        // to confirm, and would print it twice for nothing.
        for (const jobId of unconfirmed) send({ type: 'done', jobId });
        // Then drain whatever waited while we were away; `wake` covers what arrives from now on.
        for (const role of hostRoles) send({ type: 'claim', role });
        break;
      }
      case 'job':
        void handleJob({
          jobId: String(frame.jobId ?? ''),
          role: String(frame.role ?? ''),
          documentType: String(frame.documentType ?? ''),
          // Passed along as it came. A frame whose `document` is not an object is not repaired into
          // an empty one here: the printer refuses it and the hub is told, which is how a corrupt
          // row surfaces instead of cutting blank paper.
          document: (frame.document ?? {}) as Record<string, unknown>,
          format: frame.format === 'a4' ? 'a4' : 'receipt',
          attempts: Number(frame.attempts) || 0,
        });
        break;
      case 'idle':
        // Nothing left for that role: stop pulling and wait to be woken.
        busy.delete(String(frame.role ?? ''));
        break;
      case 'wake': {
        const role = String(frame.role ?? '');
        // Already printing that role: the claim that follows the current job picks this one up.
        if (!busy.has(role)) send({ type: 'claim', role });
        break;
      }
      case 'ack':
        unconfirmed.delete(String(frame.jobId ?? ''));
        break;
      case 'beat':
        // `refreshed: 0` = the hub no longer has this device as a host; it was retired while we
        // were connected. Same fact as never having been registered, so same ending.
        if (Number(frame.refreshed) === 0) {
          onRefusal('print.host_not_registered', 'this device no longer hosts any printer role');
        }
        break;
      case 'error':
        onRefusal(String(frame.code ?? 'error'), String(frame.message ?? ''));
        break;
      default:
        break;
    }
  }

  function connect(): void {
    if (!wanted || stoppedForGood || socket) return;
    const session = options.session();
    const deviceId = options.deviceId();
    if (!session || !deviceId) {
      // Not a refusal from the hub: we have nothing to say yet. Worth trying again, because this
      // one DOES get better on its own (the user logs in, the browser mints its device id).
      scheduleReconnect();
      return;
    }
    const ws = options.openSocket(options.url);
    socket = ws;
    ws.onopen = () => send({ type: 'hello', session, deviceId });
    ws.onmessage = (event) => onFrame(String(event.data));
    ws.onclose = () => {
      stopBeat();
      socket = null;
      hostRoles = [];
      busy.clear();
      if (!stoppedForGood) diagnose({ kind: 'disconnected' });
      scheduleReconnect();
    };
    ws.onerror = () => {
      // `onclose` always follows an error, so reconnecting from there keeps one path instead of two.
    };
  }

  return {
    start(): void {
      if (wanted) return;
      wanted = true;
      stoppedForGood = false;
      backoffMs = RECONNECT_MIN_MS;
      connect();
    },
    stop(): void {
      wanted = false;
      if (reconnectHandle !== null) {
        clearTimer(reconnectHandle);
        reconnectHandle = null;
      }
      teardown();
    },
    roles: () => [...hostRoles],
    pendingConfirmations: () => [...unconfirmed],
    running: () => wanted,
  };
}
