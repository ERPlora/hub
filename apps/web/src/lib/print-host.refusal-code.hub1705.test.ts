// hub#1705 — when the hub refuses the device that prints, the trace says WHY.
//
// The print host registers itself unattended: nobody is looking at the screen, and what is left is
// the diagnostic line. Until this issue the runtime answered `401 {"error": "<prose>"}` and the
// client kept `/api/print/hosts → HTTP 401` — a path and a number. The door now sends the shared
// envelope (`unauthorized` / `forbidden`), and the refusal the client throws carries that code.
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('./runtime', () => ({ RUNTIME_URL: 'http://hub', runtimeHeaders: () => ({}) }));

import { bootPrintHost, type PrintHostClient } from './print-host';

function socket() {
  return { send: () => {}, close: () => {}, onopen: null, onmessage: null, onclose: null, onerror: null };
}

/** A till with one reachable printer holding a role: it will try to register. */
function client(): PrintHostClient {
  return {
    peripherals: {
      detect: () => Promise.resolve({ online: true }),
      getDevices: () => Promise.resolve([{ key: 'p1', role: 'kitchen', ip: '10.0.0.7' }]),
      print: () => Promise.resolve(),
    },
  };
}

afterEach(() => {
  bootPrintHost.reset();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('a refused print host registration names its reason (hub#1705)', () => {
  it('keeps the stable code of the refusal instead of `→ HTTP 401`', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: false,
        status: 401,
        json: async () => ({ ok: false, error: { code: 'unauthorized', message: 'missing session' } }),
      })),
    );
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});

    const stop = await bootPrintHost(client(), {
      url: 'ws://localhost/ws/print',
      deviceId: () => Promise.resolve('dev-1'),
      session: () => 'tok',
      openSocket: socket,
      setTimer: () => null,
      clearTimer: () => {},
    });
    stop();

    const lines = warn.mock.calls.map((call) => call.map(String).join(' '));
    const refused = lines.find((line) => line.includes('register_failed'));
    expect(refused, `no register_failed diagnostic among: ${lines.join(' | ')}`).toBeDefined();
    expect(refused).toContain('unauthorized');
    expect(refused).not.toContain('HTTP 401');
  });
});
