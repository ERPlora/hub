// The page's colour mode (round 2026-10-22): `data-ep-mode="auto"` follows the visitor's device. The server paints
// it light (`data-bs-theme="light"`, the page without JS); the public bundle sets Bootstrap's `data-bs-theme` from
// `prefers-color-scheme` and follows a change while the page is open. A light or a dark page is left as it is.
import { afterEach, describe, expect, it, vi } from 'vitest';

import { followColourMode } from './mode';

type Listener = (event: { matches: boolean }) => void;

function device(dark: boolean) {
  const listeners: Listener[] = [];
  const query = {
    matches: dark,
    media: '(prefers-color-scheme: dark)',
    addEventListener: vi.fn((_type: string, listener: Listener) => listeners.push(listener)),
  };
  const matchMedia = vi.fn(() => query);
  const turn = (now: boolean) => {
    query.matches = now;
    for (const listener of listeners) listener({ matches: now });
  };
  return { matchMedia, query, turn };
}

function page(mode: string, painted = 'light'): Document {
  const doc = document.implementation.createHTMLDocument('site');
  doc.documentElement.setAttribute('data-ep-mode', mode);
  doc.documentElement.setAttribute('data-bs-theme', painted);
  return doc;
}

const theme = (doc: Document) => doc.documentElement.getAttribute('data-bs-theme');

afterEach(() => {
  vi.restoreAllMocks();
});

describe('followColourMode', () => {
  it('auto on a dark device: the page turns dark', () => {
    const { matchMedia } = device(true);
    const doc = page('auto');
    followColourMode(doc, matchMedia);
    expect(matchMedia).toHaveBeenCalledWith('(prefers-color-scheme: dark)');
    expect(theme(doc)).toBe('dark');
  });

  it('auto on a light device: stays light', () => {
    const doc = page('auto');
    followColourMode(doc, device(false).matchMedia);
    expect(theme(doc)).toBe('light');
  });

  it('auto follows the device while the page is open', () => {
    const { matchMedia, query, turn } = device(false);
    const doc = page('auto');
    followColourMode(doc, matchMedia);
    expect(query.addEventListener).toHaveBeenCalledWith('change', expect.any(Function));
    turn(true);
    expect(theme(doc)).toBe('dark');
    turn(false);
    expect(theme(doc)).toBe('light');
  });

  it.each([
    ['light', 'light'],
    ['dark', 'dark'],
  ])('a %s page is left as the owner chose it, whatever the device', (mode, painted) => {
    const { matchMedia } = device(mode === 'light');
    const doc = page(mode, painted);
    followColourMode(doc, matchMedia);
    expect(matchMedia).not.toHaveBeenCalled();
    expect(theme(doc)).toBe(painted);
  });

  it('a browser without matchMedia keeps the light page it got', () => {
    const doc = page('auto');
    followColourMode(doc, undefined);
    expect(theme(doc)).toBe('light');
  });
});
