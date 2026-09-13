/**
 * Footer tab strip — make an overflowing strip SHOW that it continues (hub#1830).
 *
 * OutfitKit already paints a 36px fade over the edge that hides tabs (`tabbar.css`,
 * `data-overflow`), and hub#1829 added a movement hint when the screen opens. Neither is enough on
 * its own: the hint lasts under half a second, and the fade only shows where there is something to
 * fade. A tab's icon and label are CENTRED, so when the cut leaves a narrow sliver of the next tab
 * the fade falls on empty background and the strip reads, at rest, exactly like a strip that ends
 * there — what NN/g calls the illusion of completeness. Measured on `/settings` at 390px: a 10px
 * sliver of an 88px tab whose label only starts 3px off screen.
 *
 * What the market does on a mobile strip that does not fit is leave the next tab genuinely PEEKING,
 * cut through its own content: Material's scrollable tabs, Apple's partially visible tab, the
 * carousel of display groups in Lightspeed Restaurant. The enterprise web (Polaris, Fluent,
 * PatternFly) moves the extra tabs into a «More» menu instead — that is a desktop answer, and it
 * hides the tabs behind one more tap, which Apple's own guidance warns about.
 *
 * So: pick the tab width that makes the cut fall past the centre of the first hidden tab. The width
 * is published in OutfitKit's own public token, `--ok-tabbar-min`, which is exactly what it is for
 * («cada producto puede ajustarlo»); the strip keeps scrolling and no tab is hidden behind anything.
 */
import { syncTabbarOverflow } from '@erplora/outfitkit/tabbar';

/** OutfitKit's token for the narrowest a tab may be before the strip starts scrolling. */
const PEEK_PROPERTY = '--ok-tabbar-min';

/**
 * How far PAST the first hidden tab's centre the cut has to fall, in pixels.
 *
 * Half of the 24px footer icon. Landing exactly on the centre already guarantees ink under the
 * fade, but it is the worst possible place for it: the fade is 36px wide and reaches zero opacity
 * at the very edge, so a cut on the centre leaves only the icon's inner half, in the last 12px,
 * at under a third of its opacity. Twelve more pixels put the whole leading half of the tab on
 * screen, where the fade dims it instead of erasing it.
 */
const PEEK_MARGIN_PX = 12;

/** Sub-pixel slack: `scrollWidth` and `clientWidth` are rounded differently by the engine. */
const EPSILON = 1;

/** What a footer tab strip looks like right now, in the strip's own `offsetLeft` coordinates. */
export interface TabbarGeometry {
  /** `clientWidth`: how much of the strip the person can see. */
  visibleWidth: number;
  /** `scrollWidth`: how much the tabs really need. */
  contentWidth: number;
  /** `offsetLeft` of the first tab — the strip's leading padding. */
  firstTabLeft: number;
  /** `offsetWidth` of a tab. Every tab is one grid column, so they all share it. */
  tabWidth: number;
  /** Distance between the left edges of two consecutive tabs: `tabWidth` plus the gap. */
  tabPitch: number;
  /** How many tabs the strip holds. */
  tabCount: number;
}

/** Index of the first tab the cut leaves incomplete, or `null` when every tab fits. */
function firstHiddenTab(geometry: TabbarGeometry): number | null {
  for (let index = 0; index < geometry.tabCount; index += 1) {
    const right = geometry.firstTabLeft + index * geometry.tabPitch + geometry.tabWidth;
    if (right > geometry.visibleWidth) return index;
  }
  return null;
}

/**
 * Is the strip hiding tabs without showing it?
 *
 * True when the cut falls SHORT of the first hidden tab's centre — the sliver on screen is padding,
 * so there is nothing for the edge fade to fade and nothing that reads as «this continues».
 */
export function hidesTabsSilently(geometry: TabbarGeometry): boolean {
  if (geometry.contentWidth <= geometry.visibleWidth + EPSILON) return false;

  const hidden = firstHiddenTab(geometry);
  if (hidden === null) return false;

  const centre = geometry.firstTabLeft + hidden * geometry.tabPitch + geometry.tabWidth / 2;
  return centre > geometry.visibleWidth;
}

/**
 * The tab width that leaves the first hidden tab peeking, or `null` when there is nothing to say.
 *
 * Solves, for a strip that shows `whole` complete tabs and then the cut:
 *
 *     firstTabLeft + whole · (width + gap) + width / 2 = visibleWidth − PEEK_MARGIN_PX
 *
 * and takes the largest `whole` whose answer still respects the width the tabs already had — that
 * floor is what keeps a label from being squeezed, and it is set per product (88px in OutfitKit,
 * 116px for a module screen). Fewer whole tabs means wider ones; showing at least one whole tab
 * plus the peek is the floor of the search, and when not even that fits at the floor, the floor
 * stands and there is no peek (hub#1841) — a squeezed label is worse than a strip that does not hint.
 */
export function peekTabWidth(geometry: TabbarGeometry): number | null {
  if (geometry.contentWidth <= geometry.visibleWidth + EPSILON) return null;
  if (geometry.tabCount < 2) return null;

  const gap = geometry.tabPitch - geometry.tabWidth;
  const room = geometry.visibleWidth - PEEK_MARGIN_PX - geometry.firstTabLeft;

  const widthFor = (whole: number): number => (room - whole * gap) / (whole + 0.5);

  let chosen: number | null = null;
  for (let whole = geometry.tabCount - 1; whole >= 1; whole -= 1) {
    if (widthFor(whole) >= geometry.tabWidth) {
      chosen = whole;
      break;
    }
  }
  // hub#1841: a strip too narrow for even one whole tab and the peek at the floor keeps the floor.
  // Falling back to «one whole tab» there answered a width BELOW it — squeezing the label this
  // function promises never to squeeze. No peek is better than a broken label.
  if (chosen === null) return geometry.tabWidth;

  // Rounded DOWN: a narrower tab moves the cut further past the centre, never short of it, so the
  // margin above survives the engine's own rounding of the column width.
  const width = Math.floor(widthFor(chosen) * 100) / 100;
  return Number.isFinite(width) && width > 0 ? width : null;
}

/** Reads the live geometry of a strip. `null` when there is not enough of it to measure a pitch. */
function readTabbarGeometry(segment: HTMLElement): TabbarGeometry | null {
  const tabs = segment.querySelectorAll<HTMLElement>('ion-segment-button');
  const first = tabs[0];
  const second = tabs[1];
  if (!first || !second) return null;

  return {
    visibleWidth: segment.clientWidth,
    contentWidth: segment.scrollWidth,
    firstTabLeft: first.offsetLeft,
    tabWidth: first.offsetWidth,
    tabPitch: second.offsetLeft - first.offsetLeft,
    tabCount: tabs.length,
  };
}

/**
 * Keeps a strip's tabs sized so the overflow stays visible. Returns its cleanup.
 *
 * Recomputes when the strip changes width (rotating the phone, folding the menu) and when the
 * number of tabs changes without it (a module whose `navigation[]` arrives over the network).
 * Every pass starts by dropping the width it published last time: the floor it has to respect is
 * the one the STYLESHEET declares. Measuring its own previous answer instead would make the floor
 * a ratchet — it could only ever climb, and a higher floor fits fewer whole tabs, so each round
 * trip of the phone would take one more whole tab off the screen for good (88 → 101.14 → 118.4 →
 * 143.2 on `/settings`, measured). The width is a function of the strip, never of its last answer.
 */
export function bindTabbarPeek(segment: HTMLElement | null): () => void {
  if (!segment) return () => {};

  const apply = (): void => {
    segment.style.removeProperty(PEEK_PROPERTY);
    const geometry = readTabbarGeometry(segment);
    if (!geometry) return;

    const width = peekTabWidth(geometry);
    if (width === null) return;

    segment.style.setProperty(PEEK_PROPERTY, `${width}px`);
    // The tabs just changed width, so `scrollWidth` did too: re-derive which edges hide something.
    syncTabbarOverflow(segment);
  };

  apply();

  const resize = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(apply) : null;
  resize?.observe(segment);
  // `childList` only: `apply` writes a style attribute on the strip itself, which this never sees.
  const tabs = typeof MutationObserver !== 'undefined' ? new MutationObserver(apply) : null;
  tabs?.observe(segment, { childList: true });

  return () => {
    resize?.disconnect();
    tabs?.disconnect();
    segment.style.removeProperty(PEEK_PROPERTY);
  };
}
