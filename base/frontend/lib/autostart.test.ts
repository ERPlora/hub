// «Start on login» on the computer (ERPlora/app HUB_APP-F27): the operating system keeps the setting and the installed
// app relays it, so the Hub only asks. A browser has no app, Android refuses the command on purpose and an older app
// has no such command: in the three the setting does not exist, which is not the same as «off».
import { describe, expect, it, vi } from 'vitest';

import { readAutostart, switchAutostart } from './autostart';

type Invoke = (command: string) => Promise<unknown>;

const app = (invoke: Invoke) => ({ __TAURI__: { core: { invoke } } });
const refusing = (reason: string) => vi.fn<Invoke>(async () => Promise.reject(reason));

describe('readAutostart', () => {
  it('in a browser there is no such setting', async () => {
    await expect(readAutostart({})).resolves.toBeNull();
  });

  it('on the computer it is what the operating system says now', async () => {
    const on = vi.fn<Invoke>(async () => true);
    await expect(readAutostart(app(on))).resolves.toBe(true);
    expect(on.mock.calls).toEqual([['autostart_is_enabled']]);
    await expect(readAutostart(app(vi.fn<Invoke>(async () => false)))).resolves.toBe(false);
  });

  it('Android refuses it on purpose and an older app has no such command: no setting', async () => {
    await expect(readAutostart(app(refusing('autostart is desktop-only')))).resolves.toBeNull();
    await expect(readAutostart(app(refusing('Command autostart_is_enabled not found')))).resolves.toBeNull();
  });

  it('an answer that is neither on nor off is no setting either', async () => {
    await expect(readAutostart(app(vi.fn<Invoke>(async () => undefined)))).resolves.toBeNull();
  });
});

describe('switchAutostart', () => {
  it('turning it on asks the app to enable it and answers what the system reads back', async () => {
    const stuck = vi.fn<Invoke>(async () => false);
    await expect(switchAutostart(true, app(stuck))).resolves.toBe(false);
    expect(stuck.mock.calls).toEqual([['autostart_enable']]);
  });

  it('turning it off asks the app to disable it', async () => {
    const off = vi.fn<Invoke>(async () => false);
    await expect(switchAutostart(false, app(off))).resolves.toBe(false);
    expect(off.mock.calls).toEqual([['autostart_disable']]);
  });

  it('a refusal of the app, or an answer that is not on or off, fails so the screen can say so', async () => {
    await expect(switchAutostart(true, app(refusing('Access is denied.')))).rejects.toBe('Access is denied.');
    await expect(switchAutostart(true, app(vi.fn<Invoke>(async () => null)))).rejects.toThrow('autostart_enable');
  });

  it('in a browser there is nothing to switch', async () => {
    await expect(switchAutostart(true, {})).rejects.toThrow('no installed app');
  });
});
