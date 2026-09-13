// @vitest-environment happy-dom
// Regression test for ERPlora/hub#1830 — a footer tab strip that hides tabs WITHOUT showing it.
//
// What is on screen (measured on `/settings` at 390px, 11/09): the strip is 382px wide and needs
// 464px, so two tabs are hidden. The fifth tab starts at x=372, which leaves a 10px sliver of a
// 88px tab — and a tab's icon and label are CENTRED, so its label only starts at x=385. Nothing of
// it is on screen. OutfitKit paints a 36px fade over that edge to say «there is more», but the fade
// falls on an empty sliver: it has no ink to fade, so at rest the strip looks exactly like a strip
// that ends there (NN/g calls it the illusion of completeness).
//
// hub#1829 added a movement hint at entry, which lasts under half a second. This is the PERMANENT
// half: the strip is sized so the cut always falls PAST the centre of the first hidden tab, which
// is where its icon and label live — the market's peek (Material scrollable tabs, Apple's partial
// tab, Lightspeed's carousel of display groups).
import { describe, it, expect } from 'vitest';
import {
  bindTabbarPeek,
  hidesTabsSilently,
  peekTabWidth,
  type TabbarGeometry,
} from './tabbar-peek';

/** `/settings` at 390px, measured in Chromium on the e2e bench (5 tabs, OutfitKit's 88px floor). */
const SETTINGS_390: TabbarGeometry = {
  visibleWidth: 382,
  contentWidth: 464,
  firstTabLeft: 4,
  tabWidth: 88,
  tabPitch: 92,
  tabCount: 5,
};

/** A module screen at 390px: same strip, but `ModuleView` raises the floor to 116px (hub#1830). */
const MODULE_390: TabbarGeometry = {
  visibleWidth: 382,
  contentWidth: 604,
  firstTabLeft: 4,
  tabWidth: 116,
  tabPitch: 120,
  tabCount: 5,
};

/** Where the cut falls relative to the first hidden tab's centre. Positive = the centre is shown. */
function slackAtCut(geometry: TabbarGeometry, tabWidth: number): number {
  const pitch = tabWidth + (geometry.tabPitch - geometry.tabWidth);
  let hidden = 0;
  while (geometry.firstTabLeft + hidden * pitch + tabWidth <= geometry.visibleWidth) hidden += 1;
  const centre = geometry.firstTabLeft + hidden * pitch + tabWidth / 2;
  return geometry.visibleWidth - centre;
}

/** The geometry the strip ends up with once the computed width is applied. */
function afterPeek(geometry: TabbarGeometry): TabbarGeometry {
  const tabWidth = peekTabWidth(geometry);
  if (tabWidth === null) throw new Error('peekTabWidth returned null for an overflowing strip');
  const tabPitch = tabWidth + (geometry.tabPitch - geometry.tabWidth);
  return {
    ...geometry,
    tabWidth,
    tabPitch,
    contentWidth: geometry.firstTabLeft * 2 + geometry.tabCount * tabPitch - (tabPitch - tabWidth),
  };
}

describe('hidesTabsSilently — the defect, stated as a contract', () => {
  it('catches the strip on screen today: two tabs hidden and the cut lands on an empty sliver', () => {
    expect(hidesTabsSilently(SETTINGS_390)).toBe(true);
    // The sliver is real and it is empty: 10px of a tab whose content starts 3px off screen.
    expect(slackAtCut(SETTINGS_390, SETTINGS_390.tabWidth)).toBeLessThan(0);
  });

  it('catches it too on a module screen, where the floor is 116px', () => {
    expect(hidesTabsSilently(MODULE_390)).toBe(true);
  });

  it('says nothing when every tab fits: there is nothing to signal', () => {
    const desktop: TabbarGeometry = { ...SETTINGS_390, visibleWidth: 1200, contentWidth: 464 };
    expect(hidesTabsSilently(desktop)).toBe(false);
  });

  it('a tab that ends exactly on the edge is shown, so the hidden one is the NEXT', () => {
    // The worst case of the defect, and the cleanest: the strip ends flush with the second tab, so
    // the third is off screen ENTIRELY — not a sliver, nothing. There is no ink for the fade to
    // fade and nothing on screen suggests a third tab exists. Reading that flush tab as the first
    // hidden one would make the check answer about a tab the person can see in full, and it would
    // call this strip fine.
    expect(
      hidesTabsSilently({
        visibleWidth: 200,
        contentWidth: 500,
        firstTabLeft: 0,
        tabWidth: 100,
        tabPitch: 100,
        tabCount: 5,
      }),
    ).toBe(true);
  });

  it('the cut landing exactly on the centre is enough: half a tab is on screen', () => {
    // The boundary the whole check turns on. Exactly on the centre, the leading half of the tab —
    // where its icon starts — is on screen, so the fade has something to fade. That is the line
    // between «shows it continues» and «looks finished»; on the centre it counts as shown.
    expect(
      hidesTabsSilently({
        visibleWidth: 250,
        contentWidth: 500,
        firstTabLeft: 0,
        tabWidth: 100,
        tabPitch: 100,
        tabCount: 5,
      }),
    ).toBe(false);
  });

  it('is happy when the cut already falls past the centre of the first hidden tab', () => {
    // Same strip, one tab fewer on screen: the cut passes through the fourth tab's icon.
    const peeking: TabbarGeometry = { ...SETTINGS_390, firstTabLeft: 4, tabWidth: 100, tabPitch: 104 };
    expect(slackAtCut(peeking, 100)).toBeGreaterThan(0);
    expect(hidesTabsSilently(peeking)).toBe(false);
  });
});

describe('peekTabWidth — the width that makes the cut land on the next tab', () => {
  it('turns the silent strip of /settings into one that shows it continues', () => {
    const fixed = afterPeek(SETTINGS_390);
    expect(hidesTabsSilently(fixed)).toBe(false);
    // Still overflowing — the point is to SHOW the overflow, never to hide it by shrinking.
    expect(fixed.contentWidth).toBeGreaterThan(fixed.visibleWidth);
  });

  it('does the same on a module screen without dropping below its 116px floor', () => {
    const fixed = afterPeek(MODULE_390);
    expect(hidesTabsSilently(fixed)).toBe(false);
    expect(fixed.tabWidth).toBeGreaterThanOrEqual(MODULE_390.tabWidth);
  });

  it('leaves the whole leading half of the next tab on screen, not just its midpoint', () => {
    // 12px = half of the 24px footer icon. A cut exactly ON the centre would leave the icon's
    // visible half inside the last pixels of the 36px fade, where it is almost transparent.
    expect(slackAtCut(SETTINGS_390, peekTabWidth(SETTINGS_390) as number)).toBeGreaterThanOrEqual(12);
    expect(slackAtCut(MODULE_390, peekTabWidth(MODULE_390) as number)).toBeGreaterThanOrEqual(12);
  });

  it('keeps as many whole tabs on screen as the floor allows', () => {
    // 382px of strip at a 88px floor: three whole tabs plus the peek is the most that fits without
    // squeezing a tab below the width its label needs.
    const width = peekTabWidth(SETTINGS_390) as number;
    const pitch = width + 4;
    expect(Math.floor((SETTINGS_390.visibleWidth - 4) / pitch)).toBe(3);
  });

  it('returns null when no tab is hidden: resizing a strip that fits must not resize its tabs', () => {
    expect(peekTabWidth({ ...SETTINGS_390, visibleWidth: 1200, contentWidth: 464 })).toBeNull();
  });

  it('returns null with a single tab, where there is no next tab to peek', () => {
    expect(peekTabWidth({ ...SETTINGS_390, tabCount: 1, contentWidth: 464 })).toBeNull();
  });
});

/** A strip whose geometry we control, because happy-dom lays nothing out. */
interface FakeStrip {
  segment: HTMLElement;
  /**
   * Narrows or widens the strip and lets the binding recompute.
   *
   * happy-dom never lays anything out, so its `ResizeObserver` cannot fire — the recompute is
   * driven through the binding's OTHER trigger, a `childList` mutation, which runs the very same
   * pass. The marker node is not an `ion-segment-button`, so the tab count stays put and the only
   * thing that changed between passes is the width.
   */
  resizeTo: (visibleWidth: number) => Promise<void>;
}

function fakeStrip(geometry: TabbarGeometry): FakeStrip {
  const live = { ...geometry };
  const segment = document.createElement('ion-segment');
  const pitch = () => {
    const declared = segment.style.getPropertyValue('--ok-tabbar-min');
    const width = declared ? Number.parseFloat(declared) : live.tabWidth;
    return { width, pitch: width + (live.tabPitch - live.tabWidth) };
  };
  for (let i = 0; i < live.tabCount; i += 1) {
    const tab = document.createElement('ion-segment-button');
    Object.defineProperty(tab, 'offsetLeft', {
      get: () => live.firstTabLeft + i * pitch().pitch,
    });
    Object.defineProperty(tab, 'offsetWidth', { get: () => pitch().width });
    segment.appendChild(tab);
  }
  Object.defineProperty(segment, 'clientWidth', { get: () => live.visibleWidth });
  Object.defineProperty(segment, 'scrollWidth', {
    get: () => live.firstTabLeft * 2 + live.tabCount * pitch().pitch - (pitch().pitch - pitch().width),
  });
  document.body.appendChild(segment);

  return {
    segment,
    resizeTo: async (visibleWidth: number) => {
      live.visibleWidth = visibleWidth;
      segment.appendChild(document.createElement('span'));
      await new Promise((resolve) => setTimeout(resolve, 0));
    },
  };
}

function fakeSegment(geometry: TabbarGeometry): HTMLElement {
  return fakeStrip(geometry).segment;
}

// ── hub#1841 — the two promises the fix makes, pinned ───────────────────────────────────────

describe('peekTabWidth — the floor is a contract, not a hope (hub#1841)', () => {
  it('never answers a width below the floor, even on a strip too narrow for a tab and a peek', () => {
    // 140px: one whole 88px tab plus half of the next plus the margin does not fit. The search used
    // to fall back to one whole tab and return (140 - 12 - 4 - 4) / 1.5 = 80px — squeezing the label
    // it promises never to squeeze. Unreachable with the phones served today (the narrowest strip is
    // 312px); the invariant is what the next person who raises the floor relies on.
    const narrow: TabbarGeometry = { ...SETTINGS_390, visibleWidth: 140 };
    const width = peekTabWidth(narrow);
    expect(width).not.toBeNull();
    expect(width as number).toBeGreaterThanOrEqual(narrow.tabWidth);
  });

  it('holds the same floor on a module screen, where it is 116px', () => {
    const narrow: TabbarGeometry = { ...MODULE_390, visibleWidth: 180 };
    expect(peekTabWidth(narrow) as number).toBeGreaterThanOrEqual(MODULE_390.tabWidth);
  });
});

describe('peekTabWidth — a pixel of rounding is not an overflow (hub#1841)', () => {
  it('leaves alone a strip whose content exceeds the visible width only by the engine rounding', () => {
    // `scrollWidth` and `clientWidth` are rounded differently: a strip that fits reads one pixel wider
    // than it shows. Resizing its tabs over that would move the whole strip for nothing.
    const rounding: TabbarGeometry = {
      visibleWidth: 382,
      contentWidth: 383,
      firstTabLeft: 4,
      tabWidth: 94,
      tabPitch: 96,
      tabCount: 4,
    };
    expect(peekTabWidth(rounding)).toBeNull();
    expect(hidesTabsSilently(rounding)).toBe(false);
  });

  it('but acts on a strip that really overflows by two pixels', () => {
    const real: TabbarGeometry = {
      visibleWidth: 382,
      contentWidth: 384,
      firstTabLeft: 4,
      tabWidth: 94,
      tabPitch: 96,
      tabCount: 4,
    };
    expect(peekTabWidth(real)).not.toBeNull();
  });
});

describe('bindTabbarPeek — wiring it to a live strip', () => {
  it('publishes the width on the strip so OutfitKit lays the tabs out with it', () => {
    const segment = fakeSegment(SETTINGS_390);
    const unbind = bindTabbarPeek(segment);

    const published = Number.parseFloat(segment.style.getPropertyValue('--ok-tabbar-min'));
    expect(published).toBeCloseTo(peekTabWidth(SETTINGS_390) as number, 2);

    unbind();
    expect(segment.style.getPropertyValue('--ok-tabbar-min')).toBe('');
  });

  it('recomputes from the strip\'s OWN width, so binding twice lands on the same number', () => {
    // The width it publishes becomes the width it would measure next time, so every pass has to
    // start from the floor the STYLESHEET declares. See the round trip below for what happens
    // when it does not — this one only pins the entry point.
    const segment = fakeSegment(SETTINGS_390);
    bindTabbarPeek(segment)();
    const once = bindTabbarPeek(segment);
    const first = segment.style.getPropertyValue('--ok-tabbar-min');
    once();

    const twice = bindTabbarPeek(segment);
    expect(segment.style.getPropertyValue('--ok-tabbar-min')).toBe(first);
    twice();
  });

  it('gives the tabs their width back when the strip widens again, instead of ratcheting up', async () => {
    // Rotating the phone, folding the side menu: the strip is recomputed on a strip that is ALREADY
    // carrying the width this binding published. If a pass took that published width for its floor
    // instead of re-reading the stylesheet's, the floor could only ever climb — and the width with
    // it, because a higher floor fits fewer whole tabs. Measured on this geometry, a single narrow
    // -and-back round trip walks 88 → 101.14 → 118.4 → 143.2: the person rotates the phone twice
    // and the strip comes back showing ONE FEWER whole tab, for good. The width has to be a
    // function of the strip, not of its own last answer.
    const strip = fakeStrip(SETTINGS_390);
    const unbind = bindTabbarPeek(strip.segment);
    const at390 = strip.segment.style.getPropertyValue('--ok-tabbar-min');
    expect(at390).toBe('101.14px');

    await strip.resizeTo(320);
    expect(strip.segment.style.getPropertyValue('--ok-tabbar-min')).toBe('118.4px');

    await strip.resizeTo(382);
    expect(strip.segment.style.getPropertyValue('--ok-tabbar-min')).toBe(at390);
    unbind();
  });

  it('leaves a strip that fits alone', () => {
    const segment = fakeSegment({ ...SETTINGS_390, visibleWidth: 1200 });
    const unbind = bindTabbarPeek(segment);
    expect(segment.style.getPropertyValue('--ok-tabbar-min')).toBe('');
    unbind();
  });

  it('does nothing, and does not throw, without a strip', () => {
    expect(() => bindTabbarPeek(null)()).not.toThrow();
  });
});
