// Regression test for ERPlora/hub#2314 — a sheet's title keeps Ionic's own side padding in md.
//
// Tailwind's preflight (`@import "tailwindcss"` in `theme/global.css`) resets `padding: 0` on `*`.
// A document rule always beats a shadow `:host` rule, so it wiped the 20px side padding Ionic gives
// `ion-title` in `md` on EVERY title of the app (the shell's topbar, its sheets and the sheets of
// every module): the title sat flush against the sheet's edge while the body kept its 16px
// (services#122). `ios` deliberately keeps padding 0: Ionic's 90px there would cut ordinary titles
// on a 360px phone, which the second test pins.
//
// NOT a check on the CSS text: the sheet is presented inside the REAL shell, with the shell's real
// stylesheets, and the browser is asked where the title's text ends up. The markup is the one the
// modules use (`ion-modal > ion-header.ion-no-border > ion-toolbar > ion-title`, plus an end button).
import { test, expect } from '../bench-boot';
import type { Page } from '@playwright/test';
import { loggedInSession } from './shell-visual-helpers';

interface SheetGeometry {
  /** Where the title's text box starts, measured from the sheet's left edge. */
  titleStart: number;
  /** Where the body's first line starts, measured from the sheet's left edge. */
  bodyStart: number;
  /** Whether the title's text is cut (ellipsis): its text is wider than the box it is given. */
  titleTruncated: boolean;
}

async function presentSheet(page: Page, mode: 'ios' | 'md', title: string): Promise<SheetGeometry> {
  return page.evaluate(
    async ({ mode, title }) => {
      const modal = document.createElement('ion-modal') as HTMLElement & {
        present(): Promise<void>;
        dismiss(): Promise<boolean>;
      };
      modal.setAttribute('mode', mode);
      modal.innerHTML = `
        <ion-header class="ion-no-border">
          <ion-toolbar>
            <ion-title></ion-title>
            <ion-buttons slot="end"><ion-button>Close</ion-button></ion-buttons>
          </ion-toolbar>
        </ion-header>
        <ion-content class="ion-padding"><p>Body text</p></ion-content>`;
      modal.querySelector('ion-title')!.textContent = title;
      document.querySelector('ion-app')!.append(modal);
      await modal.present();

      const sheet = modal.shadowRoot!.querySelector('.modal-wrapper')!.getBoundingClientRect();
      const titleEl = modal.querySelector('ion-title')!;
      const textEl = titleEl.shadowRoot!.querySelector('.toolbar-title')!;
      const text = textEl.getBoundingClientRect();
      const range = document.createRange();
      range.selectNodeContents(modal.querySelector('ion-content p')!);
      const body = range.getClientRects()[0];
      const geometry = {
        titleStart: text.left - sheet.left,
        bodyStart: body.left - sheet.left,
        titleTruncated: textEl.scrollWidth > textEl.clientWidth,
      };
      await modal.dismiss();
      modal.remove();
      return geometry;
    },
    { mode, title },
  );
}

test.describe('a sheet title keeps its side padding (hub#2314)', () => {
  test('in md the title is inset at least as much as the body, not flush with the edge', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await loggedInSession(page);
    await page.goto('/settings');
    await expect(page.locator('ion-app.hydrated')).toBeAttached();

    const sheet = await presentSheet(page, 'md', 'Voucher movements');
    expect(sheet.bodyStart, 'the body keeps its own padding').toBeGreaterThan(0);
    expect(sheet.titleStart, 'the title starts flush against the sheet edge').toBeGreaterThanOrEqual(
      sheet.bodyStart,
    );
    expect(sheet.titleTruncated, 'a short title is cut by its own padding').toBe(false);
  });

  // ios keeps the padding it has on develop (0): Ionic's own 90px leaves an ordinary title only
  // 164px on a 360px Android phone (the app runs in ios mode there too, ADR-0143), and
  // «Movimientos del bono» needs 166px in Roboto, so restoring it would cut everyday titles to
  // cure a rare long one. The title's BOX is not checked against the buttons here: with padding 0
  // the centred ios box spans the whole toolbar by design; long ios titles are a separate issue.
  test('in ios a short title on a 360px phone is shown whole, not cut by its padding', async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 780 });
    await loggedInSession(page);
    await page.goto('/settings');
    await expect(page.locator('ion-app.hydrated')).toBeAttached();

    const sheet = await presentSheet(page, 'ios', 'Movimientos del bono');
    expect(sheet.titleTruncated, 'a short title is cut by its own padding').toBe(false);
  });
});
