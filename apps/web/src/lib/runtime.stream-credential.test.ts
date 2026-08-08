// **The shell's end of the event channel** (hub#504).
//
// The hub no longer pushes a single event to a connection that has not presented a credential, so
// four live screens depend on this wiring existing: the auto-print on `sale.completed`
// (`print-on-sale.ts`), the kitchen docket on `kitchen.order.created` (`print-comanda.ts`), the
// live dashboard KPIs (`dashboard-widgets.ts`) and the install progress of the apps screen
// (`AppsPage.vue`). All four go through the one client this file builds, so this is where a
// deletion would be caught — and if it were not, they would fail the worst way there is: quietly,
// looking like "nothing is happening today".
import { afterEach, describe, expect, it, vi } from 'vitest';

import { fetchStreamTicket, getClient } from './runtime';

class FakeSocket {
  static last: FakeSocket | undefined;
  onopen: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  sent: string[] = [];
  closed = false;
  constructor(public url: string) {
    FakeSocket.last = this;
  }
  send(data: string) {
    this.sent.push(data);
  }
  close() {
    this.closed = true;
  }
}

function respondWith(status: number, body: unknown, calls?: Array<{ url: string; init?: RequestInit }>) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      calls?.push({ url, init });
      return Promise.resolve({
        ok: status >= 200 && status < 300,
        status,
        json: () => Promise.resolve(body),
      });
    }),
  );
}

const settle = () => new Promise((r) => setTimeout(r, 0));

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('the credential the shell reads the event stream with', () => {
  it('asks the runtime for a single-use ticket, on the authenticated door', async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    respondWith(200, { ok: true, data: { ticket: 'erpl_tkt_abc', expires_in_seconds: 60 } }, calls);

    expect(await fetchStreamTicket()).toBe('erpl_tkt_abc');
    expect(calls[0]?.url).toContain('/api/events/ticket');
    expect(calls[0]?.init?.method).toBe('POST');
  });

  it('answers null instead of throwing when there is no session yet', async () => {
    // The reconnect loop calls this on every attempt. A throw here would take the whole channel
    // down for good the first time somebody opens the app before logging in.
    respondWith(401, { ok: false, error: { code: 'unauthenticated' } });
    expect(await fetchStreamTicket()).toBeNull();
  });

  it('answers null when the runtime cannot be reached at all', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')));
    expect(await fetchStreamTicket()).toBeNull();
  });

  it('wires that ticket into the socket the whole shell listens on', async () => {
    respondWith(200, { ok: true, data: { ticket: 'erpl_tkt_wired', expires_in_seconds: 60 } });
    vi.stubGlobal('WebSocket', FakeSocket);
    // The client also builds the hardware bridge, which asks whether it is inside Tauri.
    vi.stubGlobal('window', {});

    // Exactly what print-on-sale, the dashboard and the apps screen do.
    getClient().on('sale.completed', () => {});
    expect(FakeSocket.last).toBeDefined();

    FakeSocket.last!.onopen?.();
    await settle();
    await settle();

    expect(FakeSocket.last!.sent.map((f) => JSON.parse(f))).toEqual([
      { type: 'auth', token: 'erpl_tkt_wired' },
    ]);
    expect(FakeSocket.last!.url).not.toContain('erpl_tkt_wired');
  });
});
