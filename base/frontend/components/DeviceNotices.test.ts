// The device's notices (APPOINTMENT-F28): base follows `base.notice.list` live — the rows
// the modules on tell, with their texts filled in — and the shell tells each new one once with the installed app's
// system notice (`erplora_notify`); a browser has the bell. It paints nothing.
import { ANDROID_NOTIFICATIONS, applySurface, KEEP_LISTENING_COMMAND, PRIMER_ANSWERED_KEY, TOLD_KEY } from '@erplora/ui/shell';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const alerts = vi.hoisted(() => ({ created: [] as Array<{ header?: string }> }));
vi.mock('@ionic/vue', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@ionic/vue')>()),
  alertController: {
    create: async (options: { header?: string }) => {
      alerts.created.push(options);
      return { present: async () => {}, onDidDismiss: async () => ({ role: 'confirm' }) };
    },
  },
}));

import type { DeviceNoticeRow } from '../operations';
import { flush, memoryStorage, mountBase } from '../__tests__/mount-base';
import DeviceNotices from './DeviceNotices.vue';

const BOOKED: DeviceNoticeRow = {
  key: 'appointment.booked',
  app: 'appointment',
  id: '0192f0aa-0000-7000-8000-000000000001',
  at: '2026-10-23T09:40:00Z',
  title: 'Nueva cita · Ana Pérez',
  body: 'Corte · sábado, 24 de octubre a las 10:00 · Marta',
  route: '/appointment/agenda?date=2026-10-24',
};

const win = window as unknown as { __TAURI__?: unknown };
let invoke: ReturnType<typeof vi.fn>;
/** Every mount of a test, unmounted after it: a piece left mounted would wake up with the next test's app. */
const mounted: Array<{ unmount: () => void }> = [];

async function mountNotices() {
  const m = await mountBase(DeviceNotices, { routes: ['/appointment/agenda'] });
  mounted.push(m.wrapper);
  return m;
}

beforeEach(() => {
  vi.stubGlobal('localStorage', memoryStorage());
  localStorage.setItem(TOLD_KEY, '[]');
  invoke = vi.fn(async () => null);
  win.__TAURI__ = { core: { invoke } };
  applySurface('desktop');
});

afterEach(() => {
  mounted.splice(0).forEach((wrapper) => wrapper.unmount());
  applySurface('web');
  vi.unstubAllGlobals();
  delete win.__TAURI__;
  document.body.innerHTML = '';
});

const notified = () => invoke.mock.calls.filter(([command]) => command === 'erplora_notify').map(([, args]) => args);
const listened = () => invoke.mock.calls.filter(([command]) => command === KEEP_LISTENING_COMMAND).map(([, args]) => args);

async function setup() {
  const m = await mountNotices();
  const call = await m.live();
  const show = (notices: DeviceNoticeRow[], rev?: number, sources = ['appointment.booked']) =>
    m.result(call, 'base.notice.list', { notices, sources }, rev);
  return { ...m, show };
}

describe('DeviceNotices', () => {
  it('follows base.notice.list live and paints nothing', async () => {
    const s = await setup();
    expect(s.client.stream.subscriptions('base.notice.list').map((sub) => sub.params)).toEqual([{}]);
    expect(s.wrapper.text()).toBe('');
  });

  it('tells a new notice once on the installed app, with its texts and the screen a tap opens', async () => {
    const s = await setup();

    await s.show([BOOKED]);
    await vi.waitFor(() => expect(notified()).toHaveLength(1));
    // The next write anywhere re-runs the query: the same row comes back and is not told again.
    await s.show([BOOKED], 2);
    await flush();

    expect(notified()).toEqual([
      {
        title: 'Nueva cita · Ana Pérez',
        body: 'Corte · sábado, 24 de octubre a las 10:00 · Marta',
        id: expect.any(Number),
        path: '/appointment/agenda?date=2026-10-24',
      },
    ]);
  });

  it('on an Android that has not let the app notify, asks once with our sentence when the person hears something', async () => {
    alerts.created.length = 0;
    invoke.mockImplementation(async (command: string) =>
      command === 'plugin:erplora-android|check_permissions' ? { [ANDROID_NOTIFICATIONS]: false } : null,
    );
    const s = await setup();

    await s.show([], 1, []);
    await flush();
    expect(alerts.created).toEqual([]);
    await s.show([], 2, ['appointment.booked', 'appointment.cancelled']);
    await vi.waitFor(() =>
      expect(invoke).toHaveBeenCalledWith('plugin:erplora-android|request_permissions', { permissions: [ANDROID_NOTIFICATIONS] }),
    );

    expect(alerts.created.map((alert) => alert.header)).toEqual(['Let us keep you posted']);
    expect(localStorage.getItem(PRIMER_ANSWERED_KEY)).toBe('1');
  });

  // HUB_APP-F26 (hub#836): with the screen off Android freezes the page; the app keeps it listening while asked to.
  it('keeps the installed app listening while the person hears something (a new kitchen ticket), and only once the hub said so', async () => {
    invoke.mockImplementation(async (command: string) =>
      command === 'plugin:erplora-android|check_permissions' ? { [ANDROID_NOTIFICATIONS]: true } : null,
    );
    const s = await setup();
    await flush();
    // Until base.notice.list answers, the app is asked nothing: a reload never stops what the page before left on.
    expect(listened()).toEqual([]);

    await s.show([], 1, ['kitchen.received']);
    await vi.waitFor(() =>
      expect(listened()).toEqual([
        {
          on: true,
          title: 'ERPlora is listening',
          body: "You'll be warned when something needs your attention, even with the screen off.",
          channel: 'Notices with the screen off',
        },
      ]),
    );
    // The app that told turned off: nothing left to hear, so nothing to keep the device awake for.
    await s.show([], 2, []);
    await vi.waitFor(() => expect(listened().map((args) => (args as { on: boolean }).on)).toEqual([true, false]));
  });

  it('an installed app without the command (the 1.1.34) keeps working: the notices still go out and nothing shows', async () => {
    alerts.created.length = 0;
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    invoke.mockImplementation(async (command: string) => {
      if (command === KEEP_LISTENING_COMMAND) throw 'erplora-android.keep_listening not allowed. Command not found';
      return command === 'plugin:erplora-android|check_permissions' ? { [ANDROID_NOTIFICATIONS]: true } : null;
    });
    const s = await setup();

    await s.show([], 1, ['kitchen.received']);
    await vi.waitFor(() => expect(listened()).toHaveLength(1));
    await s.show([BOOKED], 2, ['kitchen.received', 'appointment.booked']);
    await vi.waitFor(() => expect(notified()).toHaveLength(1));

    expect(listened()).toHaveLength(1);
    expect(warn).toHaveBeenCalledOnce();
    expect(s.wrapper.text()).toBe('');
    expect(alerts.created).toEqual([]);
    warn.mockRestore();
  });

  it('in a browser (no installed app) it does not even follow the notices: the bell is the browser\'s', async () => {
    delete win.__TAURI__;
    applySurface('web');
    const m = await mountNotices();
    await m.live().catch(() => undefined);
    await flush();

    expect(m.client.stream.subscriptions('base.notice.list')).toEqual([]);
    expect(invoke).not.toHaveBeenCalled();
    expect(localStorage.getItem(TOLD_KEY)).toBe('[]');
  });
});
