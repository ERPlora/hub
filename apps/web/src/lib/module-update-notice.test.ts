// @vitest-environment happy-dom
// hub#1172 — a hub ran 9 apps behind the marketplace and the owner had no way to know: the only
// place that said «Update to X» was Apps → «My apps», and nobody opens that screen to look. The
// bell now carries ONE aggregated notice («3 apps have a new version») that leads there.
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { nextTick, ref } from 'vue';

import type { ModuleUpdateInfo } from './module-updates';
import { notificationCount, notificationCountOf, setNotificationCount } from './shell';

const isAuthed = { value: true };
const isAdmin = { value: true };
const user = ref<{ id: string } | null>({ id: 'owner' });
const listModuleUpdates = vi.fn<() => Promise<ModuleUpdateInfo[]>>();
const fetchSystemInfo = vi.fn<() => Promise<{ hubVersion?: string | null } | null>>();

vi.mock('./session', () => ({
  get isAuthed() {
    return isAuthed;
  },
  get isAdmin() {
    return isAdmin;
  },
  get user() {
    return user;
  },
}));
vi.mock('./runtime', () => ({ listModuleUpdates: () => listModuleUpdates() }));
vi.mock('./system', () => ({ fetchSystemInfo: () => fetchSystemInfo() }));

// Imported after the mocks so the module under test picks them up.
const {
  actionableUpdateCount,
  refreshModuleUpdateNotice,
  publishModuleUpdates,
  bootModuleUpdateNoticeWatch,
  stopModuleUpdateNoticeWatch,
  MODULE_UPDATES_ROUTE,
} = await import('./module-update-notice');

const settle = async (): Promise<void> => {
  await nextTick();
  for (let i = 0; i < 5; i++) await Promise.resolve();
};

function upd(module_id: string, over: Partial<ModuleUpdateInfo> = {}): ModuleUpdateInfo {
  return {
    module_id,
    installed: '1.0.0',
    latest: '1.1.0',
    update_available: true,
    pinned: null,
    latest_min_erplora_version: null,
    ...over,
  };
}

describe('aggregated «apps have a new version» notice on the bell (hub#1172)', () => {
  beforeEach(() => {
    isAuthed.value = true;
    isAdmin.value = true;
    user.value = { id: 'owner' };
    listModuleUpdates.mockReset();
    fetchSystemInfo.mockReset();
    fetchSystemInfo.mockResolvedValue({ hubVersion: 'v1.4.0' });
    stopModuleUpdateNoticeWatch();
    setNotificationCount(0, 'deadLetters');
    setNotificationCount(0, 'printing');
    setNotificationCount(0, 'modules');
  });

  // THE symptom: apps behind the marketplace → the bell says how many, from any screen.
  it('an owner with apps behind sees how many on the bell', async () => {
    listModuleUpdates.mockResolvedValue([
      upd('sales', { installed: '2.15.24', latest: '2.16.10' }),
      upd('kitchen'),
      upd('tables'),
      upd('inventory', { update_available: false, latest: '1.0.0' }),
    ]);

    await refreshModuleUpdateNotice();

    expect(notificationCountOf('moduleUpdates')).toBe(3);
    expect(notificationCount.value).toBe(3);
  });

  it('adds to the other bell sources instead of replacing them', async () => {
    setNotificationCount(2, 'deadLetters');
    listModuleUpdates.mockResolvedValue([upd('sales')]);

    await refreshModuleUpdateNotice();

    expect(notificationCount.value).toBe(3);
    expect(notificationCountOf('deadLetters')).toBe(2);
  });

  it('leads to the «My apps» tab, where each update is one tap', () => {
    expect(MODULE_UPDATES_ROUTE).toBe('/apps#mine');
  });

  // Only an admin can update an app (the runtime refuses anyone else): a notice a cashier can do
  // nothing about teaches the whole shift to ignore the bell.
  it('a non-admin session sees nothing and the marketplace is not asked', async () => {
    isAdmin.value = false;
    listModuleUpdates.mockResolvedValue([upd('sales')]);

    await refreshModuleUpdateNotice();

    expect(notificationCountOf('moduleUpdates')).toBe(0);
    expect(listModuleUpdates).not.toHaveBeenCalled();
  });

  it('an admin handing over to a cashier clears the notice', async () => {
    listModuleUpdates.mockResolvedValue([upd('sales')]);
    await refreshModuleUpdateNotice();
    expect(notificationCountOf('moduleUpdates')).toBe(1);

    isAdmin.value = false;
    await refreshModuleUpdateNotice();

    expect(notificationCountOf('moduleUpdates')).toBe(0);
  });

  it('a signed-out shell sees nothing', async () => {
    isAuthed.value = false;
    listModuleUpdates.mockResolvedValue([upd('sales')]);

    await refreshModuleUpdateNotice();

    expect(notificationCountOf('moduleUpdates')).toBe(0);
    expect(listModuleUpdates).not.toHaveBeenCalled();
  });

  // An update that needs a newer ERPlora cannot be applied from Apps (hub#2082): counting it would
  // be a notice the owner can never clear.
  it('does not count an update that needs a newer ERPlora than this hub runs', async () => {
    listModuleUpdates.mockResolvedValue([
      upd('sales', { latest_min_erplora_version: '9.0.0' }),
      upd('kitchen', { latest_min_erplora_version: '1.4.0' }),
    ]);

    await refreshModuleUpdateNotice();

    expect(notificationCountOf('moduleUpdates')).toBe(1);
  });

  it('with an unreadable hub version, the update still counts (the runtime refuses at update time)', () => {
    expect(actionableUpdateCount([upd('sales', { latest_min_erplora_version: '9.0.0' })], null)).toBe(1);
  });

  // «I don't know» is never painted as «there is news», and never as «all clear» either.
  it('a failed check keeps the last known count instead of flashing zero', async () => {
    listModuleUpdates.mockResolvedValue([upd('sales'), upd('kitchen')]);
    await refreshModuleUpdateNotice();
    expect(notificationCountOf('moduleUpdates')).toBe(2);

    listModuleUpdates.mockRejectedValue(new Error('offline'));
    await refreshModuleUpdateNotice();

    expect(notificationCountOf('moduleUpdates')).toBe(2);
  });

  // Updating from Apps must clear the notice right away, not at the next check.
  it('what the Apps screen learns replaces the notice immediately', async () => {
    listModuleUpdates.mockResolvedValue([upd('sales'), upd('kitchen')]);
    await refreshModuleUpdateNotice();
    expect(notificationCountOf('moduleUpdates')).toBe(2);

    publishModuleUpdates([upd('sales'), upd('kitchen', { update_available: false })], 'v1.4.0');

    expect(notificationCountOf('moduleUpdates')).toBe(1);
  });

  it('what the Apps screen learns is ignored for a non-admin session', () => {
    isAdmin.value = false;

    publishModuleUpdates([upd('sales')], 'v1.4.0');

    expect(notificationCountOf('moduleUpdates')).toBe(0);
  });

  it('boot checks once, and a PIN hand-over re-checks for whoever arrived', async () => {
    listModuleUpdates.mockResolvedValue([upd('sales')]);

    bootModuleUpdateNoticeWatch();
    await settle();
    expect(listModuleUpdates).toHaveBeenCalledTimes(1);
    expect(notificationCountOf('moduleUpdates')).toBe(1);

    isAdmin.value = false;
    user.value = { id: 'cashier' };
    await settle();

    expect(notificationCountOf('moduleUpdates')).toBe(0);
  });

  // Each check costs one marketplace call per installed app (hub#516): the watch never polls fast.
  it('boot is idempotent and the re-check is hours apart, not seconds', async () => {
    vi.useFakeTimers();
    try {
      listModuleUpdates.mockResolvedValue([]);
      bootModuleUpdateNoticeWatch();
      bootModuleUpdateNoticeWatch();
      await vi.advanceTimersByTimeAsync(0);
      expect(listModuleUpdates).toHaveBeenCalledTimes(1);

      await vi.advanceTimersByTimeAsync(59 * 60_000);
      expect(listModuleUpdates).toHaveBeenCalledTimes(1);

      await vi.advanceTimersByTimeAsync(6 * 60 * 60_000);
      expect(listModuleUpdates).toHaveBeenCalledTimes(2);
    } finally {
      stopModuleUpdateNoticeWatch();
      vi.useRealTimers();
    }
  });

  // An admin's check still in flight when a cashier takes the till must not paint for the cashier.
  it('a check overtaken by a PIN hand-over drops its result', async () => {
    let answer: (u: ModuleUpdateInfo[]) => void = () => {};
    listModuleUpdates.mockReturnValueOnce(new Promise((resolve) => (answer = resolve)));
    const inFlight = refreshModuleUpdateNotice();

    isAdmin.value = false;
    await refreshModuleUpdateNotice();
    isAdmin.value = true; // back to an admin before the stale answer lands: still stale
    answer([upd('sales'), upd('kitchen')]);
    await inFlight;

    expect(notificationCountOf('moduleUpdates')).toBe(0);
  });

  // The watch only works if the shell starts it: nothing else boots it.
  it('the shell starts the watch with the other bell sources', () => {
    const app = readFileSync(join(process.cwd(), 'src/App.vue'), 'utf8');
    expect(app).toMatch(/^\s*bootModuleUpdateNoticeWatch\(\);$/m);
  });

  it('signing out clears the notice without waiting for the next check', async () => {
    listModuleUpdates.mockResolvedValue([upd('sales')]);
    bootModuleUpdateNoticeWatch();
    await settle();
    expect(notificationCountOf('moduleUpdates')).toBe(1);

    isAuthed.value = false;
    user.value = null;
    await settle();

    expect(notificationCountOf('moduleUpdates')).toBe(0);
  });

  it('stopping the watch clears the notice', async () => {
    listModuleUpdates.mockResolvedValue([upd('sales')]);
    await refreshModuleUpdateNotice();

    stopModuleUpdateNoticeWatch();

    expect(notificationCountOf('moduleUpdates')).toBe(0);
  });
});
