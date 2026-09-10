// hub#1732 — the notification permission, asked ONCE, IN CONTEXT, with a sentence of our own first.
//
// Three things are pinned here, and each one is a way this went wrong before:
//
//  1. **It gets asked at all.** The plugin has been able to ask since hub#758; the only caller was
//     `peripherals.notify()`, so a device that never received a kitchen order was never asked and
//     `dumpsys` reported the permission with no `USER_SET` flag for the life of the install.
//  2. **Our sentence comes first.** Android's own dialog says nothing about what the app wants the
//     notices for. Asked cold it reads as opportunistic and gets denied, and a denial is close to
//     permanent: the system stops showing the dialog after two.
//  3. **It is asked once.** An answer — «not now» included — is an answer. Re-asking on every
//     heartbeat is the nagging Android's guidance exists to prevent; the way back is the screen,
//     which offers it again on purpose.
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import en from '../i18n/locales/en';
import es from '../i18n/locales/es';
import {
  ANDROID_NOTIFICATIONS_PERMISSION,
  NOTIFICATION_PRIMER_ANSWERED_KEY,
  NOTICE_COPY_KEYS,
  ensureNotificationPermission,
  notificationPermission,
  primerLabelsFrom,
  shouldRunPrimer,
  shouldSendNotice,
  type NotificationPrimerLabels,
} from './notification-permission';

const LABELS: NotificationPrimerLabels = {
  header: 'Let ERPlora warn you',
  message: 'so a new order does not sit in the kitchen unnoticed',
  later: 'Not now',
  allow: 'Turn on',
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
  } = {},
) {
  const calls: string[] = [];
  let answered = options.answered ?? false;
  return {
    calls,
    isAnswered: () => answered,
    deps: {
      labels: LABELS,
      check: async () => {
        calls.push('check');
        if (options.checkThrows) throw new Error('no shell');
        return options.status === undefined ? { [ANDROID_NOTIFICATIONS_PERMISSION]: false } : options.status;
      },
      request: async () => {
        calls.push('request');
        if (options.requestThrows) throw new Error('denied');
        return options.afterRequest === undefined
          ? { [ANDROID_NOTIFICATIONS_PERMISSION]: true }
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

describe('notificationPermission — what the plugin status map says', () => {
  it('reads a granted permission', () => {
    expect(notificationPermission({ [ANDROID_NOTIFICATIONS_PERMISSION]: true })).toBe('granted');
  });

  it('reads a permission that is not granted', () => {
    expect(notificationPermission({ [ANDROID_NOTIFICATIONS_PERMISSION]: false })).toBe('denied');
  });

  it('is `unsupported` when the key is absent — the plugin only reports what this Android knows', () => {
    // Android 12 and below grant notifications at install: `PermissionPolicy.required()` leaves
    // the key out, and claiming «denied» there would paint a blocked warning on a device that
    // notifies perfectly.
    expect(notificationPermission({ 'android.permission.ACCESS_LOCAL_NETWORK': false })).toBe(
      'unsupported',
    );
  });

  it('is `unsupported` with no shell at all — a browser or the desktop app', () => {
    expect(notificationPermission(null)).toBe('unsupported');
    expect(notificationPermission({})).toBe('unsupported');
  });
});

describe('shouldRunPrimer — pure decision', () => {
  it('asks when the permission is missing and nobody answered yet', () => {
    expect(shouldRunPrimer({ permission: 'denied', alreadyAnswered: false })).toBe(true);
  });

  it('does not ask twice', () => {
    expect(shouldRunPrimer({ permission: 'denied', alreadyAnswered: false, force: false })).toBe(true);
    expect(shouldRunPrimer({ permission: 'denied', alreadyAnswered: true })).toBe(false);
  });

  it('does not ask for what is already granted, nor on a platform without the permission', () => {
    expect(shouldRunPrimer({ permission: 'granted', alreadyAnswered: false })).toBe(false);
    expect(shouldRunPrimer({ permission: 'unsupported', alreadyAnswered: false })).toBe(false);
  });

  it('asks again when the SCREEN asks it to, which is the way back from a «no»', () => {
    expect(shouldRunPrimer({ permission: 'denied', alreadyAnswered: true, force: true })).toBe(true);
    // Not even forced does it bother a device that is already notifying.
    expect(shouldRunPrimer({ permission: 'granted', alreadyAnswered: true, force: true })).toBe(false);
  });
});

describe('ensureNotificationPermission', () => {
  it('explains first and only then hands over to the system dialog', async () => {
    const h = harness();
    await expect(ensureNotificationPermission(h.deps)).resolves.toBe('granted');
    expect(h.calls).toEqual(['check', 'confirm', 'remember', 'request']);
  });

  it('«not now» is an answer: no system dialog, and no second ask', async () => {
    const h = harness({ accept: false });
    await expect(ensureNotificationPermission(h.deps)).resolves.toBe('denied');
    expect(h.calls).toEqual(['check', 'confirm', 'remember']);
    expect(h.isAnswered()).toBe(true);
  });

  it('remembers the answer BEFORE the dialog, so a reload mid-dialog cannot re-ask', async () => {
    const h = harness();
    await ensureNotificationPermission(h.deps);
    expect(h.calls.indexOf('remember')).toBeLessThan(h.calls.indexOf('request'));
  });

  it('says nothing at all once the answer is on record', async () => {
    const h = harness({ answered: true });
    await expect(ensureNotificationPermission(h.deps)).resolves.toBe('denied');
    expect(h.calls).toEqual(['check']);
  });

  it('says nothing when the permission is already granted', async () => {
    const h = harness({ status: { [ANDROID_NOTIFICATIONS_PERMISSION]: true } });
    await expect(ensureNotificationPermission(h.deps)).resolves.toBe('granted');
    expect(h.calls).toEqual(['check']);
  });

  it('says nothing on the desktop app or in a browser', async () => {
    const h = harness({ status: {} });
    await expect(ensureNotificationPermission(h.deps)).resolves.toBe('unsupported');
    expect(h.calls).toEqual(['check']);
  });

  it('re-asks when forced, which is what the screen offers after a «no»', async () => {
    const h = harness({ answered: true });
    await expect(ensureNotificationPermission({ ...h.deps, force: true })).resolves.toBe('granted');
    expect(h.calls).toEqual(['check', 'confirm', 'remember', 'request']);
  });

  it('reports the state the system answered with, not the one we hoped for', async () => {
    const h = harness({ afterRequest: { [ANDROID_NOTIFICATIONS_PERMISSION]: false } });
    await expect(ensureNotificationPermission(h.deps)).resolves.toBe('denied');
  });

  it('never propagates: a permission is not worth breaking the boot that asked for it', async () => {
    const thrown = harness({ requestThrows: true });
    await expect(ensureNotificationPermission(thrown.deps)).resolves.toBe('denied');

    const blind = harness({ checkThrows: true });
    await expect(ensureNotificationPermission(blind.deps)).resolves.toBe('unsupported');
    expect(blind.calls).toEqual(['check']);
  });
});

describe('the storage key', () => {
  // A Map-backed `localStorage`, because the default environment of this suite is `node`. It is
  // the same contract the WebView gives us, and what is under test is that the DEFAULT seams
  // (the ones production uses) read and write the namespaced key — not jsdom.
  beforeEach(() => {
    const store = new Map<string, string>();
    (globalThis as { localStorage?: unknown }).localStorage = {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => void store.set(k, v),
      removeItem: (k: string) => void store.delete(k),
      clear: () => store.clear(),
      key: (i: number) => [...store.keys()][i] ?? null,
      get length() {
        return store.size;
      },
    };
  });

  afterEach(() => {
    delete (globalThis as { localStorage?: unknown }).localStorage;
  });

  it('is namespaced, and the default seams read and write it', async () => {
    expect(NOTIFICATION_PRIMER_ANSWERED_KEY.startsWith('erplora.')).toBe(true);
    const h = harness();
    await ensureNotificationPermission({
      labels: h.deps.labels,
      check: h.deps.check,
      request: h.deps.request,
      confirm: h.deps.confirm,
    });
    expect(localStorage.getItem(NOTIFICATION_PRIMER_ANSWERED_KEY)).toBe('1');
  });
});

describe('shouldSendNotice — the cold dialog this removes', () => {
  it('does not even try once the notices are refused on this device', () => {
    // The SDK's `notify()` asks for the permission itself, WITHOUT our sentence in front
    // (hub#758's scope, not hub#1732's primer). Calling it after a «no» is exactly the
    // out-of-context dialog this issue is about — and Android would drop the notice anyway.
    expect(shouldSendNotice('denied')).toBe(false);
  });

  it('tries when it can work: granted, and on every platform without the permission', () => {
    expect(shouldSendNotice('granted')).toBe(true);
    // Desktop and browser: `erplora_notify` shows a real OS notification there and no Android
    // permission gates it. Reading `unsupported` as «do not notify» would silence the Mac.
    expect(shouldSendNotice('unsupported')).toBe(true);
  });
});

describe('primerLabelsFrom — the keys, so a rename cannot ship a raw code', () => {
  it('reads the four strings of the sheet', () => {
    const labels = primerLabelsFrom((key) => `t:${key}`);
    expect(labels).toEqual({
      header: 't:system.notices.primerHeader',
      message: 't:system.notices.primerMessage',
      later: 't:system.notices.primerLater',
      allow: 't:system.notices.primerAllow',
    });
  });

  it('every key it names exists in BOTH locales (ADR-0055/0199)', () => {
    const read = (bundle: unknown, key: string): unknown =>
      key.split('.').reduce<unknown>((node, part) => (node as Record<string, unknown>)?.[part], bundle);
    for (const key of NOTICE_COPY_KEYS) {
      expect(typeof read(en, key), `en → ${key}`).toBe('string');
      expect(typeof read(es, key), `es → ${key}`).toBe('string');
    }
  });
});
