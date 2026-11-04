// hub#775 — a long option of a dropdown reads whole before it is chosen, on as many lines as it takes. Ionic keeps the
// label of an `ion-radio` (or `ion-checkbox`) on one line and ends it in «…», and `ion-select-popover` paints in
// `ion-app`, out of reach of a form's own styles, so the rule lives in the shared theme (@erplora/ui, polish.css). In
// Chrome, in Spanish, against hub `a`: what is measured is the label against its own box (`scrollWidth`, `scrollHeight`,
// `clientWidth`, `clientHeight`), never a capture. Menus and combos › «New menu» › «How is it sold?» at 375, 390, on a
// tablet and on a desktop; the same list with several choices, as the website's categories draw it; and the 249
// countries of the invoice's issuer, where it also has to go on scrolling down to the last one. Nothing is saved.
// flow: COMBO-F02, INVOICE-F21, ui:theme
import { type Browser, expect, type Page, test } from '@playwright/test';

import { A, capture, login, settled, shown } from './helpers';

const FORM_VIEWPORTS = [
  { label: '375x667', width: 375, height: 667, longOptionLines: 2 },
  { label: '390x844', width: 390, height: 844, longOptionLines: 2 },
  { label: '820x1180', width: 820, height: 1180, longOptionLines: 1 },
  { label: '1440x900', width: 1440, height: 900, longOptionLines: 1 },
];
const SUPPLY = '[data-testid=combo-menu-form-supply_kind]';
const COUNTRY = '[data-testid=invoice-issuer-country]';
const POPOVER = 'ion-select-popover';
const OPTIONS = `${POPOVER} ion-radio, ${POPOVER} ion-checkbox`;

async function spanishPage(browser: Browser, viewport: { width: number; height: number }, path: string) {
  const context = await browser.newContext({ baseURL: A, viewport, locale: 'en-US' });
  const page = await context.newPage();
  await login(page, A, path);
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  await page.goto(`${A}${path}`);
  await expect(page.locator('html')).toHaveAttribute('lang', /^es/);
  return { context, page };
}

async function openNewMenuForm(browser: Browser, viewport: { width: number; height: number }) {
  const opened = await spanishPage(browser, viewport, '/combo/menus');
  await shown(opened.page).locator('[data-testid=combo-menus-add]').click();
  await expect(opened.page.locator(SUPPLY)).toBeVisible();
  return opened;
}

interface OptionBox {
  text: string;
  clientHeight: number;
  /** Why this option cannot be read whole; empty when it can. */
  cut: string[];
}

/** Each option of the open list: its label against the label's own box, and that box against its row. */
function measureOptions(page: Page): Promise<OptionBox[]> {
  return page.evaluate((selector) => {
    return [...document.querySelectorAll(selector)].map((option) => {
      const label = option.shadowRoot!.querySelector<HTMLElement>('[part~="label"]')!;
      const row = option.closest('ion-item')!.getBoundingClientRect();
      const box = label.getBoundingClientRect();
      const cut: string[] = [];
      if (label.scrollWidth > label.clientWidth) cut.push(`${label.scrollWidth - label.clientWidth}px past its width`);
      if (label.scrollHeight > label.clientHeight) cut.push(`${label.scrollHeight - label.clientHeight}px past its height`);
      if (box.top < row.top || box.bottom > row.bottom) cut.push('taller than its row');
      return { text: option.textContent!.trim(), clientHeight: label.clientHeight, cut };
    });
  }, OPTIONS);
}

/** «<option>: <why>» for every option that cannot be read whole. */
const cutShort = (options: OptionBox[]): string[] => options.flatMap((o) => o.cut.map((why) => `${o.text}: ${why}`));

/** Opens «How is it sold?» and, once the list has settled, measures its two options: the long one, then the short one. */
async function openSupplyList(page: Page): Promise<OptionBox[]> {
  await page.locator(SUPPLY).click();
  await expect(page.locator(OPTIONS)).toHaveCount(2);
  await settled(page);
  return measureOptions(page);
}

for (const viewport of FORM_VIEWPORTS) {
  test(`COMBO-F02: both ways of selling read whole in their list at ${viewport.label}, and a tap on either line chooses`, async ({ browser }) => {
    const { context, page } = await openNewMenuForm(browser, viewport);
    expect(cutShort(await openSupplyList(page)), 'as the form opens').toEqual([]);

    // With the short way of selling chosen the field is at its narrowest, and the list takes its width from the field.
    await page.locator(OPTIONS).nth(1).click();
    await expect(page.locator(POPOVER)).toHaveCount(0);
    await expect(page.locator('[data-testid=combo-menu-form-help-goods]')).toHaveAttribute('data-active', 'true');

    const [long, short] = await openSupplyList(page);
    expect(long.text).toBe('Se consume en el local (servicio de restauración)');
    expect(cutShort([long, short]), 'with the short one chosen').toEqual([]);
    expect(long.clientHeight / short.clientHeight).toBe(viewport.longOptionLines);
    await capture(page, `FIX-HUB-SELECT-LONG-OPTION-${viewport.label}`);

    const box = (await page.locator(OPTIONS).first().boundingBox())!;
    await page.locator(OPTIONS).first().click({ position: { x: box.width / 2, y: box.height - 8 } });
    await expect(page.locator(POPOVER)).toHaveCount(0);
    await expect(page.locator('[data-testid=combo-menu-form-help-service]')).toHaveAttribute('data-active', 'true');
    await context.close();
  });
}

// Its options are `ion-checkbox`, whose box leaves the label less room than a radio's: the website's categories
// (`interface="popover" multiple`, apps/website/frontend/components/CategoryPicker.vue) are named by each business, so
// the same select stands in, with Ionic's own list.
test('COMBO-F02: a long option of a list with several choices reads whole at 375x667', async ({ browser }) => {
  const { context, page } = await openNewMenuForm(browser, FORM_VIEWPORTS[0]);
  await page.locator(SUPPLY).evaluate((select: Element & { multiple?: boolean }) => {
    select.multiple = true;
  });
  const [long, short] = await openSupplyList(page);
  expect(cutShort([long, short])).toEqual([]);
  expect(long.clientHeight / short.clientHeight).toBe(2);
  await context.close();
});

// 320 is the narrowest phone still in use, and where the longest names of this list need their second line.
test('INVOICE-F21: every country reads whole at 320x568 and the list scrolls down to the last one, which can be chosen', async ({ browser }) => {
  const { context, page } = await spanishPage(browser, { width: 320, height: 568 }, '/invoice/issuer');
  await page.locator(COUNTRY).click();
  await expect(page.locator(OPTIONS).first()).toBeVisible();
  await settled(page);

  const options = await measureOptions(page);
  expect(options.length).toBeGreaterThan(200);
  expect(cutShort(options)).toEqual([]);
  const oneLine = Math.min(...options.map((o) => o.clientHeight));
  expect(options.filter((o) => o.clientHeight > oneLine).length).toBeGreaterThan(0);

  const scroll = await page.evaluate((selector) => {
    const scroller = document.querySelector('ion-select-popover')!.closest('ion-popover')!.shadowRoot!.querySelector('.popover-content')!;
    const room = scroller.scrollHeight - scroller.clientHeight;
    scroller.scrollTop = scroller.scrollHeight;
    const last = [...document.querySelectorAll(selector)].at(-1)!;
    return { room, scrolled: scroller.scrollTop, gap: scroller.getBoundingClientRect().bottom - last.getBoundingClientRect().bottom };
  }, OPTIONS);
  expect(scroll.room).toBeGreaterThan(0);
  expect(scroll.scrolled).toBe(scroll.room);
  expect(scroll.gap).toBeGreaterThanOrEqual(0);

  const last = options.at(-1)!.text;
  await page.locator(OPTIONS).last().click();
  await expect(page.locator(POPOVER)).toHaveCount(0);
  await expect(page.locator(COUNTRY)).toContainText(last);
  await context.close();
});
