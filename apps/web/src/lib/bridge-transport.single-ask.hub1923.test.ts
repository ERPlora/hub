// @vitest-environment happy-dom
// hub#1923 — **Android asked the same question twice, and our sheet came back after «not now».**
//
// On Android 17 the printer search needs two runtime permissions (ADR-0204): the local network and
// bonded Bluetooth. Both belong to the «nearby devices» group, so the system words them the same.
// The adapter took the local network out of the batch to put our explanation in front of it
// (hub#1773) and then asked for Bluetooth in a SECOND call: two identical dialogs back to back, and
// two «no» answers burn the install's last chances for good (`USER_FIXED`).
//
// And the Printing screen fires several searches at once (auto-scan on open + the button). Each
// read «already answered?» before the first one wrote it, so a second sheet stacked under the
// first — the «not now» that did not close on the first tap.
//
// What this pins, through the real transport, primer and i18n: one sheet, then ONE system ask
// carrying the whole batch; a «no» (ours or Android's) is respected by every search that follows.
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { invokeSpy, calls, asks, confirmSpy } = vi.hoisted(() => ({
  calls: [] as string[],
  /** Every `request_permissions` that reached Android, with what it carried. */
  asks: [] as string[][],
  invokeSpy: vi.fn<(cmd: string, args?: Record<string, unknown>) => Promise<unknown>>(),
  confirmSpy: vi.fn<() => Promise<boolean>>(async () => true),
}));

vi.mock('./device', () => ({
  isTauri: () => true,
  invokeTauri: invokeSpy,
}));

// Only the presentation of the `ion-alert` is replaced; when it goes up is the real code.
vi.mock('@ionic/vue', () => ({
  alertController: {
    create: async () => {
      calls.push('confirm');
      return {
        present: async () => {},
        onDidDismiss: async () => ({ role: (await confirmSpy()) ? 'confirm' : 'cancel' }),
      };
    },
  },
}));

import {
  ANDROID_BLUETOOTH_CONNECT_PERMISSION,
  ANDROID_LOCAL_NETWORK_PERMISSION,
} from '@erplora/module-sdk';

import { i18n } from '../i18n';
import { makeBridgeTransport } from './bridge-transport';
import { LOCAL_NETWORK_PRIMER_ANSWERED_KEY } from './local-network-permission';

const LAN = ANDROID_LOCAL_NETWORK_PERMISSION;
const BT = ANDROID_BLUETOOTH_CONNECT_PERMISSION;

/** What this Android knows and has granted. A key that is absent does not exist on this API. */
let granted: Record<string, boolean>;
/** What the user answers in Android's dialog. */
let systemSaysYes: boolean;

beforeEach(() => {
  calls.length = 0;
  asks.length = 0;
  i18n.global.locale.value = 'en';
  granted = { [LAN]: false, [BT]: false };
  systemSaysYes = false;
  confirmSpy.mockImplementation(async () => true);
  localStorage.removeItem(LOCAL_NETWORK_PRIMER_ANSWERED_KEY);
  invokeSpy.mockReset();
  invokeSpy.mockImplementation(async (cmd: string, args?: Record<string, unknown>) => {
    calls.push(cmd);
    if (cmd === 'plugin:erplora-android|check_permissions') return { ...granted };
    if (cmd === 'plugin:erplora-android|request_permissions') {
      const asked = ((args?.permissions as string[]) ?? []).slice();
      asks.push(asked);
      for (const p of asked) if (p in granted) granted[p] = systemSaysYes;
      return { ...granted };
    }
    if (cmd === 'erplora_discover_printers') return { status: 'scanned', printers: [] };
    return {};
  });
});

describe('one search, one question (hub#1923)', () => {
  it('after our sheet, Android is asked ONCE for the whole batch — not twice', async () => {
    await makeBridgeTransport().discoverPrinters();

    expect(calls.filter((c) => c === 'confirm')).toHaveLength(1);
    expect(asks, 'Android was asked in more than one dialog').toHaveLength(1);
    expect([...asks[0]].sort()).toEqual([BT, LAN].sort());
  });

  it('and when the owner allows it, it is still that one dialog — nothing behind it', async () => {
    systemSaysYes = true;

    await makeBridgeTransport().discoverPrinters();

    expect(asks, 'a second dialog followed the one the owner accepted').toHaveLength(1);
  });

  it('a «not now» to our sheet keeps Android out of it for Bluetooth too', async () => {
    confirmSpy.mockImplementation(async () => false);

    await expect(makeBridgeTransport().discoverPrinters()).resolves.toEqual([]);

    expect(asks, 'Bluetooth was asked cold right after the user said no').toEqual([]);
    expect(calls).toContain('erplora_discover_printers');
  });

  it('a «no» in Android’s dialog is respected: the next search asks nothing', async () => {
    systemSaysYes = false;
    await makeBridgeTransport().discoverPrinters();
    asks.length = 0;
    calls.length = 0;

    await makeBridgeTransport().discoverPrinters();

    expect(calls).not.toContain('confirm');
    expect(asks, 'the refused dialog came back on the next search').toEqual([]);
  });

  it('searches fired at the same time share ONE sheet and ONE system ask', async () => {
    // The screen scans on open and the owner taps «Find my printer» a moment later. The sheet
    // stays up for a while before the «not now» lands, which is when the second search arrives.
    confirmSpy.mockImplementation(() => new Promise<boolean>((r) => setTimeout(() => r(false), 20)));
    const t = makeBridgeTransport();

    await Promise.all([
      t.discoverPrinters(),
      t.discoverPrinters(),
      makeBridgeTransport().discoverPrinters(),
    ]);

    expect(calls.filter((c) => c === 'confirm'), 'the sheet stacked on itself').toHaveLength(1);
    expect(asks).toEqual([]);
  });

  it('once granted, a later search asks nothing at all', async () => {
    systemSaysYes = true;
    await makeBridgeTransport().discoverPrinters();
    asks.length = 0;
    calls.length = 0;

    await makeBridgeTransport().discoverPrinters();

    expect(calls).not.toContain('confirm');
    expect(asks).toEqual([]);
  });

  it('an Android without the local-network permission still asks for Bluetooth, no sheet', async () => {
    // API 31-36: the LAN is open, only Bluetooth is a runtime permission. Unchanged by hub#1923.
    granted = { [BT]: false };

    await makeBridgeTransport().discoverPrinters();

    expect(calls).not.toContain('confirm');
    expect(asks).toEqual([[BT]]);
  });
});
