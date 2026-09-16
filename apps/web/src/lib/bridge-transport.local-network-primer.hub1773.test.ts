// @vitest-environment happy-dom
// hub#1773 — **the dialog that pops with nothing in front of it.**
//
// This is the control that catches the real symptom, end to end and through the real chain: the
// shell's transport, the real primer, the real i18n. Nothing is faked except the two things that
// only exist on a device — Android's `check_permissions`/`request_permissions` and the sheet.
//
// What it pins: `discoverPrinters()` — the tap that means «find my printer» — puts OUR sentence in
// front of the system dialog, and only then lets Android ask. Before hub#1773 the transport went
// straight to `plugin:erplora-android|request_permissions` with nothing before it, which is why the
// dialog read as opportunistic and got refused; and a refusal here is close to permanent, because
// after two the system stops presenting the dialog at all.
//
// The three ways this goes wrong are all pinned below: asking cold, asking again and again, and
// letting a «no» take the scan down with it.
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { tauriMode, invokeSpy, calls, lanAsks, confirmSpy } = vi.hoisted(() => {
  const calls: string[] = [];
  return {
    calls,
    /** Every time Android itself was asked for the local-network permission. */
    lanAsks: [] as string[][],
    tauriMode: { value: true },
    /** What the plugin answers. The whole suite turns on this map. */
    invokeSpy: vi.fn<(cmd: string, args?: Record<string, unknown>) => Promise<unknown>>(),
    confirmSpy: vi.fn<() => Promise<boolean>>(async () => true),
  };
});

vi.mock('./device', () => ({
  isTauri: () => tauriMode.value,
  invokeTauri: invokeSpy,
}));

// The sheet is an `ion-alert`, and an alert needs a browser. Only the presentation is replaced:
// what decides WHEN it goes up, and what the transport does around it, is the real code.
vi.mock('@ionic/vue', () => ({
  alertController: {
    create: async (opts: { header: string; message: string }) => {
      calls.push('confirm');
      sheet.header = opts.header;
      sheet.message = opts.message;
      return {
        present: async () => {},
        onDidDismiss: async () => ({ role: (await confirmSpy()) ? 'confirm' : 'cancel' }),
      };
    },
  },
}));

const sheet = { header: '', message: '' };

import { ANDROID_LOCAL_NETWORK_PERMISSION, LOCAL_NETWORK_PERMISSION_DENIED } from '@erplora/module-sdk';

import { i18n } from '../i18n';
import en from '../i18n/locales/en';
import { makeBridgeTransport } from './bridge-transport';
import { LOCAL_NETWORK_PRIMER_ANSWERED_KEY } from './local-network-permission';
import { printerDiscoveryMessage } from './printer-discovery';

/** The permission map the plugin reports, and what the scan comes back with. */
const device = {
  granted: false,
  grantedAfterAsking: true,
  scan: { status: 'scanned', printers: [] } as unknown,
};

beforeEach(() => {
  calls.length = 0;
  lanAsks.length = 0;
  // The sheet comes out in the hub's active language; the suite reads the English source.
  i18n.global.locale.value = 'en';
  tauriMode.value = true;
  device.granted = false;
  device.grantedAfterAsking = true;
  device.scan = { status: 'scanned', printers: [] };
  confirmSpy.mockImplementation(async () => true);
  localStorage.removeItem(LOCAL_NETWORK_PRIMER_ANSWERED_KEY);
  invokeSpy.mockReset();
  invokeSpy.mockImplementation(async (cmd: string, args?: Record<string, unknown>) => {
    calls.push(cmd);
    if (cmd === 'plugin:erplora-android|check_permissions') {
      return { [ANDROID_LOCAL_NETWORK_PERMISSION]: device.granted };
    }
    if (cmd === 'plugin:erplora-android|request_permissions') {
      const asked = ((args?.permissions as string[]) ?? []).slice();
      if (asked.includes(ANDROID_LOCAL_NETWORK_PERMISSION)) {
        lanAsks.push(asked);
        device.granted = device.grantedAfterAsking;
      }
      return { [ANDROID_LOCAL_NETWORK_PERMISSION]: device.granted };
    }
    if (cmd === 'erplora_discover_printers') return device.scan;
    return {};
  });
});

describe('«find my printer» explains itself before Android asks (hub#1773)', () => {
  it('our sheet goes up BEFORE the system dialog', async () => {
    await makeBridgeTransport().discoverPrinters();

    const confirmAt = calls.indexOf('confirm');
    const requestAt = calls.indexOf('plugin:erplora-android|request_permissions');
    expect(confirmAt, 'the in-app explanation never went up').toBeGreaterThanOrEqual(0);
    expect(requestAt, 'Android was never asked').toBeGreaterThanOrEqual(0);
    expect(confirmAt).toBeLessThan(requestAt);
  });

  it('and it explains it in the words of the hub, not Android’s', async () => {
    await makeBridgeTransport().discoverPrinters();

    expect(sheet.header).toBe(en.hardware.localNetwork.primerHeader);
    expect(sheet.message).toBe(en.hardware.localNetwork.primerMessage);
    // Not the notices sheet: this one is about finding a printer.
    expect(sheet.message).not.toBe(en.system.notices.primerMessage);
  });

  it('a «not now» keeps Android out of it — and the scan still runs', async () => {
    // A refusal to OUR sheet costs nothing and is reversible. A refusal to Android's is not, so it
    // is never provoked. And the scan goes ahead either way: the answer the screen needs — blocked
    // or empty — comes from running it, not from skipping it.
    confirmSpy.mockImplementation(async () => false);

    await expect(makeBridgeTransport().discoverPrinters()).resolves.toEqual([]);

    expect(lanAsks, 'Android was asked for the local network anyway').toEqual([]);
    expect(calls).toContain('erplora_discover_printers');
  });

  it('asks once: a second scan does not put the sheet up again', async () => {
    confirmSpy.mockImplementation(async () => false);
    await makeBridgeTransport().discoverPrinters();
    calls.length = 0;

    await makeBridgeTransport().discoverPrinters();

    expect(calls).not.toContain('confirm');
    expect(calls).toContain('erplora_discover_printers');
  });

  it('never bothers a device that already has the permission', async () => {
    device.granted = true;

    await makeBridgeTransport().discoverPrinters();

    expect(calls).not.toContain('confirm');
  });

  it('never bothers a platform without the permission (desktop app)', async () => {
    invokeSpy.mockImplementation(async (cmd: string) => {
      calls.push(cmd);
      // The desktop shell answers the plugin call with an empty map: there is no such permission.
      if (cmd === 'plugin:erplora-android|check_permissions') return {};
      if (cmd === 'erplora_discover_printers') return device.scan;
      return {};
    });

    await makeBridgeTransport().discoverPrinters();

    expect(calls).not.toContain('confirm');
    expect(lanAsks).toEqual([]);
  });

  it('a browser has no hardware and no permission to ask for: no sheet, no plugin call', async () => {
    tauriMode.value = false;

    await expect(makeBridgeTransport().discoverPrinters()).rejects.toThrow();

    expect(calls).toEqual([]);
  });

  it('a sheet that blows up cannot take the scan down with it', async () => {
    // The till has to keep selling. Whatever happens around the permission, the scan runs and its
    // own answer reaches the screen.
    confirmSpy.mockImplementation(async () => {
      throw new Error('no window');
    });

    await expect(makeBridgeTransport().discoverPrinters()).resolves.toEqual([]);
  });

  it('still says WHY when the scan comes back blocked (hub#338 keeps working)', async () => {
    // The primer sits in front of the scan; it must not swallow the outcome behind it. A blocked
    // scan still rejects with the sentence a person can act on, in the language of the hub.
    device.grantedAfterAsking = false;
    device.scan = {
      status: LOCAL_NETWORK_PERMISSION_DENIED,
      permission: ANDROID_LOCAL_NETWORK_PERMISSION,
    };

    await expect(makeBridgeTransport().discoverPrinters()).rejects.toThrow(
      printerDiscoveryMessage('permission_denied'),
    );
    expect(i18n.global.locale.value).toBeTruthy();
  });
});
