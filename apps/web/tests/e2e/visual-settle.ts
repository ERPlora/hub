// The two settle points the visual contract was missing (ERPlora/hub#1823): the shell chrome has
// decided how you get into the menu, and every icon on screen has its glyph. Guard:
// `tests/visual-settle.test.ts`.
//
// 🔴 THIS FILE RUNS IN THE BROWSER, NOT IN NODE. `page.waitForFunction` ships the SOURCE of the
// function below and the browser rebuilds it with no module scope around it, so the body may not
// reach for a single import, constant or helper of this repo — `window` and `document` are all
// it gets. Anything else fails as a `ReferenceError` inside the page, which surfaces as a bare
// timeout at the call site. That is why the guard rebuilds it through `new Function` instead of
// calling it directly: a closure sneaking in fails the test here rather than the bench there.

/**
 * Is every `ion-icon` the capture will show already carrying its `<svg>`?
 *
 * ionicons resolves a glyph off an IntersectionObserver, so an `ion-icon` exists and is laid out
 * for a frame or two BEFORE it paints anything. `ok-widget-board` being visible therefore does
 * not mean the screen is finished — measured on 2026-09-11 over 12 loads of /dashboard at 390px,
 * the hamburger of `ion-menu-button` was still empty at that point in seven of them.
 *
 * Two details carry the whole function:
 *
 *   · It walks SHADOW ROOTS. The icon that actually flakes is `ion-menu-button`'s own, which
 *     `document.querySelectorAll('ion-icon')` never returns.
 *   · It only demands a glyph from icons INTERSECTING THE VIEWPORT. A capture is the viewport,
 *     not the page, and an icon far below the fold is never loaded by ionicons at all — waiting
 *     on those would trade a rare red for a guaranteed timeout.
 */
export function everyOnScreenIconIsPainted(): boolean {
  const icons: Element[] = [];
  const walk = (root: Document | ShadowRoot): void => {
    for (const element of Array.from(root.querySelectorAll('*'))) {
      if (element.tagName.toLowerCase() === 'ion-icon') icons.push(element);
      const shadow = (element as HTMLElement).shadowRoot;
      if (shadow !== null && shadow !== undefined) walk(shadow);
    }
  };
  walk(document);

  return icons.every((icon) => {
    const rect = icon.getBoundingClientRect();
    const onScreen =
      rect.width > 0 &&
      rect.height > 0 &&
      rect.bottom > 0 &&
      rect.right > 0 &&
      rect.top < window.innerHeight &&
      rect.left < window.innerWidth;
    if (!onScreen) return true;
    const shadow = (icon as HTMLElement).shadowRoot;
    return shadow !== null && shadow !== undefined && shadow.querySelector('svg') !== null;
  });
}

/**
 * Has the shell chrome decided which door into the menu is on screen?
 *
 * `ion-menu` lives inside `<AuthenticatedChrome>` and registers with Ionic ASYNCHRONOUSLY, and
 * until it does, Ionic keeps `ion-menu-button` at `display: none`. So on a phone the hamburger is
 * NOT there when the page looks finished: measured on 2026-09-11 over 8 fresh loads of /settings
 * at 390px, it was hidden at the settle point and at +200 ms in 8 of 8, and `block` by +1.5 s.
 * The capture landed on either side of that flip depending on the machine — 69 px of difference,
 * which the old ratio budget swallowed and the 20 px budget of hub#1823 reports, correctly, as a
 * screen that is not the one in the baseline.
 *
 * The invariant is EXACTLY ONE door, which is what makes one predicate work at all three widths:
 * at 1440 the split pane shows the drawer inline (`when="lg"` in `App.vue`) and the button stays
 * hidden for good; below that the pane is closed and the hamburger has to be there. Waiting for
 * "the hamburger" instead would hang every desktop capture, and waiting for a fixed delay would
 * be a flake with a timer on it.
 *
 * A screen with neither piece — the login, which renders no `<AuthenticatedChrome>` — has nothing
 * to resolve and settles immediately. One of the two alone means the chrome is mid-render.
 */
export function shellChromeHasSettled(): boolean {
  const menu = document.querySelector('ion-menu');
  const button = document.querySelector('ion-menu-button');
  if (menu === null && button === null) return true;
  if (menu === null || button === null) return false;

  const splitPane = document.querySelector('ion-split-pane');
  const splitPaneShowsTheMenu = splitPane !== null && splitPane.classList.contains('split-pane-visible');
  const buttonIsOnScreen = window.getComputedStyle(button).display !== 'none';
  return splitPaneShowsTheMenu !== buttonIsOnScreen;
}

/**
 * Has every scrollable box on screen STOPPED moving?
 *
 * `ion-segment[scrollable]` — the tabbar of /settings, /system, /employees and every module
 * screen — nudges its own scroll position shortly after it mounts, to hint that there are more
 * tabs off-screen. Measured on 2026-09-11 against the real bench, /settings at 390px, polling
 * every ~50 ms: still at 0 from 469 ms, `shellChromeHasSettled` and `everyOnScreenIconIsPainted`
 * both say YES at 772 ms, and only THEN does the hint run — 14 px at 889 ms, 28 px from 947 to
 * 1251 ms, 13 px at 1309 ms, back to 0 at 1368 ms and still there at 3.8 s.
 *
 * So the two predicates above hand the capture over 117 ms before the screen starts moving. The
 * Linux runner, being slower, photographed the tabbar at 28 px while this Mac photographs it at 0:
 * 5.239 px of difference on one screen, invisible under the old ratio budget and red under the
 * 20 px one. That is the same defect as the other two settle points, one layer further in.
 *
 * WHY A QUIET WINDOW AND NOT "the scroll is not moving". At 772 ms the position had been perfectly
 * still for 300 ms and was about to move: one sample, or two identical samples, prove nothing. The
 * invariant that does hold is the position holding for LONGER than the hint takes to get going
 * (420 ms between the tabbar coming to rest and the hint starting), so the window is 600 ms.
 * Landing before the hint or after it gives the SAME pixels — both are the resting position — so
 * the window does not have to predict which side it is on, only to refuse the middle.
 *
 * The key covers WHICH boxes scroll as well as where they are: the tabbar of a module screen is
 * not in the first paint (at 277 ms there was no `ion-segment` at all), so a predicate comparing
 * positions alone would have called the empty page quiet and captured before the tabbar existed.
 *
 * WHAT COUNTS AS A SCROLLER is `overflow: auto|scroll`, not "its content does not fit". Measured
 * on /dashboard: the `buffer-circles-container` of the setup card's `ion-progress-bar` animates
 * forever and its `scrollWidth` breathes around its `clientWidth` (321 px → 330, 327, 323...), so
 * with the looser test it kept joining and leaving the set, the key never repeated twice, and the
 * three dashboard captures died on the timeout instead of settling. That box is `overflow: hidden`
 * — the browser cannot scroll it, so it is not part of this invariant.
 *
 * `performance.now()` and NOT `Date.now()`: every visual spec freezes the clock with
 * `page.clock.setFixedTime` (`freezeVisualClock`), so in the page `Date.now()` answers the same
 * millisecond forever and a quiet window measured with it would either never close or close at
 * once. `setFixedTime` does not touch `performance.now()`.
 */
export function everyScrollerHasStoppedMoving(): boolean {
  const QUIET_MS = 600;

  const boxes: Element[] = [];
  const walk = (root: Document | ShadowRoot): void => {
    for (const element of Array.from(root.querySelectorAll('*'))) {
      boxes.push(element);
      const shadow = (element as HTMLElement).shadowRoot;
      if (shadow !== null && shadow !== undefined) walk(shadow);
    }
  };
  walk(document);

  const key = boxes
    .filter((box) => {
      const style = window.getComputedStyle(box);
      const scrolls = (overflow: string): boolean => overflow === 'auto' || overflow === 'scroll';
      return (
        (scrolls(style.overflowX) && box.scrollWidth > box.clientWidth) ||
        (scrolls(style.overflowY) && box.scrollHeight > box.clientHeight)
      );
    })
    .map((box) => `${box.tagName}:${box.scrollLeft},${box.scrollTop}`)
    .join('|');

  const stash = window as unknown as { __erploraVisualScrollQuiet?: { key: string; since: number } };
  const seen = stash.__erploraVisualScrollQuiet;
  const now = performance.now();
  if (seen === undefined || seen.key !== key) {
    stash.__erploraVisualScrollQuiet = { key, since: now };
    return false;
  }
  return now - seen.since >= QUIET_MS;
}
