// The device's notices (APPOINTMENT-F28, the old hub's HUB_SHELL-F66): base follows `base.notice.list` live — the rows
// the modules on tell, with their texts filled in — and the shell tells each new one once with the installed app's
// system notice (`erplora_notify`); a browser has the bell. It paints nothing.
import { TOLD_KEY } from '@erplora/ui/shell';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

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

beforeEach(() => {
  vi.stubGlobal('localStorage', memoryStorage());
  localStorage.setItem(TOLD_KEY, '[]');
  invoke = vi.fn(async () => null);
  win.__TAURI__ = { core: { invoke } };
});

afterEach(() => {
  vi.unstubAllGlobals();
  delete win.__TAURI__;
  document.body.innerHTML = '';
});

const notified = () => invoke.mock.calls.filter(([command]) => command === 'erplora_notify').map(([, args]) => args);

async function setup() {
  const m = await mountBase(DeviceNotices, { routes: ['/appointment/agenda'] });
  const call = await m.live();
  const show = (notices: DeviceNoticeRow[], rev?: number) => m.result(call, 'base.notice.list', { notices }, rev);
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

  it('in a browser (no installed app) it tells nothing and breaks nothing', async () => {
    delete win.__TAURI__;
    const s = await setup();

    await s.show([BOOKED]);

    expect(invoke).not.toHaveBeenCalled();
    expect(localStorage.getItem(TOLD_KEY)).toBe('[]');
  });
});
