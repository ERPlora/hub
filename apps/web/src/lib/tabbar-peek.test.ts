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
function fakeSegment(geometry: TabbarGeometry): HTMLElement {
  const segment = document.createElement('ion-segment');
  const pitch = () => {
    const declared = segment.style.getPropertyValue('--ok-tabbar-min');
    const width = declared ? Number.parseFloat(declared) : geometry.tabWidth;
    return { width, pitch: width + (geometry.tabPitch - geometry.tabWidth) };
  };
  for (let i = 0; i < geometry.tabCount; i += 1) {
    const tab = document.createElement('ion-segment-button');
    Object.defineProperty(tab, 'offsetLeft', {
      get: () => geometry.firstTabLeft + i * pitch().pitch,
    });
    Object.defineProperty(tab, 'offsetWidth', { get: () => pitch().width });
    segment.appendChild(tab);
  }
  Object.defineProperty(segment, 'clientWidth', { get: () => geometry.visibleWidth });
  Object.defineProperty(segment, 'scrollWidth', {
    get: () => geometry.firstTabLeft * 2 + geometry.tabCount * pitch().pitch - (pitch().pitch - pitch().width),
  });
  document.body.appendChild(segment);
  return segment;
}

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
    // The width it publishes becomes the width it would measure next time. Without re-reading the
    // strip's declared floor first, every recompute would shrink the tabs a little further.
    const segment = fakeSegment(SETTINGS_390);
    bindTabbarPeek(segment)();
    const once = bindTabbarPeek(segment);
    const first = segment.style.getPropertyValue('--ok-tabbar-min');
    once();

    const twice = bindTabbarPeek(segment);
    expect(segment.style.getPropertyValue('--ok-tabbar-min')).toBe(first);
    twice();
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
