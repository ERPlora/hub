// The browser's Fullscreen API, wrapped once for the till (WORKBOOK «Vender»: the ⋮ menu's «Full
// screen» / «Exit full screen», the browser's, when the device allows it). It is the WHOLE document that
// goes full screen, as the old shell did: the till's sheets, the checkout and the toasts live in the
// app's root (`ion-app`), so an element of the page on full screen would hide them all.
import { afterEach, describe, expect, it, vi } from 'vitest';

import { isActive, isCapable, onChange, toggle } from './fullscreen';

const root = document.documentElement as HTMLElement & { requestFullscreen?: unknown };
const saved = {
  enabled: Object.getOwnPropertyDescriptor(document, 'fullscreenEnabled'),
  element: Object.getOwnPropertyDescriptor(document, 'fullscreenElement'),
  exit: Object.getOwnPropertyDescriptor(document, 'exitFullscreen'),
  request: Object.getOwnPropertyDescriptor(root, 'requestFullscreen'),
};

/** The document as the browser shows it: allowed or not, what is on full screen, the two calls. */
function fake(enabled: boolean, element: Element | null = null, request: boolean = true) {
  const exit = vi.fn(() => Promise.resolve());
  const ask = vi.fn(() => Promise.resolve());
  Object.defineProperty(document, 'fullscreenEnabled', { configurable: true, get: () => enabled });
  Object.defineProperty(document, 'fullscreenElement', { configurable: true, get: () => element });
  Object.defineProperty(document, 'exitFullscreen', { configurable: true, value: exit });
  Object.defineProperty(root, 'requestFullscreen', { configurable: true, value: request ? ask : undefined });
  return { exit, ask };
}

afterEach(() => {
  for (const [target, key, descriptor] of [
    [document, 'fullscreenEnabled', saved.enabled],
    [document, 'fullscreenElement', saved.element],
    [document, 'exitFullscreen', saved.exit],
    [root, 'requestFullscreen', saved.request],
  ] as const) {
    if (descriptor) Object.defineProperty(target, key, descriptor);
    else delete (target as unknown as Record<string, unknown>)[key];
  }
});

describe('fullscreen', () => {
  it('is capable only when the document allows it and can ask for it', () => {
    fake(true);
    expect(isCapable()).toBe(true);
    fake(false);
    expect(isCapable()).toBe(false);
    fake(true, null, false);
    expect(isCapable()).toBe(false);
  });

  it('is active while the document is on full screen', () => {
    fake(true, document.documentElement);
    expect(isActive()).toBe(true);
    fake(true, null);
    expect(isActive()).toBe(false);
  });

  it('toggles the whole document: asks for full screen on it, or leaves full screen', async () => {
    const off = fake(true, null);
    await toggle();
    expect(off.ask).toHaveBeenCalledOnce();
    expect(off.ask.mock.contexts[0]).toBe(document.documentElement);
    expect(off.exit).not.toHaveBeenCalled();
    const on = fake(true, document.documentElement);
    await toggle();
    expect(on.exit).toHaveBeenCalledOnce();
    expect(on.ask).not.toHaveBeenCalled();
  });

  it('a refusal of the browser (no user gesture, policy) does not throw: the state just stays', async () => {
    const { ask } = fake(true, null);
    ask.mockRejectedValueOnce(new TypeError('denied'));
    await expect(toggle()).resolves.toBeUndefined();
  });

  it('says every change of state until it is unsubscribed', () => {
    const seen = vi.fn();
    const stop = onChange(seen);
    document.dispatchEvent(new Event('fullscreenchange'));
    expect(seen).toHaveBeenCalledOnce();
    stop();
    document.dispatchEvent(new Event('fullscreenchange'));
    expect(seen).toHaveBeenCalledOnce();
  });
});
