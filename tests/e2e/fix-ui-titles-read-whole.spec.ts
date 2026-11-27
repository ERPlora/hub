// Three titles of the shared library that were cut while there was room to read them, as the owner of hub `a` sees
// them in Spanish:
//   - the bar of VeriFactu → Configuración at 820 and 1280 px read «Configuración de VeriFactu · Configura…» with
//     empty room beside the buttons: the title's box takes what its text needs, centred on the bar;
//   - «Marcar pagada» of an issued invoice asked «¿Marcar FACT-… como paga…»: the question takes a second line, clear
//     of the close button;
//   - at 375 px the play button of the video of «Declarar una operación exenta, no sujeta o con inversión del sujeto
//     pasivo», in the help of Impuestos → Reglas, covered the end of its title on the poster: it stays below it.
// Each case leaves its capture. The invoice the run issues is deleted, and the numbering and issuer are given back.
// flow: ui:AppTopbar ui:ConfirmDialog ui:YouTubeEmbed INVOICE-F19 BASE-F115
import { expect, type Locator, test } from '@playwright/test';

import { A, capture, horizontalOverflow, shown, signedInSpanish, untilStill } from './helpers';
import { openTask } from './help-video-helpers';
import { cleanInvoices, issueManualInvoice, readyToInvoice } from './invoice-helpers';

const KEY = 'FIX-UI-TITLES-READ-WHOLE';
let invoice = { id: '', number: '' };

test.describe.configure({ mode: 'serial' });

test.beforeAll(async ({ browser }) => {
  const context = await readyToInvoice(browser);
  invoice = await issueManualInvoice(context);
  await context.close();
});

test.afterAll(cleanInvoices);

/** Whether Ionic's own box of the title (`.toolbar-title`, in its shadow) cuts its text, either way. */
function titleCut(title: Locator): Promise<boolean> {
  return title.evaluate((element) => {
    const box = (element.shadowRoot?.querySelector('.toolbar-title') ?? element) as HTMLElement;
    return box.scrollWidth > box.clientWidth || box.scrollHeight > box.clientHeight + 1;
  });
}

for (const size of [
  { width: 1280, height: 720 },
  { width: 820, height: 1180 },
]) {
  test(`at ${size.width} px the bar of VeriFactu → Configuración reads its whole title, centred`, async ({ browser }) => {
    const { context, page } = await signedInSpanish(browser, size, '/verifactu/config');
    try {
      await expect(shown(page).locator('[data-testid=verifactu-config-tab-own]')).toBeVisible();
      const title = shown(page).locator('.app-topbar ion-title');
      await expect(title).toHaveText(/^\s*Configuración de VeriFactu\s*Configuración\s*$/);
      await untilStill(page);
      expect(await titleCut(title), 'the title is cut').toBe(false);
      const offCentre = await title.evaluate((element) => {
        const range = document.createRange();
        range.selectNodeContents(element);
        const text = range.getBoundingClientRect();
        const bar = element.closest('ion-toolbar')!.getBoundingClientRect();
        return Math.abs(text.left + text.width / 2 - (bar.left + bar.width / 2));
      });
      expect(offCentre, 'px from the centre of the bar').toBeLessThanOrEqual(2);
      expect(await horizontalOverflow(page)).toBeLessThanOrEqual(0);
      await capture(page, `${KEY}-topbar-${size.width}`);
    } finally {
      await context.close();
    }
  });
}

for (const size of [
  { width: 1280, height: 720 },
  { width: 375, height: 667 },
]) {
  test(`at ${size.width} px «Marcar pagada» asks its whole question, clear of the close button`, async ({ browser }) => {
    const { context, page } = await signedInSpanish(browser, size, `/invoice/invoices/${invoice.id}`);
    try {
      await expect(shown(page).locator('[data-testid=invoice-detail-title]')).toContainText(invoice.number);
      await shown(page).locator('[data-testid=invoice-detail-mark-paid]').click();
      const dialog = page.locator('ion-modal.ep-form-modal:not(.overlay-hidden)').last();
      const question = `¿Marcar ${invoice.number} como pagada?`;
      await expect(dialog.locator('.ep-form-modal__title')).toHaveText(question);
      await untilStill(page);
      expect(await titleCut(dialog.locator('.ep-form-modal__title')), 'the question is cut').toBe(false);
      const clear = await dialog.evaluate((element) => {
        const text = element.querySelector('.ep-form-modal__title-text')!.getBoundingClientRect();
        const close = element.querySelector('.ep-form-modal__close')!.getBoundingClientRect();
        return text.right <= close.left + 0.5 || text.bottom <= close.top || text.top >= close.bottom;
      });
      expect(clear, 'the question stays clear of the close button').toBe(true);
      await capture(page, `${KEY}-mark-paid-${size.width}`);
      await dialog.locator('.ep-form-modal__cancel').click();
      await expect(dialog).toBeHidden();
    } finally {
      await context.close();
    }
  });
}

test('at 375 px the play button of a help video stays below its title of three lines', async ({ browser }) => {
  const { context, page } = await signedInSpanish(browser, { width: 375, height: 667 }, '/tax/rules');
  try {
    const task = await openTask(page, `${A}/tax/rules`, 'help-flow-rules-TAX-F05', []);
    const poster = task.locator('.youtube-embed__poster');
    await expect(poster).toContainText('Declarar una operación exenta, no sujeta o con inversión del sujeto pasivo');
    await poster.scrollIntoViewIfNeeded();
    await untilStill(page);
    const boxes = await poster.evaluate((element) => {
      const frame = element.getBoundingClientRect();
      const title = element.querySelector('.youtube-embed__title')!.getBoundingClientRect();
      const play = element.querySelector('.youtube-embed__play')!.getBoundingClientRect();
      return { frameBottom: frame.bottom, titleBottom: title.bottom, playTop: play.top, playBottom: play.bottom };
    });
    expect(boxes.playTop, 'the play button starts below the title').toBeGreaterThanOrEqual(boxes.titleBottom);
    expect(boxes.playBottom, 'the play button is inside the poster').toBeLessThanOrEqual(boxes.frameBottom);
    expect(await horizontalOverflow(page)).toBeLessThanOrEqual(0);
    await capture(page, `${KEY}-help-video-375`);
  } finally {
    await context.close();
  }
});
