// hub#1731 — the silent failure, provoked END TO END across every link the fix spans in the shell:
//
//   runtime answer → lib/print-enqueue (the wire) → lib/print (the gate) → lib/print-on-sale → onFailure
//
// Each link has its own tests. This file exists because the bug WAS the links drifting apart: the
// runtime could have said anything and `main.ts` threw it away (`return body?.ok === true`), so
// every unit was right and the till still charged in silence on a hub with no printer. A shell that
// carries `liveHosts` through three links and drops it in the fourth is the same silence again, and
// no unit test would notice — this one would.
//
// Only `main.ts` (the toast) is outside: it is the bootstrap file and has no test harness. The fact
// that reaches it — `SaleTicketFailure.awaitingHost` — is asserted here at the door it comes out of.
import { describe, expect, it, vi } from 'vitest';

import { createEnqueuePrintJob } from './print-enqueue';
import { createPrintService } from './print';
import { bootPrintOnSale } from './print-on-sale';
import { CLIENT_INSTANCE } from './client-instance';

type Listener = (payload: unknown, meta?: { clientInstance?: string }) => void;

/** The runtime, answering `POST /api/print/jobs` with one canned body. */
function runtimeAnswering(body: Record<string, unknown>) {
  return vi.fn(async () => ({ ok: true, status: 200, json: async () => body })) as unknown as typeof fetch;
}

/**
 * The hub of the issue: printing installed with «print on sale» ON, a sale to print, and NO
 * hardware reachable from this device — so the gate has nowhere to go but the hub's queue.
 */
function hubWithNoPrinter() {
  const listeners: Record<string, Listener[]> = {};
  const client = {
    on: (event: string, cb: Listener) => {
      (listeners[event] ??= []).push(cb);
      return () => {};
    },
    onEvent: (event: string, cb: Listener) => {
      (listeners[event] ??= []).push(cb);
      return () => {};
    },
    query: vi.fn(async (name: string) => {
      if (name === 'printing.settings.get') return [{ auto_print_on_sale: 1 }];
      return [];
    }),
    peripherals: {
      getDevices: vi.fn(async () => {
        throw new Error('hardware_unavailable');
      }),
      print: vi.fn(async () => undefined),
      openDrawer: vi.fn(async () => undefined),
    },
  };
  return {
    client: client as never,
    // Charged at THIS till (hub#1980): only the till that charged prints.
    emit: async (payload: unknown) => {
      for (const cb of listeners['sale.completed'] ?? []) cb(payload, { clientInstance: CLIENT_INSTANCE });
      await new Promise((r) => setTimeout(r, 0));
    },
  };
}

/** Wires the real chain over a runtime that answers `body`, and charges one sale through it. */
async function chargeOneSale(body: Record<string, unknown>) {
  const fetchImpl = runtimeAnswering(body);
  const { client, emit } = hubWithNoPrinter();
  const gate = createPrintService(client, {
    enqueue: createEnqueuePrintJob(fetchImpl),
    browserPrint: vi.fn(),
    iframePrint: vi.fn(),
  });
  const onFailure = vi.fn();
  // The paper itself is the sales module's (hub#1921): a stand-in, since what is under test here is
  // where the paper goes, not what it says.
  const saleDocument = async (saleId: string) => ({
    document: { receipt_id: saleId, items: [{ name: 'Corte', quantity: 1, total: 29.9 }], total: 29.9 },
    complete: true,
  });
  bootPrintOnSale(client, { print: gate, onFailure, saleDocument });

  await emit({ sale_id: '42' });

  return { fetchImpl, onFailure };
}

describe('the ticket that queues with no printer is NOT reported as printed (hub#1731)', () => {
  it('the exact case of the issue: queued, nobody draining → the till hears it, and hears WHICH case it is', async () => {
    const { fetchImpl, onFailure } = await chargeOneSale({ ok: true, status: 'queued', liveHosts: 0 });

    // The job did reach the queue (it is safe, it will come out once a printer exists)…
    const [url, init] = (fetchImpl as unknown as ReturnType<typeof vi.fn>).mock.calls[0]!;
    expect(String(url)).toContain('/api/print/jobs');
    expect(JSON.parse(String((init as RequestInit).body))).toMatchObject({ jobId: 'sale-42', role: 'receipt' });
    // …and the silence is over: the warning fires ONCE and says the paper is waiting for a printer,
    // which is what tells the cashier to set one up instead of hunting for a jam.
    expect(onFailure).toHaveBeenCalledTimes(1);
    expect(onFailure.mock.calls[0]![0]).toMatchObject({ saleId: '42', awaitingHost: true });
  });

  it('queued with a till draining receipts stays quiet: late, not lost', async () => {
    const { onFailure } = await chargeOneSale({ ok: true, status: 'queued', liveHosts: 1 });

    expect(onFailure).not.toHaveBeenCalled();
  });

  it('a runtime that predates the answer stays quiet too: «I do not know» is not «nobody»', async () => {
    const { onFailure } = await chargeOneSale({ ok: true, status: 'queued' });

    expect(onFailure).not.toHaveBeenCalled();
  });

  it('a retry the runtime already had (duplicate) is judged by the same coverage, not by its status', async () => {
    const { onFailure } = await chargeOneSale({ ok: true, status: 'duplicate', liveHosts: 0 });

    expect(onFailure).toHaveBeenCalledTimes(1);
    expect(onFailure.mock.calls[0]![0]).toMatchObject({ awaitingHost: true });
  });
});
