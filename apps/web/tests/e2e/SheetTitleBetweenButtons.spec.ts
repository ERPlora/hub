// Regression test for ERPlora/hub#2344 — in ios a sheet's title sits BETWEEN the toolbar buttons.
//
// In `ios` Ionic lays `ion-title` out `position: absolute` across the WHOLE toolbar and keeps it off
// the buttons with a fixed `padding: 0 90px`. Tailwind's preflight (`padding: 0` on `*`, a document
// rule, which always beats a shadow `:host` rule) wipes that padding, so a long title ran under the
// «Cancel»/«Close» button and both were painted on top of each other (combos#29: «Añadir artículos a
// este plato» over «Cancelar» at 360 and 390 px). Ionic's own 90px is no cure either: on a 360px
// phone it leaves an ordinary title 164px and cuts «Movimientos del bono» (hub#2314).
//
// The contract pinned here is the one of native iOS sheets, Square and Shopify POS: the title only
// takes the room the buttons leave, is centred in it, and ends in «…» when it does not fit.
//
// NOT a check on the CSS text: the sheet is presented inside the REAL shell, with its real
// stylesheets, and the browser is asked where the title's VISIBLE text ends up — the part of the
// text run that its clipping box lets through, not the box (with padding 0 the box spans the whole
// toolbar by design). The markup is the one the modules use: an inline `ion-modal` is moved by Ionic
// to `ion-app`, out of the module's shadow root, so it is styled by the shell's document CSS.
import { test, expect } from '../bench-boot';
import type { Page } from '@playwright/test';
import { loggedInSession } from './shell-visual-helpers';

const LONG_TITLE = 'Every session of this voucher: booked, delivered, released, expired and refunded';
const SHORT_TITLE = 'Movimientos del bono';

interface TitleGeometry {
  /** Left edge of the title's visible text (text run clipped by its box), in viewport px. */
  visibleLeft: number;
  /** Right edge of the title's visible text, in viewport px. */
  visibleRight: number;
  /** Centre of the visible text minus centre of the title's own box (0 = centred in its room). */
  offCentre: number;
  /** Right edge of the start button, or the sheet's left edge when there is none. */
  startLimit: number;
  /** Left edge of the end button. */
  endLimit: number;
  /** Where the body's first line starts. */
  bodyStart: number;
  /** Whether the title's text is cut (ellipsis). */
  truncated: boolean;
}

async function presentSheet(
  page: Page,
  opts: { mode: 'ios' | 'md'; title: string; startButton?: string; endButton: string },
): Promise<TitleGeometry> {
  return page.evaluate(async ({ mode, title, startButton, endButton }) => {
    const modal = document.createElement('ion-modal') as HTMLElement & { present(): Promise<void> };
    modal.setAttribute('mode', mode);
    modal.dataset.testid = 'sheet-under-test';
    modal.innerHTML = `
      <ion-header class="ion-no-border">
        <ion-toolbar>
          ${startButton === undefined ? '' : '<ion-buttons slot="start"><ion-button class="start-btn"></ion-button></ion-buttons>'}
          <ion-title></ion-title>
          <ion-buttons slot="end"><ion-button class="end-btn"></ion-button></ion-buttons>
        </ion-toolbar>
      </ion-header>
      <ion-content class="ion-padding"><p>Body text</p></ion-content>`;
    modal.querySelector('ion-title')!.textContent = title;
    modal.querySelector('.end-btn')!.textContent = endButton;
    if (startButton !== undefined) modal.querySelector('.start-btn')!.textContent = startButton;
    document.querySelector('ion-app')!.append(modal);
    await modal.present();

    const sheet = modal.shadowRoot!.querySelector('.modal-wrapper')!.getBoundingClientRect();
    const titleEl = modal.querySelector('ion-title')!;
    const box = titleEl.shadowRoot!.querySelector('.toolbar-title')!;
    const boxRect = box.getBoundingClientRect();
    const textRange = document.createRange();
    textRange.selectNodeContents(titleEl);
    const run = textRange.getBoundingClientRect();
    const visibleLeft = Math.max(run.left, boxRect.left);
    const visibleRight = Math.min(run.right, boxRect.right);
    const bodyRange = document.createRange();
    bodyRange.selectNodeContents(modal.querySelector('ion-content p')!);
    const startBtn = modal.querySelector('.start-btn');
    return {
      visibleLeft,
      visibleRight,
      offCentre: (visibleLeft + visibleRight) / 2 - (boxRect.left + boxRect.right) / 2,
      startLimit: startBtn ? startBtn.getBoundingClientRect().right : sheet.left,
      endLimit: modal.querySelector('.end-btn')!.getBoundingClientRect().left,
      bodyStart: bodyRange.getClientRects()[0]!.left,
      truncated: box.scrollWidth > box.clientWidth,
    };
  }, opts);
}

async function openShell(page: Page, width: number, height: number): Promise<void> {
  await page.setViewportSize({ width, height });
  await loggedInSession(page);
  await page.goto('/settings');
  await expect(page.locator('ion-app.hydrated')).toBeAttached();
}

test.describe('in ios a sheet title sits between the toolbar buttons (hub#2344)', () => {
  for (const { width, height } of [
    { width: 360, height: 780 },
    { width: 390, height: 844 },
    { width: 820, height: 1180 },
    { width: 1440, height: 900 },
  ]) {
    test(`at ${width}px a long title ends in «…» before the end button`, async ({ page }, testInfo) => {
      await openShell(page, width, height);
      const title = await presentSheet(page, { mode: 'ios', title: LONG_TITLE, endButton: 'Cancelar' });
      await testInfo.attach(`sheet-long-title-${width}`, { body: await page.screenshot(), contentType: 'image/png' });

      expect(title.truncated, 'a title that does not fit is cut with «…»').toBe(true);
      expect(title.visibleRight, 'the title runs under the end button').toBeLessThanOrEqual(title.endLimit);
      expect(
        Math.abs(title.visibleLeft - title.bodyStart),
        'a long title does not start where the body text starts',
      ).toBeLessThanOrEqual(1);
    });
  }

  test('at 360px a long title stays clear of BOTH buttons', async ({ page }, testInfo) => {
    await openShell(page, 360, 780);
    const title = await presentSheet(page, {
      mode: 'ios',
      title: LONG_TITLE,
      startButton: 'Atrás',
      endButton: 'Guardar',
    });
    await testInfo.attach('sheet-long-title-two-buttons-360', {
      body: await page.screenshot(),
      contentType: 'image/png',
    });

    expect(title.truncated).toBe(true);
    expect(title.visibleLeft, 'the title runs under the start button').toBeGreaterThanOrEqual(title.startLimit);
    expect(title.visibleRight, 'the title runs under the end button').toBeLessThanOrEqual(title.endLimit);
  });

  test('at 360px an ordinary title is whole and centred in the room the buttons leave', async ({ page }, testInfo) => {
    await openShell(page, 360, 780);
    const title = await presentSheet(page, { mode: 'ios', title: SHORT_TITLE, endButton: 'Cancelar' });
    await testInfo.attach('sheet-short-title-360', { body: await page.screenshot(), contentType: 'image/png' });

    expect(title.truncated, 'an ordinary title is cut on a 360px phone').toBe(false);
    expect(title.visibleRight, 'the title runs under the end button').toBeLessThanOrEqual(title.endLimit);
    expect(Math.abs(title.offCentre), 'the title is not centred in its room').toBeLessThanOrEqual(1);
  });

  // The rule is for ios only: an md sheet's title is laid out like any other md title (md's side
  // padding is hub#2314's business, so it is compared with a title outside a sheet, not pinned).
  test('in md a sheet title is laid out like any md title', async ({ page }) => {
    await openShell(page, 390, 844);
    const styles = await page.evaluate(async () => {
      const read = (el: Element) => {
        const s = getComputedStyle(el);
        return { position: s.position, paddingLeft: s.paddingLeft, paddingRight: s.paddingRight };
      };
      const loose = document.createElement('ion-toolbar');
      loose.setAttribute('mode', 'md');
      loose.innerHTML = '<ion-title mode="md">Voucher movements</ion-title>';
      document.querySelector('ion-app')!.append(loose);
      const modal = document.createElement('ion-modal') as HTMLElement & { present(): Promise<void> };
      modal.setAttribute('mode', 'md');
      modal.innerHTML = `
        <ion-header><ion-toolbar><ion-title>Voucher movements</ion-title>
          <ion-buttons slot="end"><ion-button>Close</ion-button></ion-buttons></ion-toolbar></ion-header>
        <ion-content class="ion-padding"><p>Body text</p></ion-content>`;
      document.querySelector('ion-app')!.append(modal);
      await modal.present();
      await customElements.whenDefined('ion-title');
      return { sheet: read(modal.querySelector('ion-title')!), loose: read(loose.querySelector('ion-title')!) };
    });
    expect(styles.sheet, 'the ios sheet rule leaks into md').toEqual(styles.loose);
  });

  // The rule is for sheets only: the shell's topbar keeps Ionic's ios layout, its title centred on
  // the WHOLE bar even though its start and end buttons are of very different widths.
  test('the shell topbar title stays centred on the whole bar', async ({ page }) => {
    await openShell(page, 1440, 900);
    const title = page.locator('ion-header.app-topbar ion-title');
    await expect(title).toHaveText(/\S/);
    const offCentre = await title.evaluate((el) => {
      const range = document.createRange();
      range.selectNodeContents(el);
      const text = range.getBoundingClientRect();
      const bar = el.closest('ion-toolbar')!.getBoundingClientRect();
      return (text.left + text.right) / 2 - (bar.left + bar.right) / 2;
    });
    expect(Math.abs(offCentre), 'the topbar title left the centre of the bar').toBeLessThanOrEqual(1);
  });
});
