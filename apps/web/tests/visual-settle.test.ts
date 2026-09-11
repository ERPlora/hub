// Guard for the icon settle point of the visual contract (ERPlora/hub#1823).
//
// Two things move after a screen looks finished, and both were photographed mid-flight until
// hub#1823 made the budget tight enough to see them.
//
// ── WHAT THIS EXISTS TO STOP ─────────────────────────────────────────────────────────────────
// `ion-icon` injects its `<svg>` ASYNCHRONOUSLY — ionicons resolves the glyph off an
// IntersectionObserver, a frame or two after the element is in the DOM and laid out. The visual
// specs settle on `ok-widget-board` being visible, and measured on 2026-09-11 against the real
// bench (12 consecutive loads of /dashboard at 390px), ONE on-screen icon was still glyph-less at
// that moment in SEVEN of them: the hamburger inside `ion-menu-button`. It paints ~10 ms later.
//
// With the old budget (`maxDiffPixelRatio: 0.002` = 658 px at 390x844) that hole was invisible.
// With the absolute 20 px budget of hub#1823 it is not: the missing hamburger is 69 px, so the
// capture goes RED — measured twice in twelve runs of the whole contract. A contract that reds at
// random is the disease hub#1752 was closing, so the budget could not land without this.
//
// ── WHY THE PREDICATE IS TESTED THROUGH `new Function` ───────────────────────────────────────
// `page.waitForFunction(everyOnScreenIconIsPainted)` does not ship the function: Playwright ships
// its SOURCE (`toString()`) and the browser rebuilds it there, with no module scope around it. A
// helper pulled in from an import would therefore blow up at runtime — inside the browser, where
// the failure reads as a timeout and not as the `ReferenceError` it is. Rebuilding the function
// from its own source here is what keeps that honest: these cases exercise exactly what the
// browser will run.
import { describe, expect, it } from 'vitest';

import { everyOnScreenIconIsPainted, everyScrollerHasStoppedMoving, shellChromeHasSettled } from './e2e/visual-settle.ts';

interface FakeNode {
  tagName: string;
  shadowRoot?: FakeRoot | null;
  rect?: { width: number; height: number; top: number; left: number };
}

interface FakeRoot {
  children: FakeNode[];
  svg: boolean;
}

const VIEWPORT = { innerWidth: 390, innerHeight: 844 };

/** An `<svg>` the walker may run into; it is a leaf, and never an icon. */
const SVG: FakeNode = { tagName: 'svg' };

/** An `ion-icon` with its glyph already injected. */
function painted(rect?: FakeNode['rect']): FakeNode {
  return { tagName: 'ion-icon', rect, shadowRoot: { children: [SVG], svg: true } };
}

/** An `ion-icon` that is in the DOM and laid out, but whose glyph has not arrived yet. */
function unpainted(rect?: FakeNode['rect']): FakeNode {
  return { tagName: 'ion-icon', rect, shadowRoot: { children: [], svg: false } };
}

/** A host with a shadow DOM of its own — `ion-menu-button`, which is where the defect lives. */
function host(children: FakeNode[]): FakeNode {
  return { tagName: 'ion-menu-button', rect: { width: 40, height: 40, top: 12, left: 8 }, shadowRoot: { children, svg: false } };
}

const ON_SCREEN = { width: 24, height: 24, top: 20, left: 12 };

/**
 * Runs the predicate the way the BROWSER will: rebuilt from its own source, with `document` and
 * `window` as the only things it may reach for.
 */
function runAgainst(tree: FakeNode[], viewport = VIEWPORT): boolean {
  const decorate = (node: FakeNode): unknown => ({
    tagName: node.tagName,
    getBoundingClientRect: () => ({
      width: node.rect?.width ?? 0,
      height: node.rect?.height ?? 0,
      top: node.rect?.top ?? 0,
      left: node.rect?.left ?? 0,
      bottom: (node.rect?.top ?? 0) + (node.rect?.height ?? 0),
      right: (node.rect?.left ?? 0) + (node.rect?.width ?? 0),
    }),
    shadowRoot:
      node.shadowRoot === undefined || node.shadowRoot === null
        ? null
        : {
            querySelectorAll: () => node.shadowRoot!.children.map(decorate),
            querySelector: (selector: string) => (selector === 'svg' && node.shadowRoot!.svg ? {} : null),
          },
  });
  const fakeDocument = { querySelectorAll: () => tree.map(decorate) };
  const rebuild = new Function('document', 'window', `return (${everyOnScreenIconIsPainted.toString()})();`);
  return rebuild(fakeDocument, viewport) as boolean;
}

describe('the icon settle point of the visual contract (hub#1823)', () => {
  it('says YES when every on-screen icon already has its glyph', () => {
    expect(runAgainst([painted(ON_SCREEN), painted(ON_SCREEN)])).toBe(true);
  });

  it('REGRESSION: says NO while an on-screen icon is still glyph-less', () => {
    // The capture taken at this instant is the one that came back 69 px different.
    expect(runAgainst([painted(ON_SCREEN), unpainted(ON_SCREEN)])).toBe(false);
  });

  it('REGRESSION: looks INSIDE shadow roots, where the icon that actually flaked lives', () => {
    // The hamburger is `ion-menu-button`'s own `ion-icon`, so `document.querySelectorAll` does not
    // reach it. A predicate that does not pierce shadow DOM returns a confident YES here and the
    // settle point goes back to being decorative — that is this case detecting its own positive.
    expect(runAgainst([host([unpainted(ON_SCREEN)])])).toBe(false);
    expect(runAgainst([host([painted(ON_SCREEN)])])).toBe(true);
  });

  it('ignores what the capture cannot show, so the wait can never hang', () => {
    // Off-screen icons are never loaded by ionicons (IntersectionObserver), and a capture is the
    // viewport, not the page. Waiting on them would turn this helper into a 30 s timeout.
    expect(runAgainst([unpainted({ width: 24, height: 24, top: 2000, left: 12 })])).toBe(true);
    expect(runAgainst([unpainted({ width: 24, height: 24, top: 20, left: 900 })])).toBe(true);
    expect(runAgainst([unpainted({ width: 0, height: 0, top: 0, left: 0 })])).toBe(true);
    expect(runAgainst([unpainted()])).toBe(true);
  });

  it('counts an icon with no shadow root at all as not painted yet', () => {
    // Between `<ion-icon>` being parsed and Stencil upgrading it there is no shadow root, and
    // nothing on screen either — the state right before the glyph, not a state to capture in.
    expect(runAgainst([{ tagName: 'ion-icon', rect: ON_SCREEN, shadowRoot: null }])).toBe(false);
  });
});

interface FakeChrome {
  menu: boolean;
  button: 'absent' | 'shown' | 'hidden';
  splitPaneVisible: boolean;
}

/** Runs the chrome predicate the way the browser will: rebuilt from its own source. */
function chromeSettled(chrome: FakeChrome): boolean {
  const nodes: Record<string, unknown> = {};
  if (chrome.menu) nodes['ion-menu'] = { tagName: 'ion-menu' };
  if (chrome.button !== 'absent') nodes['ion-menu-button'] = { tagName: 'ion-menu-button' };
  nodes['ion-split-pane'] = {
    tagName: 'ion-split-pane',
    classList: { contains: (name: string) => name === 'split-pane-visible' && chrome.splitPaneVisible },
  };
  const fakeDocument = { querySelector: (selector: string) => nodes[selector] ?? null };
  const fakeWindow = {
    getComputedStyle: () => ({ display: chrome.button === 'shown' ? 'block' : 'none' }),
  };
  const rebuild = new Function('document', 'window', `return (${shellChromeHasSettled.toString()})();`);
  return rebuild(fakeDocument, fakeWindow) as boolean;
}

describe('the shell chrome settle point of the visual contract (hub#1823)', () => {
  it('REGRESSION: says NO while the phone still has no way into the menu', () => {
    // The state measured on 8 of 8 fresh loads of /settings at 390px: the drawer is in the DOM,
    // the split pane is not showing it, and Ionic still has `ion-menu-button` at `display: none`
    // because the menu has not registered yet. It flips to `block` between 200 ms and 1.5 s —
    // long after the card the spec settles on. A capture taken here is missing the hamburger, and
    // that is 69 px: red under the 20 px budget, invisible under the old ratio.
    expect(chromeSettled({ menu: true, button: 'hidden', splitPaneVisible: false })).toBe(false);
  });

  it('says YES once the hamburger is on screen (phone and tablet)', () => {
    expect(chromeSettled({ menu: true, button: 'shown', splitPaneVisible: false })).toBe(true);
  });

  it('says YES on a desktop, where the sidebar IS the menu and the button stays hidden', () => {
    // At 1440 the split pane shows the drawer inline (`when="lg"`), so Ionic keeps the button
    // hidden for good. Demanding a hamburger here would hang every 1440 capture.
    expect(chromeSettled({ menu: true, button: 'hidden', splitPaneVisible: true })).toBe(true);
  });

  it('REGRESSION: says NO while BOTH doors are on screen at once', () => {
    // The other half of the flip: a hamburger still painted over an already-open split pane is a
    // frame in transit, not a screen. Without this the 1440 captures settle on the wrong instant.
    expect(chromeSettled({ menu: true, button: 'shown', splitPaneVisible: true })).toBe(false);
  });

  it('says YES on a screen with no drawer chrome at all, like the login', () => {
    // `ion-menu` and the topbar both live inside <AuthenticatedChrome>, so the login screen has
    // neither. Nothing to resolve there, and waiting would hang the login captures.
    expect(chromeSettled({ menu: false, button: 'absent', splitPaneVisible: false })).toBe(true);
  });

  it('REGRESSION: says NO while the chrome is only half mounted', () => {
    // One of the two present means <AuthenticatedChrome> is mid-render: keep waiting, or the
    // capture freezes whichever half arrived first.
    expect(chromeSettled({ menu: true, button: 'absent', splitPaneVisible: false })).toBe(false);
    expect(chromeSettled({ menu: false, button: 'hidden', splitPaneVisible: false })).toBe(false);
  });
});

// ── THE THIRD SETTLE POINT: A TABBAR THAT SCROLLS ITSELF ─────────────────────────────────────
//
// `ion-segment[scrollable]` (the tabbar of /settings, /system, /employees and every module screen)
// nudges its own scroll position after it mounts, to hint that there are more tabs off-screen.
// Measured on 2026-09-11 against the real bench, /settings at 390px, polling every ~50 ms:
//
//     469ms scroll=0    ← the tabbar exists and is still
//     772ms scroll=0    ← chrome=OK icons=OK: the OTHER TWO predicates already say "capture now"
//     889ms scroll=14   ← the hint starts, AFTER the settle point
//     947ms scroll=28
//    1251ms scroll=28
//    1309ms scroll=13
//    1368ms scroll=0    ← back to rest, and still there at 3.8 s
//
// So a capture can land on 0, on 14, on 28 or on 13 depending on how fast the machine is, and the
// two quiet positions (before the hint and after it) are the SAME pixels. On the GitHub Linux
// runner it lands at 28 and on this Mac at 0 — a 5.239 px difference on one screen, which the old
// ratio budget swallowed (658 px at 390x844) and the 20 px budget reports as red.
//
// It is not enough to see the scroll standing still: at 772 ms it had been standing still for
// 300 ms and was about to move. What settles the screen is the position holding for LONGER than
// the hint takes to start (420 ms measured) — hence the 600 ms quiet window.
interface FakeScroller {
  key: string;
  scrollLeft: number;
  scrollWidth: number;
  clientWidth: number;
  inShadowRootOf?: string;
  /** What the browser computes for `overflow-x`; anything but `auto`/`scroll` cannot scroll. */
  overflow?: string;
}

/**
 * Drives the scroll predicate through a TIMELINE, the way `waitForFunction` polls it: same page,
 * same `window` stash between calls, a clock that only moves forward. Returns what the predicate
 * answered at each step.
 */
function scrollTimeline(steps: { at: number; scrollers: FakeScroller[] }[]): boolean[] {
  const stash: Record<string, unknown> = {};
  let clock = 0;
  const fakeWindow = stash;
  const fakePerformance = { now: () => clock };
  const answers: boolean[] = [];
  const rebuild = new Function(
    'document',
    'window',
    'performance',
    `return (${everyScrollerHasStoppedMoving.toString()})();`,
  );
  for (const step of steps) {
    clock = step.at;
    const styles = new Map<unknown, { overflowX: string; overflowY: string }>();
    const decorate = (s: FakeScroller): unknown => {
      const node = {
        tagName: 'div',
        scrollLeft: s.scrollLeft,
        scrollWidth: s.scrollWidth,
        clientWidth: s.clientWidth,
        getAttribute: () => s.key,
        shadowRoot: null,
      };
      styles.set(node, { overflowX: s.overflow ?? 'auto', overflowY: s.overflow ?? 'auto' });
      return node;
    };
    const roots = step.scrollers.filter((s) => s.inShadowRootOf === undefined).map(decorate);
    const hosts = step.scrollers
      .filter((s) => s.inShadowRootOf !== undefined)
      .map((s) => ({
        tagName: s.inShadowRootOf!,
        scrollLeft: 0,
        scrollWidth: 0,
        clientWidth: 0,
        getAttribute: () => null,
        shadowRoot: { querySelectorAll: () => [decorate(s)] },
      }));
    const all = [...roots, ...hosts];
    for (const host of hosts) styles.set(host, { overflowX: 'visible', overflowY: 'visible' });
    const fakeDocument = { querySelectorAll: () => all };
    (fakeWindow as { getComputedStyle?: unknown }).getComputedStyle = (node: unknown) =>
      styles.get(node) ?? { overflowX: 'visible', overflowY: 'visible' };
    answers.push(rebuild(fakeDocument, fakeWindow, fakePerformance) as boolean);
  }
  return answers;
}

const TABBAR = { key: 'tabbar', scrollWidth: 600, clientWidth: 390 };

describe('the tabbar settle point of the visual contract (hub#1823)', () => {
  it('says NO the first time it looks, because one sample cannot tell still from about-to-move', () => {
    expect(scrollTimeline([{ at: 100, scrollers: [{ ...TABBAR, scrollLeft: 0 }] }])).toEqual([false]);
  });

  it('REGRESSION: says NO at the instant the other two predicates settle, 300 ms before the hint', () => {
    // The exact measured timeline: still at 0 since 469 ms, asked at 772 ms. Answering YES here is
    // what put the Linux runner inside the animation.
    const answers = scrollTimeline([
      { at: 469, scrollers: [{ ...TABBAR, scrollLeft: 0 }] },
      { at: 772, scrollers: [{ ...TABBAR, scrollLeft: 0 }] },
    ]);
    expect(answers).toEqual([false, false]);
  });

  it('REGRESSION: says NO on the plateau of the hint, where two Linux runners both landed', () => {
    // 28 px held from 947 ms to 1251 ms — 304 ms of perfect stillness in the MIDDLE of the
    // animation. Two consecutive runs of the regeneration workflow both photographed it, which is
    // exactly why "the two runs agree" is not evidence that a capture point is stable.
    const answers = scrollTimeline([
      { at: 889, scrollers: [{ ...TABBAR, scrollLeft: 14 }] },
      { at: 947, scrollers: [{ ...TABBAR, scrollLeft: 28 }] },
      { at: 1251, scrollers: [{ ...TABBAR, scrollLeft: 28 }] },
    ]);
    expect(answers).toEqual([false, false, false]);
  });

  it('says YES once the position has held longer than the hint takes to start', () => {
    const answers = scrollTimeline([
      { at: 1368, scrollers: [{ ...TABBAR, scrollLeft: 0 }] },
      { at: 1800, scrollers: [{ ...TABBAR, scrollLeft: 0 }] },
      { at: 1969, scrollers: [{ ...TABBAR, scrollLeft: 0 }] },
    ]);
    expect(answers).toEqual([false, false, true]);
  });

  it('REGRESSION: a tabbar that arrives LATE resets the wait instead of being missed', () => {
    // The tabbar of a module screen is not in the first paint: at 277 ms there was no segment at
    // all. A predicate that only compared positions would have called the empty page "quiet" and
    // captured before the tabbar existed.
    const answers = scrollTimeline([
      { at: 100, scrollers: [] },
      { at: 800, scrollers: [] },
      { at: 850, scrollers: [{ ...TABBAR, scrollLeft: 0 }] },
      { at: 900, scrollers: [{ ...TABBAR, scrollLeft: 0 }] },
      { at: 1500, scrollers: [{ ...TABBAR, scrollLeft: 0 }] },
    ]);
    expect(answers).toEqual([false, true, false, false, true]);
  });

  it('REGRESSION: looks INSIDE shadow roots, where the scrolling element of ion-segment lives', () => {
    // `ion-segment` does not scroll: the `.segment-scroll` inside its shadow root does.
    // `document.querySelectorAll('*')` never returns it.
    const answers = scrollTimeline([
      { at: 100, scrollers: [{ ...TABBAR, scrollLeft: 0, inShadowRootOf: 'ion-segment' }] },
      { at: 200, scrollers: [{ ...TABBAR, scrollLeft: 28, inShadowRootOf: 'ion-segment' }] },
      { at: 900, scrollers: [{ ...TABBAR, scrollLeft: 28, inShadowRootOf: 'ion-segment' }] },
    ]);
    expect(answers).toEqual([false, false, true]);
  });

  it('REGRESSION: ignores a box that OVERFLOWS but cannot scroll, like the dashboard meter', () => {
    // Measured on /dashboard: the `buffer-circles-container` inside the `ion-progress-bar` of the
    // setup card animates FOREVER, and its `scrollWidth` breathes around its `clientWidth`
    // (321 px): 330, 327, 323, 330... So a box that merely overflows kept entering and leaving the
    // set, the key never repeated, and the three dashboard captures died on the 5 s timeout
    // instead of settling. What makes a box a scroller is the browser being able to scroll it —
    // `overflow: auto|scroll` — not its content happening not to fit. That meter is
    // `overflow: hidden`, and so are the other two boxes that flickered.
    const breathing = (w: number): FakeScroller[] => [
      { key: 'meter', scrollLeft: 0, scrollWidth: w, clientWidth: 321, overflow: 'hidden' },
    ];
    const answers = scrollTimeline([
      { at: 100, scrollers: breathing(330) },
      { at: 300, scrollers: breathing(321) },
      { at: 500, scrollers: breathing(327) },
      { at: 800, scrollers: breathing(323) },
    ]);
    expect(answers).toEqual([false, false, false, true]);
  });

  it('ignores what cannot scroll, so a screen without a tabbar is not held back by its own layout', () => {
    // Every element is asked for its scroll position; only the ones with something to scroll are
    // part of the invariant. Without this cut, a page full of `overflow: hidden` boxes would make
    // the key change on every relayout and the wait would never end.
    const answers = scrollTimeline([
      { at: 100, scrollers: [{ key: 'fits', scrollLeft: 0, scrollWidth: 390, clientWidth: 390 }] },
      { at: 700, scrollers: [{ key: 'fits', scrollLeft: 99, scrollWidth: 390, clientWidth: 390 }] },
    ]);
    expect(answers).toEqual([false, true]);
  });
});
