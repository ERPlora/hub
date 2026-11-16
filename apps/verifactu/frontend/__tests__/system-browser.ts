// Inside the installed app an outside page (the AEAT's) opens in the system browser, through the bridge's
// `open_external_url`, never as a link followed inside the app. A test puts the page inside the app first, and its file
// takes it out after each test (`outOfTheApp` of base's download harness).
import { expect, vi } from 'vitest';

type TauriWindow = { __TAURI__?: { core: { invoke: (command: string, args?: unknown) => Promise<unknown> } } };

/** Puts the page inside the installed app, whose bridge resolves every command: its `invoke`, to look at. */
export function insideTheInstalledApp() {
  const invoke = vi.fn<(command: string, args?: unknown) => Promise<unknown>>(() => Promise.resolve());
  (window as TauriWindow).__TAURI__ = { core: { invoke } };
  return invoke;
}

/** A person's tap on `element`: the page stops the link and asks the bridge to open `url` in the system browser. */
export function expectTapOpensInTheSystemBrowser(element: Element, invoke: ReturnType<typeof insideTheInstalledApp>, url: string): void {
  const tap = new MouseEvent('click', { bubbles: true, cancelable: true });
  element.dispatchEvent(tap);
  expect(tap.defaultPrevented).toBe(true);
  expect(invoke).toHaveBeenCalledWith('open_external_url', { url });
}
