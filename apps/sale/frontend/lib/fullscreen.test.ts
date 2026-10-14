// The browser's Fullscreen API, wrapped once for the till (WORKBOOK «Vender»: the ⋮ menu's «Full
// screen» / «Exit full screen», the browser's, when the device allows it): whether the device can,
// whether the till element is the one on full screen, the toggle and the change of state (Esc, F11).
import { afterEach, describe, expect, it, vi } from 'vitest';

import { isActive, isCapable, onChange, toggle } from './fullscreen';

type FullscreenDoc = {
  fullscreenEnabled?: boolean;
  fullscreenElement?: Element | null;
  exitFullscreen?: () => Promise<void>;
};

const doc = document as unknown as FullscreenDoc;
const saved = {
  enabled: Object.getOwnPropertyDescriptor(document, 'fullscreenEnabled'),
  element: Object.getOwnPropertyDescriptor(document, 'fullscreenElement'),
  exit: Object.getOwnPropertyDescriptor(document, 'exitFullscreen'),
};

function fake(enabled: boolean, element: Element | null = null): { exit: ReturnType<typeof vi.fn> } {
  const exit = vi.fn(() => Promise.resolve());
  Object.defineProperty(document, 'fullscreenEnabled', { configurable: true, get: () => enabled });
  Object.defineProperty(document, 'fullscreenElement', { configurable: true, get: () => element });
  Object.defineProperty(document, 'exitFullscreen', { configurable: true, value: exit });
  return { exit };
}

function till(): HTMLElement & { requestFullscreen: ReturnType<typeof vi.fn> } {
  const el = document.createElement('div') as unknown as HTMLElement & { requestFullscreen: ReturnType<typeof vi.fn> };
  el.requestFullscreen = vi.fn(() => Promise.resolve());
  return el;
}

afterEach(() => {
  for (const [key, descriptor] of [
    ['fullscreenEnabled', saved.enabled],
    ['fullscreenElement', saved.element],
    ['exitFullscreen', saved.exit],
  ] as const) {
    if (descriptor) Object.defineProperty(document, key, descriptor);
    else delete (doc as Record<string, unknown>)[key];
  }
});

describe('fullscreen', () => {
  it('is capable only when the document allows it and the element can ask for it', () => {
    fake(true);
    expect(isCapable(till())).toBe(true);
    expect(isCapable(document.createElement('div'))).toBe(false);
    fake(false);
    expect(isCapable(till())).toBe(false);
    expect(isCapable(null)).toBe(false);
  });

  it('is active only while that very element is the one on full screen', () => {
    const el = till();
    fake(true, el);
    expect(isActive(el)).toBe(true);
    expect(isActive(till())).toBe(false);
    fake(true, null);
    expect(isActive(el)).toBe(false);
  });

  it('toggles: asks for full screen on the element, or leaves it when the element already is', async () => {
    const el = till();
    const { exit } = fake(true, null);
    await toggle(el);
    expect(el.requestFullscreen).toHaveBeenCalledOnce();
    expect(exit).not.toHaveBeenCalled();
    const second = fake(true, el);
    await toggle(el);
    expect(second.exit).toHaveBeenCalledOnce();
    expect(el.requestFullscreen).toHaveBeenCalledOnce();
  });

  it('a refusal of the browser (no user gesture, policy) does not throw: the state just stays', async () => {
    const el = till();
    el.requestFullscreen.mockRejectedValueOnce(new TypeError('denied'));
    fake(true, null);
    await expect(toggle(el)).resolves.toBeUndefined();
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
