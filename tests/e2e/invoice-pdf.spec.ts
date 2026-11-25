// «Download PDF» of an invoice (INVOICE-F25) in Chrome: an invoice with a withholding and a due date downloads as a real
// PDF under its number, opened here by a PDF reader of its own: it says what the screen shows, with the record's QR
// legend. The accountancy firm's and the employee's button is the same one.
import { readFileSync } from 'node:fs';

import { expect, type Page, test } from '@playwright/test';
import { getDocument } from 'pdfjs-dist/legacy/build/pdf.mjs';

import { A, EMPLOYEE, login, settled, shown } from './helpers';
import { cleanInvoices, flowShots, issueByHand, readyToInvoice } from './invoice-helpers';
import { stamp } from './sale-helpers';

const CUSTOMER = `e2e PDF ${stamp()}`;
const RECIPIENT = { customer_name: CUSTOMER, customer_tax_id: 'B12345674', customer_address: 'Calle Luna 3' };
let invoice: { id: string; number: string };

test.beforeAll(async ({ browser }) => {
  const context = await readyToInvoice(browser);
  invoice = await issueByHand(context, {
    ...RECIPIENT,
    lines: [{ description: 'Consultoría', quantity: '1', unit_price: 10000, tax_rate: '21' }],
    withholding_rate: 15,
  });
  await context.close();
});

test.afterAll(() => cleanInvoices());

/** The words of the PDF the button saves, and its title and language, as a reader of its own opens it. */
async function downloaded(page: Page): Promise<{ name: string; words: string; title: string; language: string; pages: number }> {
  const download = page.waitForEvent('download');
  await shown(page).locator('[data-testid=invoice-detail-pdf]').click();
  const file = await download;
  const document = await getDocument({ data: new Uint8Array(readFileSync((await file.path()) as string)) }).promise;
  const metadata = await document.getMetadata();
  const texts: string[] = [];
  for (let n = 1; n <= document.numPages; n += 1) {
    const { items } = await (await document.getPage(n)).getTextContent();
    texts.push(...items.map((item) => ('str' in item ? item.str : '')));
  }
  const info = metadata.info as { Title?: string; Language?: string };
  return {
    name: file.suggestedFilename(),
    words: texts.join(' ').replace(/\s+/g, ' '),
    title: info.Title ?? '',
    language: info.Language ?? '',
    pages: document.numPages,
  };
}

async function open(page: Page): Promise<void> {
  await page.goto(`${A}/invoice/invoices/${invoice.id}`);
  await expect(shown(page).locator('[data-testid=invoice-detail-title]')).toContainText(invoice.number);
}

test('«Download PDF» saves the invoice as a real PDF under its number, with what the screen shows', async ({ page }) => {
  await login(page, A, '/invoice/invoices');
  await open(page);
  await expect(shown(page).locator('[data-testid=invoice-verifactu]')).toBeVisible();

  const pdf = await downloaded(page);

  expect(pdf.name).toBe(`${invoice.number}.pdf`);
  expect(pdf.pages).toBe(1);
  expect([pdf.title, pdf.language]).toEqual([`Invoice ${invoice.number}`, 'en']);
  for (const said of [invoice.number, CUSTOMER, 'B12345674', 'Consultoría', '€121.00', '-€15.00', '€106.00', 'QR tributario:', 'VERI*FACTU']) {
    expect(pdf.words).toContain(said);
  }
  await flowShots(page, 'F25', async (shot) => {
    await expect(shown(shot).locator('[data-testid=invoice-detail-pdf]')).toBeVisible();
  });
});

const ACTIONS = ['print', 'pdf', 'email', 'back'].map((name) => `[data-testid=invoice-detail-${name}]`);

test('the buttons of the invoice fit in the three sizes, as tall as each other', async ({ page }) => {
  await login(page, A, '/invoice/invoices');
  await open(page);
  for (const [width, height] of [[1440, 900], [820, 1180], [375, 667]]) {
    await page.setViewportSize({ width, height });
    await settled(page);
    const boxes = await Promise.all(ACTIONS.map(async (one) => (await shown(page).locator(one).boundingBox())!));
    expect(boxes.map((box) => Math.round(box.height))).toEqual([44, 44, 44, 44]);
    for (const box of boxes) {
      expect(box.x).toBeGreaterThanOrEqual(0);
      expect(box.x + box.width).toBeLessThanOrEqual(width);
    }
    const inARow = boxes.every((box) => Math.abs(box.y - boxes[0].y) <= 1);
    expect(inARow || width === 375, `the buttons of ${width}px are in a row`).toBe(true);
  }
});

test('an employee downloads their own invoices', async ({ browser }) => {
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/invoice/invoices', EMPLOYEE);
  const mine = await issueByHand(context, { ...RECIPIENT, lines: [{ description: 'Curso', quantity: '1', unit_price: 5000, tax_rate: '21' }] });
  await page.goto(`${A}/invoice/invoices/${mine.id}`);

  expect((await downloaded(page)).name).toBe(`${mine.number}.pdf`);
  await context.close();
});
