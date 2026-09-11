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
