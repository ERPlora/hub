// hub#760, hub#784 — a form's window fits the screen whatever its select has chosen, in Chrome, against hub `a`. A
// select used to keep the chosen text on one line, and the one-column grid of a form (`auto`, so as wide as its widest
// child's minimum) grew to it, and every field with it, whichever the form:
//   - «New menu» (COMBO-F02) in Spanish: «Se consume en el local (servicio de restauración)», 387 px at 375 and 390;
//   - «Rectify» (INVOICE-F08) on the R1 it opens with: 534 px in Spanish and 463 in English, past a tablet's window too,
//     its «This cannot be undone» cut in half;
//   - «New table» (TABLE-F02) with a zone of a long name, the business's own words: 569 px at 375.
// The rule lives in FormModal (@erplora/ui). Each size is a new browser context, the form opened there, never a window
// resized with the form open. It measures each field and each line against the dialog, not the page's overflow, which
// clipped fields never raised, and that the select's chosen text can be read whole. Saves nothing but what it needs to
// open them (an invoice and a zone, removed after).
// flow: COMBO-F02, INVOICE-F08, TABLE-F02
import { type Browser, type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, api, capture, login, painted, psql, shown } from './helpers';
import { cleanInvoices, ensureIssuer, issuedIds, openDialog, snapshotSeries } from './invoice-helpers';

const RUN = Date.now().toString(36);
const LANGUAGES = ['es', 'en'] as const;
const PHONE = { label: '375x667', width: 375, height: 667 };
const VIEWPORTS = [PHONE, { label: '390x844', width: 390, height: 844 }, { label: '820x1180', width: 820, height: 1180 }];
const WITH_DESKTOP = [...VIEWPORTS, { label: '1440x900', width: 1440, height: 900 }];

type Viewport = (typeof WITH_DESKTOP)[number];

/** A new browser at `viewport`, the owner on `path` with the interface in `language`. */
async function ownerAt(browser: Browser, viewport: Viewport, language: string, path: string): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ baseURL: A, viewport: { width: viewport.width, height: viewport.height }, locale: 'en-US' });
  const page = await context.newPage();
  await login(page, A, path);
  await context.addCookies([{ name: 'django_language', value: language, domain: new URL(A).hostname, path: '/' }]);
  await page.goto(`${A}${path}`);
  await expect(page.locator('html')).toHaveAttribute('lang', new RegExp(`^${language}`));
  return { context, page };
}

/** What the person cannot reach or read in the open form `form`: the dialog past the screen, its body scrolling
 *  sideways, a field or a line past the dialog (its hook and by how many px), the text `select` has chosen cut short
 *  or missing. Empty when all of it fits. */
function cutOff(page: Page, form: string, select: string): Promise<string[]> {
  return page.evaluate(
    ({ form, select }) => {
      const cut: string[] = [];
      const modal = document.querySelector(`ion-modal[data-testid=${form}]:not(.overlay-hidden)`);
      const dialog = modal?.shadowRoot?.querySelector('.modal-wrapper')?.getBoundingClientRect();
      const body = modal?.querySelector('.ep-form-modal__body');
      if (!modal || !dialog || !body) return [`${form} is not open`];
      if (dialog.left < 0 || dialog.right > window.innerWidth) cut.push(`dialog ${dialog.left}..${dialog.right}`);
      if (body.scrollWidth > body.clientWidth) cut.push(`body scrolls ${body.scrollWidth - body.clientWidth}px sideways`);
      for (const field of body.querySelectorAll('[data-testid]')) {
        const box = field.getBoundingClientRect();
        if (box.width === 0) continue;
        const hook = field.getAttribute('data-testid');
        if (dialog.left - box.left > 1) cut.push(`${hook} -${Math.round(dialog.left - box.left)}px`);
        if (box.right - dialog.right > 1) cut.push(`${hook} +${Math.round(box.right - dialog.right)}px`);
      }
      const chosen = modal.querySelector(`[data-testid=${select}]`)?.shadowRoot?.querySelector('[part~="text"]');
      if (!chosen?.textContent?.trim()) cut.push(`${select} shows nothing chosen`);
      else if (chosen.scrollWidth > chosen.clientWidth) cut.push(`«${chosen.textContent}» cut short`);
      return cut;
    },
    { form, select },
  );
}

test.describe('«New menu»', () => {
  const FORM = 'combo-menu-form';
  const SUPPLY = 'combo-menu-form-supply_kind';

  for (const language of LANGUAGES) {
    for (const viewport of WITH_DESKTOP) {
      test(`COMBO-F02: it fits the window at ${viewport.label} in ${language}, either way of selling`, async ({ browser }) => {
        const { context, page } = await ownerAt(browser, viewport, language, '/combo/menus');
        await shown(page).locator('[data-testid=combo-menus-add]').click();
        await expect(openDialog(page, FORM)).toBeVisible();
        await expect(page.locator(`[data-testid=${SUPPLY}]`)).toBeVisible();
        await expect.poll(() => cutOff(page, FORM, SUPPLY), { message: 'eaten in, as the form opens' }).toEqual([]);
        await capture(page, `FIX-UI-FORM-MODAL-FITS-menu-${language}-${viewport.label}`);

        await page.locator(`[data-testid=${SUPPLY}]`).click();
        await page.locator('ion-select-popover ion-radio').nth(1).click();
        await expect(page.locator('[data-testid=combo-menu-form-help-goods]')).toHaveAttribute('data-active', 'true');
        await expect(page.locator('ion-select-popover')).toHaveCount(0);
        await painted(page);
        await expect.poll(() => cutOff(page, FORM, SUPPLY), { message: 'to take away, once chosen' }).toEqual([]);
        await context.close();
      });
    }
  }
});

test.describe('«Rectify»', () => {
  const FORM = 'invoice-rectify';
  let invoiceId = '';

  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ baseURL: A });
    await login(await context.newPage(), A, '/invoice/invoices');
    snapshotSeries();
    await ensureIssuer(context);
    const issued = await api<{ id: string }>(context, A, 'POST', '/invoice/invoices', {
      customer_name: `e2e Fits ${RUN}`,
      customer_tax_id: '12345678Z',
      customer_address: 'Calle Sol 5, Madrid',
      lines: [{ description: `e2e Fits ${RUN}`, quantity: '1', unit_price: 1000, tax_rate: '21' }],
    });
    expect(issued.status).toBe(201);
    issuedIds.add(issued.data.id);
    invoiceId = issued.data.id;
    await context.close();
  });
  test.afterAll(cleanInvoices);

  for (const language of LANGUAGES) {
    for (const viewport of VIEWPORTS) {
      test(`INVOICE-F08: it fits the window at ${viewport.label} in ${language}, as it opens`, async ({ browser }) => {
        const { context, page } = await ownerAt(browser, viewport, language, `/invoice/invoices/${invoiceId}`);
        await shown(page).locator('[data-testid=invoice-detail-rectify]').click();
        await expect(openDialog(page, FORM)).toBeVisible();
        await expect(page.locator('[data-testid=invoice-rectify-note]')).toBeVisible();
        await expect.poll(() => cutOff(page, FORM, 'invoice-rectify-type')).toEqual([]);
        await capture(page, `FIX-UI-FORM-MODAL-FITS-rectify-${language}-${viewport.label}`);
        await context.close();
      });
    }
  }
});

test.describe('«New table»', () => {
  const FORM = 'table-form';
  const SELECT = 'table-form-zone';
  const TAG = 'E2E Fits';
  /** 75 characters, as long as a business may well name a zone. */
  const ZONE = `${TAG} ${RUN} Terraza de verano junto a la fuente del patio interior del local`.slice(0, 75);

  function cleanZones(): void {
    psql(`delete from table_zone where name like '${TAG} %'`);
  }

  test.beforeAll(async ({ browser }) => {
    cleanZones();
    const context = await browser.newContext({ baseURL: A });
    await login(await context.newPage(), A, '/table/zones');
    const zone = await api<{ id: string }>(context, A, 'POST', '/table/zones', { name: ZONE });
    expect(zone.status).toBe(201);
    await context.close();
  });
  test.afterAll(cleanZones);

  test('TABLE-F02: it fits the window at 375x667 in es with a zone of a long name chosen', async ({ browser }) => {
    const { context, page } = await ownerAt(browser, PHONE, 'es', '/table/tables');
    await shown(page).locator('[data-testid=table-tables-add]').click();
    await expect(openDialog(page, FORM)).toBeVisible();
    await page.locator(`[data-testid=${SELECT}]`).click();
    await page.locator('ion-popover').getByText(ZONE, { exact: true }).click();
    await expect(page.locator('ion-select-popover')).toHaveCount(0);
    await painted(page);
    await expect
      .poll(() => page.locator(`[data-testid=${SELECT}]`).evaluate((select) => select.shadowRoot?.querySelector('[part~="text"]')?.textContent))
      .toBe(ZONE);
    await expect.poll(() => cutOff(page, FORM, SELECT)).toEqual([]);
    await capture(page, 'FIX-UI-FORM-MODAL-FITS-table-es-375x667');
    await context.close();
  });
});
