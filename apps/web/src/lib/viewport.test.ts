// @vitest-environment happy-dom
// The shell's ONE answer to "is there room beside the title?".
//
// The topbar of a till is not a page header: on a phone it holds a menu button, the title of the
// screen and every global action of the product at once, and Ionic centres the title in `ios` mode
// — so the actions do not push it, they COVER it. Reported by Ioan on a 390px screen (2026-08-09).
//
// The width has to be a reactive value and not a media query in the stylesheet because what changes
// is not how the buttons LOOK: below the threshold they are not buttons at all, they are rows of an
// overflow menu. `display:none` would leave every one of them in the tab order and announced.
import { beforeEach, describe, expect, it, vi } from 'vitest';

type Listener = (event: MediaQueryListEvent) => void;

/** A `MediaQueryList` we can move by hand: happy-dom will not resize a viewport for us. */
function installMatchMedia(matches: boolean): { fire: (matches: boolean) => void; media: () => string } {
  const listeners: Listener[] = [];
  let media = '';
  const mql = {
    get matches() {
      return matches;
    },
    addEventListener: (_type: string, cb: Listener) => {
      listeners.push(cb);
    },
  };
  window.matchMedia = vi.fn((query: string) => {
    media = query;
    return mql as unknown as MediaQueryList;
  }) as unknown as typeof window.matchMedia;
  return {
    fire: (next: boolean) => {
      matches = next;
      for (const cb of listeners) cb({ matches: next } as MediaQueryListEvent);
    },
    media: () => media,
  };
}

/** Re-imports the module so the binding it does at load runs against the stub just installed. */
const load = async () => {
  vi.resetModules();
  return import('./viewport');
};

beforeEach(() => {
  vi.unstubAllGlobals();
});

describe('the width the shell reads', () => {
  it('is already known at the first render — a topbar that starts wide would flash its buttons', async () => {
    installMatchMedia(true);

    const { isCompactViewport } = await load();

    expect(isCompactViewport.value).toBe(true);
  });

  it('follows the screen live: turning a phone sideways gives the actions their room back', async () => {
    const screen = installMatchMedia(true);
    const { isCompactViewport } = await load();

    screen.fire(false);

    expect(isCompactViewport.value).toBe(false);
  });

  it('asks about the width at which the toolbar actually runs out, not an invented one', async () => {
    const screen = installMatchMedia(false);

    const { COMPACT_VIEWPORT_QUERY } = await load();

    // Ionic's own `md` step: from a tablet up the title and the actions fit side by side.
    expect(COMPACT_VIEWPORT_QUERY).toBe('(max-width: 767px)');
    expect(screen.media()).toBe(COMPACT_VIEWPORT_QUERY);
  });

  it('boots on a runtime without `matchMedia` instead of taking the shell down with it', async () => {
    // @ts-expect-error — deliberately modelling a runtime that has no media queries at all.
    window.matchMedia = undefined;

    const { isCompactViewport } = await load();

    // Wide is the safe default: every action stays reachable in the toolbar.
    expect(isCompactViewport.value).toBe(false);
  });
});
