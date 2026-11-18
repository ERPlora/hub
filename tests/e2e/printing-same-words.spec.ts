// flow: PRINTING-F03, PRINTING-F18 — hub#1470: in Printing a refused field loses its mark as soon as it is corrected,
// without saving again, and only its own. «New printer» is refused for its name, address and port with the same words;
// «Print from this device» for its name and its printers, and ticking another printer takes the printers' notice
// alone. At 390, 834 and 1440, and once more in Spanish. Saves are refused in the browser, so nothing is created.
import { expect, type Page, test } from '@playwright/test';

import { A, api, capture, login, psql, shown } from './helpers';
import { dialog } from './inventory-helpers';
import { stamp } from './sale-helpers';
import {
  expectMarked,
  expectUnmarked,
  refuseWithTheSameWords,
  type SameWordsWindow,
  testEachSameWordsCase,
  testTheMarksGoOneByOne,
} from './same-words-helpers';
import { discardChanges } from './unsaved-back-helpers';

const TAG = `E2E1470 ${stamp()}`;
const SAME_WORDS = { en: 'Check this field.', es: 'Revisa este campo.' };

type Language = keyof typeof SAME_WORDS;

/** «New printer»: a name and an address turn «Save» on; the port keeps its 9100. */
const PRINTER: SameWordsWindow = {
  app: 'PRINTING-PRINTER',
  page: '/printing/printers',
  add: 'printing-printers-add',
  testid: 'printing-printer',
  save: '**/api/printing/printers',
  fill: async (form) => {
    await form.locator('[data-testid=printing-printer-name] input').fill(`${TAG} Till`);
    await form.locator('[data-testid=printing-printer-address] input').fill('192.168.1.50');
  },
  keys: ['name', 'address', 'port'],
  created: `select count(*) from printing_printer where name like '${TAG}%' and name not like '${TAG} Reach%'`,
};

testTheMarksGoOneByOne([PRINTER]);

/** The two active printers the device window offers, made by this file. */
let reached: string[] = [];

test.describe('Print from this device', () => {
  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ baseURL: A });
    await login(await context.newPage(), A, '/printing/devices');
    reached = [];
    for (const [name, address] of [
      [`${TAG} Reach Till`, '10.0.0.71'],
      [`${TAG} Reach Bar`, '10.0.0.72'],
    ]) {
      const created = await api<{ id: string }>(context, A, 'POST', '/printing/printers', { name, kind: 'network', address, usage: 'receipt' });
      expect(created.status, JSON.stringify(created.data)).toBe(201);
      reached.push(created.data.id);
    }
    await context.close();
  });

  test.afterAll(() => {
    psql(`delete from printing_printer where name like '${TAG}%'`);
  });

  async function nameAndPrintersOneByOne(page: Page, language: Language, label: string): Promise<void> {
    const words = SAME_WORDS[language];
    await shown(page).locator('[data-testid=printing-devices-add]').click();
    const modal = dialog(page, 'printing-device');
    const name = modal.locator('[data-testid=printing-device-name]');
    const notice = modal.locator('[data-testid=printing-device-printers-error]');
    await name.locator('input').fill(`${TAG} Counter`);
    await modal.locator(`[data-testid=printing-device-printer-${reached[0]}]`).click();

    await refuseWithTheSameWords(page, '**/api/printing/devices', ['name', 'printers'], words);
    await modal.locator('[data-testid=printing-device-submit]').click();
    await expectMarked(name, words);
    await expect(notice).toHaveText(words);
    await capture(page, `CLOSE-PRINTING-hub1470-device-refused-${label}`);

    await modal.locator(`[data-testid=printing-device-printer-${reached[1]}]`).click();
    await expect(notice).toBeHidden();
    await expectMarked(name, words);
    await capture(page, `CLOSE-PRINTING-hub1470-device-printer-ticked-${label}`);

    const typed = name.locator('input');
    await typed.fill(`${await typed.inputValue()} 2`);
    await expectUnmarked(name, words);
    await capture(page, `CLOSE-PRINTING-hub1470-device-name-typed-${label}`);

    await page.unroute('**/api/printing/devices');
    await modal.locator('[data-testid=printing-device-cancel]').click();
    await discardChanges(page);
    await expect(modal).toBeHidden();
    expect(psql(`select count(*) from printing_printdevice where name like '${TAG}%'`)).toBe('0');
  }

  testEachSameWordsCase(
    ({ size }) => `hub#1470 PRINTING-F18 at ${size.label}: the name and the printers refused with the same words lose their marks one by one`,
    '/printing/devices',
    (page, { language, size }) => nameAndPrintersOneByOne(page, language, size.label),
  );
});
