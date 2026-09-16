// @vitest-environment happy-dom
// hub#1773 — the local-network permission, asked ONCE, IN CONTEXT, with a sentence of our own first.
//
// `ACCESS_LOCAL_NETWORK` (API 37+) is what stands between the till and every printer on the venue's
// network, and until now the only thing that ever asked for it was `ensurePermissions()` inside the
// transport — one `request_permissions` call, cold, with nothing in front of it. What Android then
// shows says the app wants to «find, connect to and determine the relative position of nearby
// devices», which reads like tracking and gets refused; and a refusal is close to permanent,
// because after two the system stops presenting the dialog at all.
//
// Three things are pinned here, the same three hub#1732 pinned for the notices — they are the three
// ways this goes wrong:
//
//  1. **Our sentence comes first.** The refusal that costs nothing is the one to OUR sheet; the one
//     to Android's is nearly irreversible.
//  2. **It is asked once.** «Not now» is an answer. Re-asking on every scan is the nagging Android's
//     own guidance exists to prevent, and it burns the two chances the system gives us.
//  3. **A «no» never breaks the flow.** The till has to keep selling with no printer, so nothing
//     here propagates and nothing here blocks.
import { afterEach, describe, expect, it } from 'vitest';

import { ANDROID_LOCAL_NETWORK_PERMISSION } from '@erplora/module-sdk';

import en from '../i18n/locales/en';
import es from '../i18n/locales/es';
import {
  LOCAL_NETWORK_COPY_KEYS,
  LOCAL_NETWORK_PRIMER_ANSWERED_KEY,
  ensureLocalNetworkPermission,
  localNetworkPermission,
  localNetworkPermissionState,
  localNetworkPrimerLabelsFrom,
} from './local-network-permission';
import type { PermissionPrimerLabels } from './device-permission';
import {
  ANDROID_NOTIFICATIONS_PERMISSION,
  NOTIFICATION_PRIMER_ANSWERED_KEY,
  ensureNotificationPermission,
} from './notification-permission';

const LABELS: PermissionPrimerLabels = {
  header: 'Let ERPlora look for your printer',
  message: 'to find it we have to look at the devices on your network',
  later: 'Not now',
  allow: 'Look for it',
};

/** A recorder for everything the primer did, plus the seams it does it through. */
function harness(
  options: {
    status?: Record<string, boolean> | null;
    afterRequest?: Record<string, boolean> | null;
    answered?: boolean;
    accept?: boolean;
    requestThrows?: boolean;
    checkThrows?: boolean;
    force?: boolean;
  } = {},
) {
  const calls: string[] = [];
  let answered = options.answered ?? false;
  return {
    calls,
    isAnswered: () => answered,
    deps: {
      labels: LABELS,
      force: options.force,
      check: async () => {
        calls.push('check');
        if (options.checkThrows) throw new Error('no shell');
        return options.status === undefined
          ? { [ANDROID_LOCAL_NETWORK_PERMISSION]: false }
          : options.status;
      },
      request: async () => {
        calls.push('request');
        if (options.requestThrows) throw new Error('denied');
        return options.afterRequest === undefined
          ? { [ANDROID_LOCAL_NETWORK_PERMISSION]: true }
          : options.afterRequest;
      },
      confirm: async () => {
        calls.push('confirm');
        return options.accept ?? true;
      },
      readAnswered: () => answered,
      writeAnswered: () => {
        calls.push('remember');
        answered = true;
      },
    },
  };
}

afterEach(() => {
  try {
    localStorage.removeItem(LOCAL_NETWORK_PRIMER_ANSWERED_KEY);
  } catch {
    // a storage that refuses to be cleaned cannot fail a test about permissions
  }
});

describe('what this device can do about the local network', () => {
  it('an ABSENT key is `unsupported`, never `denied`', () => {
    // The plugin reports only the permissions THIS Android knows, and on desktop the whole map is
    // empty. Reading the absence as a refusal would claim the printer search is blocked on a Mac
    // that finds printers fine — a false alarm about something that works.
    expect(localNetworkPermission({})).toBe('unsupported');
    expect(localNetworkPermission(null)).toBe('unsupported');
    expect(localNetworkPermission(undefined)).toBe('unsupported');
    expect(localNetworkPermission({ 'android.permission.POST_NOTIFICATIONS': true })).toBe(
      'unsupported',
    );
  });

  it('reads the real answer when the key IS there', () => {
    expect(localNetworkPermission({ [ANDROID_LOCAL_NETWORK_PERMISSION]: true })).toBe('granted');
    expect(localNetworkPermission({ [ANDROID_LOCAL_NETWORK_PERMISSION]: false })).toBe('denied');
  });

  it('`localNetworkPermissionState` answers `unsupported` when it cannot even ask', async () => {
    // Whoever consumes this paints a state. A rejection would take the screen down instead of
    // filling in a status, so a plugin that cannot answer is «we do not know», not «blocked».
    await expect(
      localNetworkPermissionState(async () => {
        throw new Error('no shell');
      }),
    ).resolves.toBe('unsupported');
  });
});

describe('the primer: our sentence, then the system dialog', () => {
  it('shows OUR sheet BEFORE Android is ever asked', async () => {
    const h = harness();

    await expect(ensureLocalNetworkPermission(h.deps)).resolves.toBe('granted');

    // The order is the whole fix: `request` after `confirm`, never before it.
    expect(h.calls).toEqual(['check', 'confirm', 'remember', 'request']);
  });

  it('a «not now» keeps Android OUT of it — the refusal that costs nothing', async () => {
    const h = harness({ accept: false });

    await expect(ensureLocalNetworkPermission(h.deps)).resolves.toBe('denied');

    expect(h.calls).not.toContain('request');
    // Answered all the same: «not now» is an answer, and the way back is the screen.
    expect(h.isAnswered()).toBe(true);
  });

  it('remembers BEFORE opening the system dialog', async () => {
    // Load-bearing order: a reload while Android's dialog is up would otherwise come back and ask
    // again, spending the second and last chance the system gives us.
    const h = harness();
    await ensureLocalNetworkPermission(h.deps);
    expect(h.calls.indexOf('remember')).toBeLessThan(h.calls.indexOf('request'));
  });

  it('asks ONCE: a device that already answered is never bothered again', async () => {
    const h = harness({ answered: true });

    await expect(ensureLocalNetworkPermission(h.deps)).resolves.toBe('denied');

    expect(h.calls).toEqual(['check']);
  });

  it('`force` is the way back — the screen asking on the user’s behalf', async () => {
    const h = harness({ answered: true, force: true });

    await expect(ensureLocalNetworkPermission(h.deps)).resolves.toBe('granted');

    expect(h.calls).toEqual(['check', 'confirm', 'remember', 'request']);
  });

  it('never bothers a device that already has the permission', async () => {
    const h = harness({ status: { [ANDROID_LOCAL_NETWORK_PERMISSION]: true } });

    await expect(ensureLocalNetworkPermission(h.deps)).resolves.toBe('granted');

    expect(h.calls).toEqual(['check']);
  });

  it('never bothers a platform that has no such permission (desktop, browser, old Android)', async () => {
    const h = harness({ status: {} });

    await expect(ensureLocalNetworkPermission(h.deps)).resolves.toBe('unsupported');

    expect(h.calls).toEqual(['check']);
  });

  it('cannot read the state → `unsupported`, and nothing is asked', async () => {
    const h = harness({ checkThrows: true });

    await expect(ensureLocalNetworkPermission(h.deps)).resolves.toBe('unsupported');

    expect(h.calls).toEqual(['check']);
  });

  it('a request that blows up never propagates: the till keeps selling', async () => {
    const h = harness({ requestThrows: true });

    await expect(ensureLocalNetworkPermission(h.deps)).resolves.toBe('denied');
  });

  it('`force` cannot re-open the sheet on a device that is already granted', async () => {
    const h = harness({ status: { [ANDROID_LOCAL_NETWORK_PERMISSION]: true }, force: true });

    await expect(ensureLocalNetworkPermission(h.deps)).resolves.toBe('granted');

    expect(h.calls).toEqual(['check']);
  });
});

describe('the copy', () => {
  it('every key of the sheet and of the blocked row resolves in `en` AND in `es`', () => {
    // A renamed key ships as raw `hardware.localNetwork.primerHeader` text inside the dialog,
    // which is exactly what nobody sees until a customer does.
    const read = (bundle: unknown, key: string): unknown =>
      key.split('.').reduce<unknown>((o, k) => (o as Record<string, unknown> | undefined)?.[k], bundle);

    for (const key of LOCAL_NETWORK_COPY_KEYS) {
      expect(typeof read(en, key), `${key} missing in en`).toBe('string');
      expect(typeof read(es, key), `${key} missing in es`).toBe('string');
      expect((read(es, key) as string).length, `${key} empty in es`).toBeGreaterThan(0);
    }
  });

  it('binds the four strings of the sheet through the caller’s `t` (ADR-0055)', () => {
    const labels = localNetworkPrimerLabelsFrom((key) => `t:${key}`);
    expect(labels).toEqual({
      header: 't:hardware.localNetwork.primerHeader',
      message: 't:hardware.localNetwork.primerMessage',
      later: 't:hardware.localNetwork.primerLater',
      allow: 't:hardware.localNetwork.primerAllow',
    });
  });

  it('the sheet does NOT reuse the notices copy: they ask for different things', () => {
    expect(en.hardware.localNetwork.primerMessage).not.toBe(en.system.notices.primerMessage);
    expect(es.hardware.localNetwork.primerMessage).not.toBe(es.system.notices.primerMessage);
  });
});

describe('its memory is its OWN — the notices sheet cannot answer for it', () => {
  // Through the two PRODUCTION wrappers and the real storage, with nothing about memory injected:
  // this pins the wiring, not the core (`device-permission.test.ts` already pins the core honours
  // whatever key it is handed). A shared key would mean: «Not now» to the notices sheet during
  // setup, and the printer sheet never appears again for the life of the install — the dialog
  // goes back to popping cold, which is the whole of hub#1773 undone and invisible.
  afterEach(() => {
    localStorage.removeItem(NOTIFICATION_PRIMER_ANSWERED_KEY);
  });

  it('the two keys are two', () => {
    expect(LOCAL_NETWORK_PRIMER_ANSWERED_KEY).not.toBe(NOTIFICATION_PRIMER_ANSWERED_KEY);
  });

  it('«not now» to the notices sheet leaves the printer sheet still to come', async () => {
    const sheets: string[] = [];
    const denied = {
      [ANDROID_NOTIFICATIONS_PERMISSION]: false,
      [ANDROID_LOCAL_NETWORK_PERMISSION]: false,
    };

    await ensureNotificationPermission({
      labels: LABELS,
      check: async () => denied,
      request: async () => denied,
      confirm: async () => {
        sheets.push('notices');
        return false;
      },
    });
    await ensureLocalNetworkPermission({
      labels: LABELS,
      check: async () => denied,
      request: async () => denied,
      confirm: async () => {
        sheets.push('printer');
        return false;
      },
    });

    expect(sheets).toEqual(['notices', 'printer']);
    // And each answer landed in ITS key.
    expect(localStorage.getItem(NOTIFICATION_PRIMER_ANSWERED_KEY)).toBe('1');
    expect(localStorage.getItem(LOCAL_NETWORK_PRIMER_ANSWERED_KEY)).toBe('1');
  });
});
