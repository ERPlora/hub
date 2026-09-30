// @vitest-environment happy-dom
// hub#2336 — with the marketplace down, `GET /api/modules/updates` answered every app with
// `update_available: false` inside an `ok: true` envelope: word for word «everything is up to date».
// The bell took it at its word and cleared «N apps have a new version» until the next check, hours
// later. The runtime now marks each row `checked: false` when it could not ask, and the bell:
//   · keeps the last known count (a known update among the answered rows still counts);
//   · says it could not check (`moduleUpdatesUnknown`), for an admin only;
//   · lets the owner ask again (`retryModuleUpdateNotice`), once at a time (`moduleUpdatesChecking`).
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { nextTick, ref } from 'vue';

import type { ModuleUpdateInfo } from './module-updates';
import { notificationCountOf, setNotificationCount } from './shell';

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
  refreshModuleUpdateNotice,
  publishModuleUpdates,
  markModuleUpdatesUnknown,
  retryModuleUpdateNotice,
  moduleUpdatesUnknown,
  moduleUpdatesChecking,
  stopModuleUpdateNoticeWatch,
} = await import('./module-update-notice');
const { hasUncheckedUpdates } = await import('./module-updates');

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
    checked: true,
    ...over,
  };
}

/** A row the runtime could not ask the marketplace about. */
const unchecked = (module_id: string): ModuleUpdateInfo =>
  upd(module_id, { update_available: false, latest: '1.0.0', checked: false });

function deferred<T>() {
  let resolve!: (v: T) => void;
  const promise = new Promise<T>((res) => (resolve = res));
  return { promise, resolve };
}

describe('hasUncheckedUpdates (hub#2336)', () => {
  it('is true when any row could not be checked', () => {
    expect(hasUncheckedUpdates([upd('sales'), unchecked('kitchen')])).toBe(true);
  });

  it('is false when every row was checked', () => {
    expect(hasUncheckedUpdates([upd('sales'), upd('kitchen', { update_available: false })])).toBe(false);
  });

  // A runtime older than the field answers without it: that is the old «checked» answer.
  it('reads a row without the field as checked', () => {
    const { checked: _omit, ...legacy } = upd('sales');
    expect(hasUncheckedUpdates([legacy as ModuleUpdateInfo])).toBe(false);
  });

  it('an empty answer is fully checked (no apps installed)', () => {
    expect(hasUncheckedUpdates([])).toBe(false);
  });
});

describe('the bell when the marketplace could not be asked (hub#2336)', () => {
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

  // THE symptom: the marketplace goes down after the bell said «2 apps have a new version».
  it('🔴 an answer with unchecked apps keeps the last count instead of clearing it', async () => {
    listModuleUpdates.mockResolvedValue([upd('sales'), upd('kitchen')]);
    await refreshModuleUpdateNotice();
    expect(notificationCountOf('moduleUpdates')).toBe(2);

    listModuleUpdates.mockResolvedValue([unchecked('sales'), unchecked('kitchen')]);
    await refreshModuleUpdateNotice();

    expect(notificationCountOf('moduleUpdates')).toBe(2);
  });

  it('🔴 an answer with unchecked apps says it could not check', async () => {
    listModuleUpdates.mockResolvedValue([unchecked('sales'), upd('kitchen', { update_available: false })]);
    await refreshModuleUpdateNotice();

    expect(moduleUpdatesUnknown.value).toBe(true);
  });

  // A known update among the answered rows is news whatever happened to the others.
  it('a known update among the answered apps still counts', async () => {
    listModuleUpdates.mockResolvedValue([upd('sales'), upd('tables'), unchecked('kitchen')]);
    await refreshModuleUpdateNotice();

    expect(notificationCountOf('moduleUpdates')).toBe(2);
    expect(moduleUpdatesUnknown.value).toBe(true);
  });

  it('a runtime that did not answer at all also says it could not check (and keeps the count)', async () => {
    listModuleUpdates.mockResolvedValue([upd('sales')]);
    await refreshModuleUpdateNotice();
    listModuleUpdates.mockRejectedValue(new Error('offline'));

    await refreshModuleUpdateNotice();

    expect(moduleUpdatesUnknown.value).toBe(true);
    expect(notificationCountOf('moduleUpdates')).toBe(1);
  });

  it('a fully answered check clears «could not check» and paints the real count', async () => {
    listModuleUpdates.mockResolvedValue([upd('sales'), unchecked('kitchen')]);
    await refreshModuleUpdateNotice();
    expect(moduleUpdatesUnknown.value).toBe(true);

    listModuleUpdates.mockResolvedValue([upd('sales', { update_available: false }), upd('kitchen')]);
    await refreshModuleUpdateNotice();

    expect(moduleUpdatesUnknown.value).toBe(false);
    expect(notificationCountOf('moduleUpdates')).toBe(1);
  });

  // Up to date and checked: nothing to say, not «could not check».
  it('an answered «nothing new» is not «could not check»', async () => {
    listModuleUpdates.mockResolvedValue([upd('sales', { update_available: false })]);
    await refreshModuleUpdateNotice();

    expect(moduleUpdatesUnknown.value).toBe(false);
    expect(notificationCountOf('moduleUpdates')).toBe(0);
  });

  it('is not said to someone who cannot update apps', async () => {
    listModuleUpdates.mockResolvedValue([unchecked('sales')]);
    await refreshModuleUpdateNotice();
    expect(moduleUpdatesUnknown.value).toBe(true);

    isAdmin.value = false;
    await refreshModuleUpdateNotice();

    expect(moduleUpdatesUnknown.value).toBe(false);
  });

  it('stopping the watch (sign-out) clears it', async () => {
    listModuleUpdates.mockResolvedValue([unchecked('sales')]);
    await refreshModuleUpdateNotice();

    stopModuleUpdateNoticeWatch();

    expect(moduleUpdatesUnknown.value).toBe(false);
  });

  // ── What the Apps screen learns ────────────────────────────────────────────────────────────

  it('what the Apps screen learns with unchecked apps keeps the count and says it', async () => {
    listModuleUpdates.mockResolvedValue([upd('sales'), upd('kitchen')]);
    await refreshModuleUpdateNotice();

    publishModuleUpdates([unchecked('sales'), unchecked('kitchen')], 'v1.4.0');

    expect(notificationCountOf('moduleUpdates')).toBe(2);
    expect(moduleUpdatesUnknown.value).toBe(true);
  });

  it('what the Apps screen learns fully answered clears it', async () => {
    listModuleUpdates.mockResolvedValue([unchecked('sales')]);
    await refreshModuleUpdateNotice();

    publishModuleUpdates([upd('sales')], 'v1.4.0');

    expect(moduleUpdatesUnknown.value).toBe(false);
    expect(notificationCountOf('moduleUpdates')).toBe(1);
  });

  it('a failed check on the Apps screen says it on the bell too, keeping the count', async () => {
    listModuleUpdates.mockResolvedValue([upd('sales')]);
    await refreshModuleUpdateNotice();

    markModuleUpdatesUnknown();

    expect(moduleUpdatesUnknown.value).toBe(true);
    expect(notificationCountOf('moduleUpdates')).toBe(1);
  });

  it('a failed check on the Apps screen is not said to a non-admin', () => {
    isAdmin.value = false;
    markModuleUpdatesUnknown();
    expect(moduleUpdatesUnknown.value).toBe(false);
  });

  // ── Retry from the bell ────────────────────────────────────────────────────────────────────

  it('🔴 «Check again» asks the marketplace again and an answer clears it', async () => {
    listModuleUpdates.mockResolvedValue([unchecked('sales')]);
    await refreshModuleUpdateNotice();
    listModuleUpdates.mockResolvedValue([upd('sales')]);

    retryModuleUpdateNotice();
    await settle();

    expect(listModuleUpdates).toHaveBeenCalledTimes(2);
    expect(moduleUpdatesUnknown.value).toBe(false);
    expect(notificationCountOf('moduleUpdates')).toBe(1);
  });

  it('is «checking» while the question is out, and «Check again» cannot fire twice', async () => {
    listModuleUpdates.mockResolvedValue([unchecked('sales')]);
    await refreshModuleUpdateNotice();
    expect(moduleUpdatesChecking.value).toBe(false);
    const pending = deferred<ModuleUpdateInfo[]>();
    listModuleUpdates.mockReturnValue(pending.promise);

    retryModuleUpdateNotice();
    await settle();
    expect(moduleUpdatesChecking.value).toBe(true);
    retryModuleUpdateNotice();
    await settle();
    expect(listModuleUpdates).toHaveBeenCalledTimes(2);

    pending.resolve([upd('sales', { update_available: false })]);
    await settle();
    expect(moduleUpdatesChecking.value).toBe(false);
    expect(moduleUpdatesUnknown.value).toBe(false);
  });

  // What the Apps screen learns overtakes a check in flight: that check still has to give the
  // button back when its answer lands, or the bell reads «Checking…» forever.
  it('a check overtaken by the Apps screen does not leave «Checking…» stuck', async () => {
    const pending = deferred<ModuleUpdateInfo[]>();
    listModuleUpdates.mockReturnValueOnce(pending.promise);
    const inFlight = refreshModuleUpdateNotice();
    await settle();
    expect(moduleUpdatesChecking.value).toBe(true);

    publishModuleUpdates([unchecked('sales')], 'v1.4.0');
    pending.resolve([upd('sales')]);
    await inFlight;

    expect(moduleUpdatesChecking.value).toBe(false);
    expect(moduleUpdatesUnknown.value, 'the overtaken answer is dropped').toBe(true);
  });

  it('a retry that fails again keeps saying it could not check', async () => {
    listModuleUpdates.mockResolvedValue([unchecked('sales')]);
    await refreshModuleUpdateNotice();
    listModuleUpdates.mockRejectedValue(new Error('offline'));

    retryModuleUpdateNotice();
    await settle();

    expect(moduleUpdatesUnknown.value).toBe(true);
    expect(moduleUpdatesChecking.value).toBe(false);
  });
});
