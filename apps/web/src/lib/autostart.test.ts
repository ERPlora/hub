// «Start on login» (ADR-0204 §7, hub#389) — the web face of the shell's autostart commands.
//
// The state lives in the OS (LaunchAgent / registry / autostart dir) and the shell only relays
// it, so the ONE probe that decides whether the toggle renders is the command itself: a browser
// has no shell, Android answers an error on purpose (the plugin is desktop-only), and an older
// desktop shell simply lacks the command. All three must mean "no toggle", never "toggle off".
import { describe, it, expect, vi, beforeEach } from 'vitest';

const invokeTauri = vi.fn();

vi.mock('./device', () => ({
  invokeTauri: (cmd: string, args?: Record<string, unknown>) => invokeTauri(cmd, args),
}));

import { autostartState, setAutostart } from './autostart';

beforeEach(() => {
  invokeTauri.mockReset();
});

describe('autostartState', () => {
  it('a desktop shell answers availability and the OS state in one probe', async () => {
    invokeTauri.mockResolvedValue(false);

    expect(await autostartState()).toEqual({ available: true, enabled: false });
    expect(invokeTauri).toHaveBeenCalledWith('autostart_is_enabled', undefined);
  });

  it('in a plain browser there is no toggle to show', async () => {
    // invokeTauri resolves null outside the shell — that is "no shell", not "disabled".
    invokeTauri.mockResolvedValue(null);

    expect(await autostartState()).toEqual({ available: false, enabled: false });
  });

  it('on Android (or an older shell) the command errors and the toggle stays hidden', async () => {
    // The Rust command answers an error on mobile ON PURPOSE: a silent `false` would render a
    // toggle that can never work on a tablet.
    invokeTauri.mockRejectedValue(new Error('autostart is desktop-only (ADR-0204 §7)'));

    expect(await autostartState()).toEqual({ available: false, enabled: false });
  });
});

describe('setAutostart', () => {
  it('enabling asks the shell and reports the state the OS read back', async () => {
    invokeTauri.mockResolvedValue(true);

    expect(await setAutostart(true)).toBe(true);
    expect(invokeTauri).toHaveBeenCalledWith('autostart_enable', undefined);
  });

  it('disabling goes through its own command', async () => {
    invokeTauri.mockResolvedValue(false);

    expect(await setAutostart(false)).toBe(false);
    expect(invokeTauri).toHaveBeenCalledWith('autostart_disable', undefined);
  });

  it('a shell that failed to change the state does not get to claim it did', async () => {
    // The answer is what the OS says NOW, not what was asked: a sandboxed build whose enable()
    // silently no-ops must leave the toggle OFF, or the till "starts on login" only on screen.
    invokeTauri.mockResolvedValue(false);

    expect(await setAutostart(true)).toBe(false);
  });

  it('a refusal propagates so the screen can say it failed', async () => {
    invokeTauri.mockRejectedValue(new Error('io error: permission denied'));

    await expect(setAutostart(true)).rejects.toThrow('permission denied');
  });
});
