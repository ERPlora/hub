// @vitest-environment happy-dom
// hub#1678 — a module can put a counter on the bell. With «I review them first» on WhatsApp, an
// appointment waited as pending and the owner only found out by opening the diary: the bell knew
// two sources wired by hand (dead letters, printing) and nothing a module could feed.
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { nextTick, ref } from 'vue';

import type { InstalledManifest } from './module-loader';
import { notificationCount, notificationCountOf, setNotificationCount } from './shell';

const isAuthed = { value: true };
const user = ref<{ id: string } | null>({ id: 'owner' });
const allowed = new Set<string>(['appointments.view']);
let installed: InstalledManifest[] = [];
const query = vi.fn<(name: string, params?: Record<string, unknown>) => Promise<unknown>>();

vi.mock('./session', () => ({
  get isAuthed() {
    return isAuthed;
  },
  get user() {
    return user;
  },
  hasPermission: (p: string) => allowed.has(p),
}));
vi.mock('./runtime', () => ({ getClient: () => ({ query }) }));
vi.mock('./module-loader', () => ({ loadInstalledManifests: async () => installed }));

// Imported after the mocks so the module under test picks them up.
const { refreshBellCounters, bellCounters, bootBellCountersWatch, stopBellCountersWatch } = await import(
  './bell-counters'
);

const settle = async (): Promise<void> => {
  await nextTick();
  for (let i = 0; i < 5; i++) await Promise.resolve();
};

function appointments(bell: Record<string, unknown>, locale?: InstalledManifest['locale']): InstalledManifest {
  return {
    moduleId: 'appointments',
    manifest: { id: 'appointments', name: 'Appointments', version: '1.0.0', ui: { entry: 'x.js' }, bell } as never,
    entryUrl: '/modules/appointments/x.js',
    locale,
  };
}

const TO_CONFIRM = {
  label: 'Appointments to confirm',
  icon: 'calendar-outline',
  query: 'appointments.pending_count',
  params: { status: 'pending' },
  nav: 'agenda',
  permission: 'appointments.view',
};

describe('module counters on the bell (hub#1678)', () => {
  beforeEach(() => {
    isAuthed.value = true;
    user.value = { id: 'owner' };
    allowed.clear();
    allowed.add('appointments.view');
    query.mockReset();
    stopBellCountersWatch();
    setNotificationCount(0, 'deadLetters');
    setNotificationCount(0, 'printing');
  });

  // THE symptom: one appointment waiting → the bell says 1 and its row leads to the diary.
  it('counts what the module declares and leads to its tab', async () => {
    installed = [appointments({ 'appointments.to_confirm': TO_CONFIRM })];
    query.mockResolvedValue([{ count: 1 }]);

    await refreshBellCounters();

    expect(query).toHaveBeenCalledWith('appointments.pending_count', { status: 'pending' });
    expect(notificationCount.value).toBe(1);
    expect(notificationCountOf('modules')).toBe(1);
    expect(bellCounters.value).toEqual([
      {
        key: 'appointments.to_confirm',
        label: 'Appointments to confirm',
        icon: 'calendar-outline',
        count: 1,
        path: '/m/appointments/agenda',
      },
    ]);
  });

  it('adds up with the sources the bell already had', async () => {
    installed = [appointments({ 'appointments.to_confirm': TO_CONFIRM })];
    query.mockResolvedValue([{ count: 3 }]);
    setNotificationCount(2, 'printing');

    await refreshBellCounters();

    expect(notificationCount.value).toBe(5);
  });

  it('reads the translated label from the module locale', async () => {
    installed = [
      appointments(
        { 'appointments.to_confirm': TO_CONFIRM },
        { bell: { 'appointments.to_confirm': { label: 'Citas por confirmar' } } },
      ),
    ];
    query.mockResolvedValue([{ count: 2 }]);

    await refreshBellCounters();

    expect(bellCounters.value[0]?.label).toBe('Citas por confirmar');
  });

  // Derived state (ADR-0067): confirm the appointment and the row goes, no dismiss needed.
  it('shows no row and no badge while nothing is waiting', async () => {
    installed = [appointments({ 'appointments.to_confirm': TO_CONFIRM })];
    query.mockResolvedValueOnce([{ count: 1 }]).mockResolvedValueOnce([{ count: 0 }]);

    await refreshBellCounters();
    await refreshBellCounters();

    expect(bellCounters.value).toEqual([]);
    expect(notificationCount.value).toBe(0);
  });

  it('skips a counter the session may not see, without asking the runtime', async () => {
    allowed.clear();
    installed = [appointments({ 'appointments.to_confirm': TO_CONFIRM })];
    query.mockResolvedValue([{ count: 4 }]);

    await refreshBellCounters();

    expect(query).not.toHaveBeenCalled();
    expect(notificationCount.value).toBe(0);
  });

  // A module counts ITS data: a bell entry pointing at another module's query is not honoured.
  it('ignores a counter whose query belongs to another module', async () => {
    installed = [appointments({ 'appointments.sneaky': { ...TO_CONFIRM, query: 'sales.list' } })];
    query.mockResolvedValue([{ count: 9 }]);

    await refreshBellCounters();

    expect(query).not.toHaveBeenCalled();
    expect(bellCounters.value).toEqual([]);
  });

  // A tab id, never a path: whatever `nav` says, the row stays inside the module.
  it('keeps the destination inside the module that raised it', async () => {
    installed = [
      appointments({ 'appointments.to_confirm': { ...TO_CONFIRM, nav: '../../system' } }),
      appointments({ 'appointments.first_tab': { ...TO_CONFIRM, nav: undefined } }),
    ];
    query.mockResolvedValue([{ count: 1 }]);

    await refreshBellCounters();

    expect(bellCounters.value.map((c) => c.path)).toEqual([
      '/m/appointments/..%2F..%2Fsystem',
      '/m/appointments',
    ]);
  });

  // A runtime blip must not read as "all clear": the last known count stays.
  it('keeps the last count when the query fails', async () => {
    installed = [appointments({ 'appointments.to_confirm': TO_CONFIRM })];
    query.mockResolvedValueOnce([{ count: 2 }]).mockRejectedValueOnce(new Error('offline'));

    await refreshBellCounters();
    await refreshBellCounters();

    expect(bellCounters.value[0]?.count).toBe(2);
    expect(notificationCount.value).toBe(2);
  });

  it('treats a first row without a numeric count as nothing waiting', async () => {
    installed = [appointments({ 'appointments.to_confirm': TO_CONFIRM })];
    query.mockResolvedValue([{ total: 7 }]);

    await refreshBellCounters();

    expect(bellCounters.value).toEqual([]);
  });

  it('clears on logout', async () => {
    installed = [appointments({ 'appointments.to_confirm': TO_CONFIRM })];
    query.mockResolvedValue([{ count: 1 }]);
    await refreshBellCounters();

    isAuthed.value = false;
    await refreshBellCounters();

    expect(bellCounters.value).toEqual([]);
    expect(notificationCount.value).toBe(0);
  });

  // A shift hand-over by PIN is not a logout (user-switch.ts): the next cashier must not see, for
  // up to a poll, the counters of the person who left — least of all one she has no permission for.
  it('repaints at once when another cashier takes over the till', async () => {
    installed = [appointments({ 'appointments.to_confirm': TO_CONFIRM })];
    query.mockResolvedValue([{ count: 2 }]);
    bootBellCountersWatch();
    await settle();
    expect(notificationCountOf('modules')).toBe(2);

    allowed.clear();
    user.value = { id: 'cashier' };
    await settle();

    expect(bellCounters.value).toEqual([]);
    expect(notificationCountOf('modules')).toBe(0);
  });

  it('a slow answer asked for the previous cashier does not repaint the bell after the hand-over', async () => {
    installed = [appointments({ 'appointments.to_confirm': TO_CONFIRM })];
    let answer: (v: unknown) => void = () => {};
    query.mockReturnValueOnce(new Promise((r) => (answer = r)));
    const slow = refreshBellCounters();
    await settle();
    expect(query).toHaveBeenCalledTimes(1);

    allowed.clear();
    await refreshBellCounters();
    answer([{ count: 5 }]);
    await slow;

    expect(bellCounters.value).toEqual([]);
    expect(notificationCountOf('modules')).toBe(0);
  });
});
