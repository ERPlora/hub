// hub#1732 — **the device becomes a notification target and nobody asks for the permission.**
//
// `POST_NOTIFICATIONS` is declared in both manifests and `PermissionPolicy.required()` lists it,
// so everything is in place to ask — and the only caller was `peripherals.notify()`, which fires
// when a kitchen order arrives. Measured on a clean install used for 40 minutes (business setup,
// template, till, appointment, sale, charge, printing): `dumpsys` reported
// `POST_NOTIFICATIONS: granted=false` with **no `USER_SET` flag**, the fingerprint of a permission
// that was never put in front of the user. The other two dangerous ones carry `USER_SET`, because
// their dialog does get shown.
//
// The moment that HAS to ask is this one: the alta of this device as a print host. That is when
// somebody is standing at the till configuring it, and it is what makes this device the one that
// will be told an order came in. Waiting for the first order instead means asking a tablet propped
// on a shelf with nobody in front of it — the dialog goes unanswered and the notification that
// prompted it is lost.
import { afterEach, describe, expect, it } from 'vitest';

import { bootPrintHost, type PrintHostClient } from './print-host';

function socket() {
  return { send: () => {}, close: () => {}, onopen: null, onmessage: null, onclose: null, onerror: null };
}

/** A till with one reachable printer that already has a role: a print host, by definition. */
function client(): PrintHostClient {
  return {
    peripherals: {
      detect: () => Promise.resolve({ online: true }),
      getDevices: () => Promise.resolve([{ key: 'p1', role: 'kitchen', ip: '10.0.0.7' }]),
      print: () => Promise.resolve(),
    },
  };
}

afterEach(() => bootPrintHost.reset());

describe('the print host alta announces that this device now gets told about orders', () => {
  it('calls onRegistered once the hub confirms a role', async () => {
    const announced: number[] = [];
    const stop = await bootPrintHost(client(), {
      url: 'ws://localhost/ws/print',
      deviceId: () => Promise.resolve('dev-1'),
      session: () => 'tok',
      openSocket: socket,
      registerHost: () => Promise.resolve({ heartbeatSeconds: 30 }),
      heartbeatHost: () => Promise.resolve({ refreshed: 1, heartbeatSeconds: 30 }),
      setTimer: () => null,
      clearTimer: () => {},
      onRegistered: () => announced.push(1),
    });
    stop();

    // Exactly once: a primer that reappears on every heartbeat is the nagging Android's own
    // guidance exists to prevent.
    expect(announced).toEqual([1]);
  });

  it('says nothing on a device that holds no role — there is nothing to be told about', async () => {
    const announced: number[] = [];
    const noRole: PrintHostClient = {
      peripherals: {
        detect: () => Promise.resolve({ online: true }),
        getDevices: () => Promise.resolve([{ key: 'p1', role: null, ip: '10.0.0.7' }]),
        print: () => Promise.resolve(),
      },
    };
    const stop = await bootPrintHost(noRole, {
      url: 'ws://localhost/ws/print',
      deviceId: () => Promise.resolve('dev-1'),
      session: () => 'tok',
      openSocket: socket,
      registerHost: () => Promise.resolve({ heartbeatSeconds: 30 }),
      heartbeatHost: () => Promise.resolve({ refreshed: 0, heartbeatSeconds: 30 }),
      setTimer: () => null,
      clearTimer: () => {},
      onRegistered: () => announced.push(1),
    });
    stop();

    expect(announced).toEqual([]);
  });
});
