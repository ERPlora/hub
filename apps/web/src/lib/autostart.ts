// «Start on login» (ADR-0204 §7, hub#389) — the web face of the shell's autostart commands.
//
// Why it exists: the print queue lives in the hub (ADR-0196 §6) and the device with the app is
// what drains it — if nobody opened the app, the tickets wait. On a dedicated desktop till,
// starting with the OS session guarantees there is always a print host. Opt-in, OFF by default.
//
// The state lives in the OS (LaunchAgent / registry key / autostart dir); the shell relays it and
// this module never caches it. One probe decides everything: a browser has no shell (`invokeTauri`
// resolves `null`), Android answers an error ON PURPOSE (the plugin is desktop-only), and an older
// desktop shell lacks the command. All three mean "no toggle", never "toggle off".
import { invokeTauri } from './device';

export interface AutostartState {
  /** Whether this device can start on login at all — i.e. whether the toggle should render. */
  available: boolean;
  /** What the OS says right now. Meaningless when `available` is false. */
  enabled: boolean;
}

/** Availability and current state, in the one probe that can honestly answer both. */
export async function autostartState(): Promise<AutostartState> {
  try {
    const enabled = await invokeTauri<boolean>('autostart_is_enabled');
    if (typeof enabled === 'boolean') return { available: true, enabled };
  } catch {
    // Mobile (desktop-only by decision) or a shell older than the command.
  }
  return { available: false, enabled: false };
}

/**
 * Flips the setting and answers with the state the OS reads BACK — not the state that was asked
 * for. A shell whose `enable()` silently failed must leave the toggle OFF, or the till "starts on
 * login" only on screen. A refusal propagates so the screen can say it failed.
 */
export async function setAutostart(enabled: boolean): Promise<boolean> {
  const state = await invokeTauri<boolean>(enabled ? 'autostart_enable' : 'autostart_disable');
  return state === true;
}
