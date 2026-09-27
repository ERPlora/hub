// @vitest-environment happy-dom
// The shell's ONE answer to "is there room beside the title?" — and, since hub#1197, to "is this a
// phone?" for the two panel cards that have to fold there.
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

/**
 * A `MediaQueryList` we can move by hand: happy-dom will not resize a viewport for us.
 *
 * Query-aware since hub#1197: the module now binds TWO breakpoints at load (the topbar's and the
 * panel cards'), so a single shared `mql` would make them report the same answer for two different
 * widths. `matches` may be one bool applied to every query asked (what every test before hub#1197
 * relied on) or a per-query map for the tests that need the two breakpoints to disagree.
 */
function installMatchMedia(matches: boolean | Record<string, boolean>): {
  fire: (matches: boolean, query?: string) => void;
  media: () => string[];
} {
  const listeners = new Map<string, Listener[]>();
  const state = new Map<string, boolean>();
  const seen: string[] = [];
  const valueFor = (query: string): boolean =>
    typeof matches === 'boolean' ? matches : (matches[query] ?? false);
  window.matchMedia = vi.fn((query: string) => {
    seen.push(query);
    if (!state.has(query)) state.set(query, valueFor(query));
    const mql = {
      get matches() {
        return state.get(query)!;
      },
      addEventListener: (_type: string, cb: Listener) => {
        const arr = listeners.get(query) ?? [];
        arr.push(cb);
        listeners.set(query, arr);
      },
    };
    return mql as unknown as MediaQueryList;
  }) as unknown as typeof window.matchMedia;
  return {
    fire: (next: boolean, query = seen[seen.length - 1]) => {
      state.set(query, next);
      for (const cb of listeners.get(query) ?? []) cb({ matches: next } as MediaQueryListEvent);
    },
    media: () => seen,
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
    const { isCompactViewport, COMPACT_VIEWPORT_QUERY } = await load();

    screen.fire(false, COMPACT_VIEWPORT_QUERY);

    expect(isCompactViewport.value).toBe(false);
  });

  it('asks about the width at which the toolbar actually runs out, not an invented one', async () => {
    const screen = installMatchMedia(false);

    const { COMPACT_VIEWPORT_QUERY } = await load();

    // Ionic's own `md` step: from a tablet up the title and the actions fit side by side.
    expect(COMPACT_VIEWPORT_QUERY).toBe('(max-width: 767px)');
    expect(screen.media()).toContain(COMPACT_VIEWPORT_QUERY);
  });

  it('boots on a runtime without `matchMedia` instead of taking the shell down with it', async () => {
    // @ts-expect-error — deliberately modelling a runtime that has no media queries at all.
    window.matchMedia = undefined;

    const { isCompactViewport, isPhoneViewport } = await load();

    // Wide is the safe default: every action stays reachable in the toolbar, and no card folds.
    expect(isCompactViewport.value).toBe(false);
    expect(isPhoneViewport.value).toBe(false);
  });
});

// hub#1197 — «Mis apps» and the setup checklist together ran a 390px hub to 4.3 screens before the
// widget board even started. Both cards fold on a phone (fewer tiles, fewer rows, a way to see the
// rest), and they have to fold at the SAME width so the panel does not read as two products stitched
// together. This is that one width, read the same way the topbar already reads its own.
describe('the width the panel cards read to fold (hub#1197)', () => {
  it('is already known at the first render — a card that starts wide would flash its rows', async () => {
    installMatchMedia(true);

    const { isPhoneViewport } = await load();

    expect(isPhoneViewport.value).toBe(true);
  });

  it('follows the screen live: rotating the till gives the cards their rows back', async () => {
    const screen = installMatchMedia(true);
    const { isPhoneViewport, PHONE_VIEWPORT_QUERY } = await load();

    screen.fire(false, PHONE_VIEWPORT_QUERY);

    expect(isPhoneViewport.value).toBe(false);
  });

  it('asks about 540px — the breakpoint the setup card already used in its stylesheet', async () => {
    const screen = installMatchMedia(false);

    const { PHONE_VIEWPORT_QUERY } = await load();

    expect(PHONE_VIEWPORT_QUERY).toBe('(max-width: 540px)');
    expect(screen.media()).toContain(PHONE_VIEWPORT_QUERY);
  });

  it('is its OWN breakpoint, not the topbar one wearing a new name', async () => {
    // 600px matches the topbar's phone step (≤767px) but not the panel cards' (≤540px): a hub
    // between those two widths must fold the topbar and keep both cards at their full size.
    installMatchMedia({
      '(max-width: 767px)': true,
      '(max-width: 540px)': false,
    });

    const { isCompactViewport, isPhoneViewport } = await load();

    expect(isCompactViewport.value).toBe(true);
    expect(isPhoneViewport.value).toBe(false);
  });
});

// hub#2272 — a phone held sideways is WIDE (667px, past both width steps) and SHORT (375px). The
// blocking strip that sits over every screen took ~113px of those 375 and left the till's open
// ticket without room for a single line. The fold there is about HEIGHT, so it is its own query.
describe('the height the blocking strip reads to fold (hub#2272)', () => {
  it('is already known at the first render — a strip that starts tall would jump on every boot', async () => {
    installMatchMedia(true);

    const { isShortViewport } = await load();

    expect(isShortViewport.value).toBe(true);
  });

  it('follows the screen live: turning the phone upright gives the strip its detail back', async () => {
    const screen = installMatchMedia(true);
    const { isShortViewport, SHORT_VIEWPORT_QUERY } = await load();

    screen.fire(false, SHORT_VIEWPORT_QUERY);

    expect(isShortViewport.value).toBe(false);
  });

  it('asks about a HEIGHT of 500px: every phone on its side, no phone upright, no tablet', async () => {
    const screen = installMatchMedia(false);

    const { SHORT_VIEWPORT_QUERY } = await load();

    expect(SHORT_VIEWPORT_QUERY).toBe('(max-height: 500px)');
    expect(screen.media()).toContain(SHORT_VIEWPORT_QUERY);
  });

  it('is its OWN breakpoint: a wide landscape phone folds the strip and keeps the wide topbar', async () => {
    installMatchMedia({
      '(max-width: 767px)': false,
      '(max-width: 540px)': false,
      '(max-height: 500px)': true,
    });

    const { isCompactViewport, isPhoneViewport, isShortViewport } = await load();

    expect(isShortViewport.value).toBe(true);
    expect(isCompactViewport.value).toBe(false);
    expect(isPhoneViewport.value).toBe(false);
  });

  it('is false on a runtime without `matchMedia`: the strip stays whole', async () => {
    // @ts-expect-error — deliberately modelling a runtime that has no media queries at all.
    window.matchMedia = undefined;

    const { isShortViewport } = await load();

    expect(isShortViewport.value).toBe(false);
  });
});
