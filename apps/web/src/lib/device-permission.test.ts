// @vitest-environment happy-dom
// hub#1773 — the ONE primer, shared by the two runtime permissions this app asks for.
//
// `POST_NOTIFICATIONS` (hub#1732) and `ACCESS_LOCAL_NETWORK` (hub#1773) need exactly the same
// dance — read the real state, explain ourselves, then let Android ask, once — so it lives here
// once instead of being copied. What this file pins is what the sharing must NOT break:
//
//  1. each permission keeps its OWN memory: answering the notices sheet cannot silence the printer
//     sheet for the life of the install, which is what a single storage key would do;
//  2. each permission reads its OWN key out of the plugin's map, so one being off never claims the
//     other is;
//  3. an absent key is `unsupported` — the reading that keeps a false alarm off a desktop.
import { afterEach, describe, expect, it } from 'vitest';

import {
  ensureDevicePermission,
  permissionStateOf,
  shouldRunPrimer,
  type PermissionPrimerLabels,
} from './device-permission';

const LABELS: PermissionPrimerLabels = { header: 'h', message: 'm', later: 'l', allow: 'a' };

const NOTICES = 'android.permission.POST_NOTIFICATIONS';
const LAN = 'android.permission.ACCESS_LOCAL_NETWORK';

describe('permissionStateOf: the plugin map, read honestly', () => {
  it('an absent key is `unsupported`, a present one is what it says', () => {
    expect(permissionStateOf(null, LAN)).toBe('unsupported');
    expect(permissionStateOf({}, LAN)).toBe('unsupported');
    expect(permissionStateOf({ [NOTICES]: false }, LAN)).toBe('unsupported');
    expect(permissionStateOf({ [LAN]: false }, LAN)).toBe('denied');
    expect(permissionStateOf({ [LAN]: true }, LAN)).toBe('granted');
  });
});

describe('shouldRunPrimer: once, and only where there is something to ask for', () => {
  it('only a real refusal opens the sheet', () => {
    expect(shouldRunPrimer({ permission: 'granted', alreadyAnswered: false })).toBe(false);
    expect(shouldRunPrimer({ permission: 'unsupported', alreadyAnswered: false })).toBe(false);
    expect(shouldRunPrimer({ permission: 'denied', alreadyAnswered: false })).toBe(true);
  });

  it('an answer is an answer — `force` is the only way back', () => {
    expect(shouldRunPrimer({ permission: 'denied', alreadyAnswered: true })).toBe(false);
    expect(shouldRunPrimer({ permission: 'denied', alreadyAnswered: true, force: true })).toBe(true);
    // Not even `force` may nag a device that has nothing to grant.
    expect(shouldRunPrimer({ permission: 'granted', alreadyAnswered: true, force: true })).toBe(false);
  });
});

describe('the two permissions do not answer for each other', () => {
  /** A device where the notices were refused long ago and the LAN has never been asked about. */
  function device() {
    const memory = new Set<string>(['erplora.notifications.primerAnswered']);
    const asked: string[] = [];
    return {
      asked,
      memory,
      deps: (permission: string, storageKey: string) => ({
        permission,
        storageKey,
        labels: LABELS,
        tag: 'test',
        check: async () => ({ [NOTICES]: false, [LAN]: false }),
        request: async () => {
          asked.push(permission);
          return { [NOTICES]: false, [LAN]: false };
        },
        confirm: async () => true,
        readAnswered: () => memory.has(storageKey),
        writeAnswered: () => memory.add(storageKey),
      }),
    };
  }

  it('the notices being already answered does NOT silence the local-network sheet', async () => {
    const d = device();

    await ensureDevicePermission(d.deps(NOTICES, 'erplora.notifications.primerAnswered'));
    await ensureDevicePermission(d.deps(LAN, 'erplora.localNetwork.primerAnswered'));

    // Only the LAN one reached Android: the notices one had already been answered.
    expect(d.asked).toEqual([LAN]);
  });

  it('and answering the local-network sheet remembers only ITS own answer', async () => {
    const d = device();
    d.memory.clear();

    await ensureDevicePermission(d.deps(LAN, 'erplora.localNetwork.primerAnswered'));

    expect([...d.memory]).toEqual(['erplora.localNetwork.primerAnswered']);
  });
});

describe('the memory the callers do NOT inject — the real one, in storage', () => {
  const NOTICES_KEY = 'erplora.notifications.primerAnswered';
  const LAN_KEY = 'erplora.localNetwork.primerAnswered';

  afterEach(() => {
    localStorage.removeItem(NOTICES_KEY);
    localStorage.removeItem(LAN_KEY);
  });

  /** The same deps the shell uses in production: only the device and the sheet are replaced. */
  function realMemory(permission: string, storageKey: string, asked: string[]) {
    return {
      permission,
      storageKey,
      labels: LABELS,
      tag: 'test',
      check: async () => ({ [NOTICES]: false, [LAN]: false }),
      request: async () => {
        asked.push(permission);
        return { [NOTICES]: false, [LAN]: false };
      },
      confirm: async () => true,
    };
  }

  it('each permission writes ITS OWN key, so one answer cannot silence the other', async () => {
    // A single shared key would mean: the owner taps «Not now» on the notices sheet during setup,
    // and the printer sheet never appears again for the life of the install — the dialog goes
    // back to popping cold, which is the whole of hub#1773 undone and invisible.
    const asked: string[] = [];

    await ensureDevicePermission(realMemory(NOTICES, NOTICES_KEY, asked));
    await ensureDevicePermission(realMemory(LAN, LAN_KEY, asked));

    expect(localStorage.getItem(NOTICES_KEY)).toBe('1');
    expect(localStorage.getItem(LAN_KEY)).toBe('1');
    // Both were put in front of the user: neither answered for the other.
    expect(asked).toEqual([NOTICES, LAN]);
  });

  it('and an answer already in storage keeps that ONE quiet, on its own', async () => {
    localStorage.setItem(NOTICES_KEY, '1');
    const asked: string[] = [];

    await ensureDevicePermission(realMemory(NOTICES, NOTICES_KEY, asked));
    await ensureDevicePermission(realMemory(LAN, LAN_KEY, asked));

    expect(asked).toEqual([LAN]);
  });
});

describe('two askers at once get ONE sheet (hub#2306 review)', () => {
  // A device booting with a session already open and a printer: the print-host alta and the
  // sign-in ask both reach the primer before anybody has answered. Two stacked sheets would ask
  // twice and could spend Android's second (and last) system dialog.
  function slowDevice() {
    const memory = new Set<string>();
    const open: ((yes: boolean) => void)[] = [];
    let sheets = 0;
    let requests = 0;
    const deps = {
      permission: NOTICES,
      storageKey: 'erplora.notifications.primerAnswered',
      tag: 'test',
      labels: LABELS,
      check: async () => ({ [NOTICES]: false }),
      request: async () => {
        requests += 1;
        return { [NOTICES]: true };
      },
      confirm: () => {
        sheets += 1;
        return new Promise<boolean>((resolve) => void open.push(resolve));
      },
      readAnswered: () => memory.has('erplora.notifications.primerAnswered'),
      writeAnswered: () => void memory.add('erplora.notifications.primerAnswered'),
    };
    return {
      deps,
      answer: (yes: boolean) => open.splice(0).forEach((resolve) => resolve(yes)),
      sheets: () => sheets,
      requests: () => requests,
    };
  }

  it('a second ask while the sheet is up joins it instead of stacking another', async () => {
    const d = slowDevice();
    const first = ensureDevicePermission(d.deps);
    const second = ensureDevicePermission(d.deps);
    await new Promise((r) => setTimeout(r, 0));
    d.answer(true);
    await expect(Promise.all([first, second])).resolves.toEqual(['granted', 'granted']);
    expect(d.sheets()).toBe(1);
    expect(d.requests()).toBe(1);
  });

  it('once it is answered, the next ask is a fresh one (nothing stays pinned)', async () => {
    const d = slowDevice();
    const first = ensureDevicePermission(d.deps);
    await new Promise((r) => setTimeout(r, 0));
    d.answer(false);
    await expect(first).resolves.toBe('denied');
    // Answered → no sheet, but the state is read again (not the old promise).
    await expect(ensureDevicePermission({ ...d.deps, check: async () => ({ [NOTICES]: true }) })).resolves.toBe(
      'granted',
    );
    expect(d.sheets()).toBe(1);
  });
});
