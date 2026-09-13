// @vitest-environment happy-dom
// hub#1841 — after resizing the tabs, the edge fade is re-derived from the NEW layout.
//
// `bindTabbarPeek` publishes a tab width and then calls OutfitKit's `syncTabbarOverflow`, because
// changing the width changes `scrollWidth` and the fade on each edge depends on it. Today the strip
// overflows before and after, so removing that call leaves `data-overflow` unchanged and the suite
// green (mutant measured on rv-1837). What must hold is the ORDER: the fade is recomputed once the
// new width is on the strip — a call before it, or no call, would leave the fade describing the
// layout that was just replaced.
import { describe, expect, it, vi } from 'vitest';

const seenWidths: string[] = [];
vi.mock('@erplora/outfitkit/tabbar', () => ({
  syncTabbarOverflow: (segment: HTMLElement) => {
    seenWidths.push(segment.style.getPropertyValue('--ok-tabbar-min'));
  },
}));

import { bindTabbarPeek, peekTabWidth, type TabbarGeometry } from './tabbar-peek';

const SETTINGS_390: TabbarGeometry = {
  visibleWidth: 382,
  contentWidth: 464,
  firstTabLeft: 4,
  tabWidth: 88,
  tabPitch: 92,
  tabCount: 5,
};

function strip(geometry: TabbarGeometry): HTMLElement {
  const segment = document.createElement('ion-segment');
  for (let i = 0; i < geometry.tabCount; i += 1) {
    const tab = document.createElement('ion-segment-button');
    Object.defineProperty(tab, 'offsetLeft', { get: () => geometry.firstTabLeft + i * geometry.tabPitch });
    Object.defineProperty(tab, 'offsetWidth', { get: () => geometry.tabWidth });
    segment.appendChild(tab);
  }
  Object.defineProperty(segment, 'clientWidth', { get: () => geometry.visibleWidth });
  Object.defineProperty(segment, 'scrollWidth', { get: () => geometry.contentWidth });
  document.body.appendChild(segment);
  return segment;
}

describe('bindTabbarPeek re-derives the edge fade after publishing the width (hub#1841)', () => {
  it('calls syncTabbarOverflow with the new width already on the strip', () => {
    seenWidths.length = 0;
    const unbind = bindTabbarPeek(strip(SETTINGS_390));

    expect(seenWidths.length, 'the fade was never re-derived after the tabs changed width').toBeGreaterThan(0);
    expect(seenWidths.at(-1)).toBe(`${peekTabWidth(SETTINGS_390)}px`);
    unbind();
  });
});
