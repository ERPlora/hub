// Regression test for ERPlora/hub#2314 — a sheet's title keeps Ionic's own side padding.
//
// Tailwind's preflight (`@import "tailwindcss"` in `theme/global.css`) resets `padding: 0` on `*`.
// A document rule always beats a shadow `:host` rule, so it wiped the side padding Ionic gives
// `ion-title` from inside its shadow root (20px in `md`, 90px in `ios`) on EVERY title of the app:
// the shell's topbar, the shell's sheets and the sheets of every module. In `md` the title sat
// flush against the sheet's edge while the body kept its 16px (services#122); in `ios` the centred
// title had nothing keeping it off the toolbar's buttons, so a long one ran under them.
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
  /** Where the title's text box ends, measured from the sheet's left edge. */
  titleEnd: number;
  /** Where the end buttons start, measured from the sheet's left edge. */
  buttonsStart: number;
  /** Where the body's first line starts, measured from the sheet's left edge. */
  bodyStart: number;
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
      const text = titleEl.shadowRoot!.querySelector('.toolbar-title')!.getBoundingClientRect();
      const buttons = modal.querySelector('ion-buttons')!.getBoundingClientRect();
      const range = document.createRange();
      range.selectNodeContents(modal.querySelector('ion-content p')!);
      const body = range.getClientRects()[0];
      const geometry = {
        titleStart: text.left - sheet.left,
        titleEnd: text.right - sheet.left,
        buttonsStart: buttons.left - sheet.left,
        bodyStart: body.left - sheet.left,
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
  });

  test('in ios a long centred title stops before the end buttons instead of running under them', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await loggedInSession(page);
    await page.goto('/settings');
    await expect(page.locator('ion-app.hydrated')).toBeAttached();

    const sheet = await presentSheet(
      page,
      'ios',
      'Every session of this voucher: booked, delivered, released, expired and refunded',
    );
    expect(sheet.titleEnd, 'the title text runs under the end buttons').toBeLessThanOrEqual(sheet.buttonsStart);
  });
});
