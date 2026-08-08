// The link that was missing (hub#501): a job out of the hub's queue becoming paper.
//
// What is worth pinning here is that this path is **unattended** — it resolves a printer by role and
// hands the structured document to the hardware, and it NEVER falls back to a print dialog, because
// there is nobody in the kitchen to press "Print". Everything it cannot do it says out loud, so the
// drain reports `failed` and the hub gives the ticket to the next host instead of losing it.
import { afterEach, describe, expect, it, vi } from 'vitest';

import { bootPrintHost, createJobPrinter, printChannelUrl, type PrintHostClient } from './print-host';
import type { DrainJob } from './print-drain';

function job(overrides: Partial<DrainJob> = {}): DrainJob {
  return {
    jobId: 'j1',
    role: 'kitchen',
    documentType: 'kitchen_order',
    document: { receipt_id: 'K-1', items: [{ name: 'Bacalao', quantity: 2 }] },
    format: 'receipt',
    attempts: 1,
    ...overrides,
  };
}

/** A device with the printers the test names, and a record of everything printed. */
function client(
  devices: { role: string | null; ip: string | null; port?: number }[],
  onPrint?: (...args: unknown[]) => Promise<void>,
): PrintHostClient & { printed: unknown[][] } {
  const printed: unknown[][] = [];
  return {
    printed,
    peripherals: {
      getDevices: () => Promise.resolve(devices),
      print: async (...args: unknown[]) => {
        printed.push(args);
        if (onPrint) await onPrint(...args);
      },
    },
  } as PrintHostClient & { printed: unknown[][] };
}

describe('print host — a queued job becomes paper', () => {
  // **The whole point of hub#501.** The document that comes out of the queue is structured, and it
  // reaches `erplora_print` untouched: the renderer picks its layout from `documentType` and reads
  // the fields from `document`. Nothing is converted along the way, which is what lets the same
  // ticket be re-rendered on other paper — or on a screen — later.
  it('sends the structured document to the printer that holds the job role', async () => {
    const c = client([
      { role: 'receipt', ip: '10.0.0.5' },
      { role: 'kitchen', ip: '192.168.100.196', port: 9100 },
    ]);

    await createJobPrinter(c)(job());

    expect(c.printed).toHaveLength(1);
    expect(c.printed[0]).toEqual([
      'network:192.168.100.196:9100',
      'kitchen_order',
      { receipt_id: 'K-1', items: [{ name: 'Bacalao', quantity: 2 }] },
      'j1',
    ]);
  });

  // The `jobId` travels with it: it is the idempotency key on the hub's queue AND on the device's
  // own retry queue, so a job handed out twice is still one piece of paper at the far end.
  it('carries the jobId all the way to the hardware', async () => {
    const c = client([{ role: 'receipt', ip: '10.0.0.5' }]);

    await createJobPrinter(c)(job({ role: 'receipt', jobId: 'sale-42' }));

    expect(c.printed[0][3]).toBe('sale-42');
  });

  // A role nobody registered a printer for is a **fact this device cannot fix**, and it has to be
  // said: the drain turns the rejection into `failed`, the hub puts the ticket back, and a host that
  // does have that printer takes it. Swallowing it would lose the ticket silently.
  it('refuses loudly when no printer holds that role', async () => {
    const c = client([{ role: 'receipt', ip: '10.0.0.5' }]);

    await expect(createJobPrinter(c)(job({ role: 'kitchen' }))).rejects.toThrow(/kitchen/);
    expect(c.printed).toHaveLength(0);
  });

  // A device row with a role but no address is not a printer: sending to it would resolve to a
  // nonsense target instead of saying "there is nowhere to print this".
  it('does not treat a printer with no address as usable', async () => {
    const c = client([{ role: 'kitchen', ip: null }]);

    await expect(createJobPrinter(c)(job())).rejects.toThrow(/kitchen/);
    expect(c.printed).toHaveLength(0);
  });

  // No hardware at all (the app is a plain browser tab, or the peripherals layer is down) is also a
  // refusal and not a shrug — this device is simply not able to be a print host right now.
  it('refuses when the hardware layer cannot even be asked', async () => {
    const c = {
      peripherals: {
        getDevices: () => Promise.reject(new Error('bridge not running')),
        print: () => Promise.resolve(),
      },
    } as unknown as PrintHostClient;

    await expect(createJobPrinter(c)(job())).rejects.toThrow(/bridge not running/);
  });

  // A printer that is there but refuses the bytes (no paper, lid open) surfaces as itself, so the
  // reason reaches `_print_queue.last_error` and the owner reads something actionable.
  it('lets the printer own failure through with its reason', async () => {
    const c = client([{ role: 'kitchen', ip: '192.168.100.196' }], () =>
      Promise.reject(new Error('out of paper')),
    );

    await expect(createJobPrinter(c)(job())).rejects.toThrow('out of paper');
  });

  // **The property that makes this unattended.** `print.ts` deliberately falls back to the browser's
  // print dialog when the hardware is not there — right for a cashier who pressed "print", wrong
  // here: a kitchen order would sit behind a modal on a tablet nobody is looking at, and the hub
  // would be told the ticket came out. Failing is the correct outcome; the queue keeps the job.
  // **The channel follows the page's scheme.** A hub served over https refuses a `ws://` socket
  // outright (mixed content), so a hard-coded scheme would mean the print host works in local
  // development and silently never connects on every deployed hub — the worst place to find out.
  it('derives the channel URL from the page, keeping its scheme', () => {
    expect(printChannelUrl({ protocol: 'https:', host: 'bar.erplora.com' })).toBe(
      'wss://bar.erplora.com/ws/print',
    );
    expect(printChannelUrl({ protocol: 'http:', host: 'localhost:8080' })).toBe(
      'ws://localhost:8080/ws/print',
    );
  });

  it('never opens the browser print dialog, whatever goes wrong', async () => {
    const dialog = vi.fn();
    const original = globalThis.print;
    globalThis.print = dialog;
    try {
      const noPrinter = client([]);
      await expect(createJobPrinter(noPrinter)(job())).rejects.toThrow();

      const broken = client([{ role: 'kitchen', ip: '10.0.0.9' }], () =>
        Promise.reject(new Error('lid open')),
      );
      await expect(createJobPrinter(broken)(job())).rejects.toThrow();

      expect(dialog).not.toHaveBeenCalled();
    } finally {
      globalThis.print = original;
    }
  });
});

describe('print host — booting it in the shell', () => {
  afterEach(() => {
    bootPrintHost.reset();
  });

  // **Booting twice must not drain twice.** Two loops on the same device would each claim, and the
  // hub hands two claims two DIFFERENT jobs (`SKIP LOCKED`) — so a second boot would not duplicate a
  // ticket, it would race for them. A hot reload, or a second call from a future caller, must be a
  // no-op rather than a second print host wearing the same device id.
  it('opens one channel however many times it is booted', async () => {
    const opened: string[] = [];
    const openSocket = (url: string) => {
      opened.push(url);
      return {
        send: () => {},
        close: () => {},
        onopen: null,
        onmessage: null,
        onclose: null,
        onerror: null,
      };
    };
    const c = client([{ role: 'receipt', ip: '10.0.0.5' }]);

    await bootPrintHost(c, { url: 'ws://h/ws/print', session: () => 's', deviceId: async () => 'till-1', openSocket });
    await bootPrintHost(c, { url: 'ws://h/ws/print', session: () => 's', deviceId: async () => 'till-1', openSocket });

    expect(opened).toEqual(['ws://h/ws/print']);
  });

  // A browser tab that has no device identity yet is not a print host, and asking the hub about it
  // would only earn a refusal. Nothing is opened until there is something to say.
  it('does not open a channel for a device with no identity', async () => {
    const opened: string[] = [];
    const c = client([]);

    await bootPrintHost(c, {
      url: 'ws://h/ws/print',
      session: () => 's',
      deviceId: async () => null,
      openSocket: (url: string) => {
        opened.push(url);
        throw new Error('should never be reached');
      },
    });

    expect(opened).toEqual([]);
  });
});
