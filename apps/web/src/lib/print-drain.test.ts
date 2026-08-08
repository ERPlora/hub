// The shell end of the print host's channel (hub#343). Tested against a fake socket, because what
// is worth pinning here is the LOOP — when it claims, when it confirms, what it does with a ticket
// it printed and could not confirm, and which refusals it must not retry — not the WebSocket, which
// `crates/server/tests/print_drain_ws.rs` already exercises against a real server.
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { createPrintDrain, type DrainJob, type DrainSocket } from './print-drain';

/** A socket the test drives by hand: nothing happens until the test says so. */
class FakeSocket implements DrainSocket {
  sent: Record<string, unknown>[] = [];
  closed = false;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;

  send(data: string): void {
    this.sent.push(JSON.parse(data) as Record<string, unknown>);
  }

  close(): void {
    this.closed = true;
  }

  /** The hub answering. */
  deliver(frame: Record<string, unknown>): void {
    this.onmessage?.({ data: JSON.stringify(frame) });
  }

  /** The connection dropping (a redeploy, a Wi-Fi cell change, a lid closing). */
  drop(): void {
    this.closed = true;
    this.onclose?.();
  }

  framesOfType(type: string): Record<string, unknown>[] {
    return this.sent.filter((f) => f.type === type);
  }
}

/** Timers the test runs on demand, so nothing waits in real seconds. */
class Timers {
  private queue: { fn: () => void; ms: number; id: number }[] = [];
  private nextId = 1;

  set = (fn: () => void, ms: number): unknown => {
    const id = this.nextId++;
    this.queue.push({ fn, ms, id });
    return id;
  };

  clear = (handle: unknown): void => {
    this.queue = this.queue.filter((t) => t.id !== handle);
  };

  /** Runs everything currently scheduled (once). */
  runAll(): void {
    const due = this.queue;
    this.queue = [];
    for (const t of due) t.fn();
  }

  get pending(): number {
    return this.queue.length;
  }
}

interface Harness {
  drain: ReturnType<typeof createPrintDrain>;
  sockets: FakeSocket[];
  timers: Timers;
  printed: DrainJob[];
  diagnostics: { kind: string; code?: string }[];
  socket(): FakeSocket;
}

function harness(
  overrides: {
    printJob?: (job: DrainJob) => Promise<void>;
    session?: () => string | null;
    deviceId?: () => string | null;
  } = {},
): Harness {
  const sockets: FakeSocket[] = [];
  const timers = new Timers();
  const printed: DrainJob[] = [];
  const diagnostics: { kind: string; code?: string }[] = [];

  const drain = createPrintDrain({
    url: 'ws://hub.test/ws/print',
    session: overrides.session ?? (() => 'session-token'),
    deviceId: overrides.deviceId ?? (() => 'till-1'),
    openSocket: () => {
      const s = new FakeSocket();
      sockets.push(s);
      return s;
    },
    printJob:
      overrides.printJob ??
      (async (job) => {
        printed.push(job);
      }),
    setTimer: timers.set,
    clearTimer: timers.clear,
    onDiagnostic: (e) => diagnostics.push({ kind: e.kind, code: e.code }),
  });

  return {
    drain,
    sockets,
    timers,
    printed,
    diagnostics,
    socket: () => sockets[sockets.length - 1],
  };
}

/** Opens the socket and completes the handshake for `roles`. */
function connect(h: Harness, roles = ['receipt']): FakeSocket {
  h.drain.start();
  const s = h.socket();
  s.onopen?.();
  s.deliver({ type: 'ready', deviceId: 'till-1', roles, heartbeatSeconds: 30 });
  return s;
}

describe('print drain — the shell end of /ws/print', () => {
  let h: Harness;

  beforeEach(() => {
    h = harness();
  });

  it('introduces itself with the session and the device, and nothing else', () => {
    h.drain.start();
    const s = h.socket();
    s.onopen?.();

    expect(s.sent[0]).toEqual({ type: 'hello', session: 'session-token', deviceId: 'till-1' });
  });

  it('does not open a socket at all without a session or a device id', () => {
    const anonymous = harness({ session: () => null });
    anonymous.drain.start();
    expect(anonymous.sockets).toHaveLength(0);

    const nameless = harness({ deviceId: () => null });
    nameless.drain.start();
    expect(nameless.sockets).toHaveLength(0);
  });

  // A device that has just come back may have tickets waiting from while it was off. Waiting to be
  // woken would leave them there until the next sale.
  it('claims every role the hub gave it as soon as it is ready', () => {
    const s = connect(h, ['kitchen', 'receipt']);

    expect(s.framesOfType('claim').map((f) => f.role)).toEqual(['kitchen', 'receipt']);
    expect(h.drain.roles()).toEqual(['kitchen', 'receipt']);
  });

  it('prints the job it is handed and confirms it by jobId', async () => {
    const s = connect(h);
    s.deliver({ type: 'job', jobId: 'j1', role: 'receipt', documentType: 'receipt', document: { receipt_id: 't' }, format: 'receipt', attempts: 1 });
    await vi.waitFor(() => expect(h.printed).toHaveLength(1));

    // The STRUCTURED document reaches the printer as it left the hub — that is the whole of
    // hub#501: nothing between the queue and the paper reinterprets the ticket.
    expect(h.printed[0].document).toEqual({ receipt_id: 't' });
    expect(h.printed[0].documentType).toBe('receipt');
    expect(s.framesOfType('done')).toEqual([{ type: 'done', jobId: 'j1' }]);
  });

  it('keeps pulling after each ticket until the hub says there is nothing left', async () => {
    const s = connect(h);
    s.deliver({ type: 'job', jobId: 'j1', role: 'receipt', documentType: 'receipt', document: { receipt_id: '1' }, format: 'receipt', attempts: 1 });
    await vi.waitFor(() => expect(s.framesOfType('claim')).toHaveLength(2));

    s.deliver({ type: 'idle', role: 'receipt' });
    expect(s.framesOfType('claim')).toHaveLength(2);
  });

  // The reason this is a socket and not polling.
  it('claims when the hub says a ticket arrived for one of its roles', () => {
    const s = connect(h);
    s.sent.length = 0;

    s.deliver({ type: 'wake', role: 'receipt' });
    expect(s.framesOfType('claim')).toEqual([{ type: 'claim', role: 'receipt' }]);
  });

  // 🔴 The decision this piece exists to make. The hub reprints an unconfirmed ticket once its
  // lease expires — losing a ticket is worse than duplicating one — so a client that forgot its
  // confirmations would make the business pay a duplicate for every dropped connection.
  it('re-confirms a ticket it printed but could not confirm, as soon as there is a socket again', async () => {
    const first = connect(h);
    first.deliver({ type: 'job', jobId: 'j1', role: 'receipt', documentType: 'receipt', document: { receipt_id: 't' }, format: 'receipt', attempts: 1 });
    await vi.waitFor(() => expect(first.framesOfType('done')).toHaveLength(1));
    // The `done` went into a socket that was already dying: the hub never acknowledged it.
    expect(h.drain.pendingConfirmations()).toEqual(['j1']);

    first.drop();
    h.timers.runAll(); // the reconnect
    const second = h.socket();
    expect(second).not.toBe(first);
    second.onopen?.();
    second.deliver({ type: 'ready', deviceId: 'till-1', roles: ['receipt'], heartbeatSeconds: 30 });

    const frames = second.sent.map((f) => f.type);
    expect(second.framesOfType('done')).toEqual([{ type: 'done', jobId: 'j1' }]);
    // Claiming first could hand us back the very ticket we are about to confirm.
    expect(frames.indexOf('done')).toBeGreaterThanOrEqual(0);
    expect(frames.indexOf('done')).toBeLessThan(frames.indexOf('claim'));
  });

  it('forgets a confirmation once the hub acknowledges it', async () => {
    const s = connect(h);
    s.deliver({ type: 'job', jobId: 'j1', role: 'receipt', documentType: 'receipt', document: { receipt_id: 't' }, format: 'receipt', attempts: 1 });
    await vi.waitFor(() => expect(h.drain.pendingConfirmations()).toEqual(['j1']));

    s.deliver({ type: 'ack', jobId: 'j1', confirmed: true });
    expect(h.drain.pendingConfirmations()).toEqual([]);
  });

  // A printer that will not print is not a ticket that is gone: the hub has to hear about it so
  // another host gets a turn.
  it('reports a printer that refused, with its reason, instead of going quiet', async () => {
    const broken = harness({
      printJob: async () => {
        throw new Error('out of paper');
      },
    });
    const s = connect(broken);
    const claimsBefore = s.framesOfType('claim').length;
    s.deliver({ type: 'job', jobId: 'j1', role: 'receipt', documentType: 'receipt', document: { receipt_id: 't' }, format: 'receipt', attempts: 1 });

    await vi.waitFor(() => expect(s.framesOfType('failed')).toHaveLength(1));
    expect(s.framesOfType('failed')[0]).toEqual({
      type: 'failed',
      jobId: 'j1',
      error: 'out of paper',
    });
    expect(broken.drain.pendingConfirmations()).toEqual([]);
    expect(broken.diagnostics.map((d) => d.kind)).toContain('print_failed');
    // 🔴 And it does NOT ask for the next one. A printer out of paper is out of paper for the next
    // ticket too: claiming again straight away spins claim→fail→claim and burns all five hand-outs
    // in milliseconds, dead-lettering a ticket whose only problem was a roll about to be changed.
    expect(s.framesOfType('claim')).toHaveLength(claimsBefore);
  });

  it('beats on the cadence the hub published, not one of its own', () => {
    const s = connect(h);
    s.sent.length = 0;

    h.timers.runAll();
    expect(s.framesOfType('beat')).toHaveLength(1);
  });

  it('reconnects after the socket drops', () => {
    const first = connect(h);
    first.drop();

    expect(h.sockets).toHaveLength(1);
    h.timers.runAll();
    expect(h.sockets).toHaveLength(2);
  });

  // 🔴 A device that is not registered will not become registered by asking again. Reconnecting
  // into a refusal hammers the hub and hides the problem from whoever has to fix it.
  it.each([
    'unauthenticated',
    'print.host_not_registered',
    'print.device_required',
    'print.not_ready',
  ])('stops for good on %s instead of retrying it for ever', (code) => {
    const s = connect(h);

    s.deliver({ type: 'error', code, message: 'no' });

    expect(s.closed).toBe(true);
    expect(h.drain.running()).toBe(false);
    h.timers.runAll();
    expect(h.sockets).toHaveLength(1);
    expect(h.diagnostics.some((d) => d.kind === 'refused' && d.code === code)).toBe(true);
  });

  // …but a refusal about ONE role is not a refusal about the device. The bar till asking for the
  // kitchen is a bug in the caller, not a reason to stop printing the bar's own tickets.
  it('keeps draining after a refusal that is only about one role', () => {
    const s = connect(h);

    s.deliver({ type: 'error', code: 'print.role_not_hosted', message: 'not yours' });

    expect(s.closed).toBe(false);
    expect(h.drain.running()).toBe(true);
  });

  // Being retired while connected is the same fact as never having been registered.
  it('stops when a beat reports that the device hosts nothing any more', () => {
    const s = connect(h);

    s.deliver({ type: 'beat', refreshed: 0, heartbeatSeconds: 30 });

    expect(h.drain.running()).toBe(false);
    expect(h.diagnostics.some((d) => d.code === 'print.host_not_registered')).toBe(true);
  });

  it('stops cleanly when asked, and does not reconnect behind the caller´s back', () => {
    const s = connect(h);

    h.drain.stop();

    expect(s.closed).toBe(true);
    h.timers.runAll();
    expect(h.sockets).toHaveLength(1);
    expect(h.drain.running()).toBe(false);
  });

  it('ignores a frame it cannot parse rather than tearing the socket down', () => {
    const s = connect(h);

    s.onmessage?.({ data: 'not json at all' });

    expect(s.closed).toBe(false);
    expect(h.drain.running()).toBe(true);
  });
});
