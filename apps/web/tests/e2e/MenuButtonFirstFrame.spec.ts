// Regression test for ERPlora/hub#1831 — on a phone the menu button is there from the first frame.
//
// `ion-menu-button` hides itself (`autoHide`, class `menu-button-hidden`) until its `ion-menu`
// registers, and the menu registers ASYNCHRONOUSLY inside `<AuthenticatedChrome>`. Measured on this
// bench, `/settings` at 390 px, sampling every 100 ms: the footer tab bar already painted and the
// button still `display: none` for one sample in 2 loads of 4 on a Mac — up to a second on the Linux
// runner (hub#1823). Nothing on screen let you leave the page you landed on.
//
// NOT a timing check: an observer installed before the page loads records whether the button was
// EVER hidden while the screen was painted. A window of 100 ms or of 1 s is caught the same way, and
// a runner that happens to sample after the window closes cannot turn it green.
import { test, expect } from '../bench-boot';
import { loggedInSession } from './shell-visual-helpers';

declare global {
  interface Window {
    __menuButtonHiddenWhilePainted?: boolean;
  }
}

test.describe('el botón de menú está desde el primer fotograma (hub#1831)', () => {
  test('a 390 px el botón de menú no se oculta nunca con la pantalla ya pintada', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await loggedInSession(page);
    await page.addInitScript(() => {
      window.__menuButtonHiddenWhilePainted = false;
      const check = (): void => {
        const tabbar = document.querySelector<HTMLElement>('.ok-tabbar');
        const painted = tabbar !== null && tabbar.offsetParent !== null;
        if (!painted) return;
        for (const button of Array.from(document.querySelectorAll('ion-menu-button'))) {
          if (button.classList.contains('menu-button-hidden') || getComputedStyle(button).display === 'none') {
            window.__menuButtonHiddenWhilePainted = true;
          }
        }
      };
      new MutationObserver(check).observe(document, {
        subtree: true,
        childList: true,
        attributes: true,
        attributeFilter: ['class', 'style'],
      });
    });

    for (let load = 1; load <= 4; load++) {
      await page.goto('/settings');
      await expect(page.locator('.ok-tabbar').filter({ visible: true }).first()).toBeVisible();
      // Long enough for the menu to have registered on any runner: the question is what happened
      // BEFORE, and the observer already has the answer.
      await page.waitForTimeout(1500);
      expect(
        await page.evaluate(() => window.__menuButtonHiddenWhilePainted),
        `load ${load}: the screen was painted while the menu button was hidden`,
      ).toBe(false);
    }
  });

  test('a 1440 px el menú está fijo a la izquierda y el botón no se pinta', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await loggedInSession(page);
    await page.goto('/settings');
    await expect(page.locator('ion-split-pane.split-pane-visible')).toBeAttached();
    await expect
      .poll(() =>
        page.evaluate(() =>
          Array.from(document.querySelectorAll('ion-menu-button')).every(
            (button) => getComputedStyle(button).display === 'none',
          ),
        ),
      )
      .toBe(true);
  });
});
