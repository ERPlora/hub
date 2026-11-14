// flow: SERVICE-F12 — hub#888: in Services › Vouchers › «New package», fields refused with the same words lose their
// marks one by one as each is corrected, and the lines refused as a whole (a service twice) lose the notice under them
// at a change to the lines: every field carries the name the server refuses it by, and the lines are a group that says
// each change. At 390, 834 and 1440, and once more in Spanish. The refusal is answered in the browser (`page.route`), so
// nothing is created.
import { expect, type Locator, test } from '@playwright/test';

import { capture, psql, shown } from './helpers';
import { VIEWPORTS } from './sale-helpers';
import { expectMarked, refuseWithTheSameWords, type SameWordsWindow, testTheMarksGoOneByOne } from './same-words-helpers';
import { cleanUp, named, ownerPage, pick, post, TAG } from './service-helpers';

test.beforeAll(cleanUp);
test.afterAll(cleanUp);

const LABEL = 'Same words';

/** A name and a service of its own on the first line turn «Create package» on; Validity and Uses are left empty, so
 *  typing in them is a change. */
const PACKAGE: SameWordsWindow = {
  app: 'SERVICE-PACKAGE',
  page: '/service/packages',
  add: 'service-packages-add',
  testid: 'service-package-form',
  save: '**/api/service/packages',
  fill: async (form: Locator) => {
    const cut = await post<{ name: string }>(form.page().context(), '/service/services', {
      name: named(`${LABEL} Cut`),
      price: 2000,
      tax_category_key: 'service.generic',
    });
    await form.locator('[data-testid=service-package-form-name] input').fill(named(LABEL));
    await pick(form.page(), 'service-package-form-line-service-0', cut.name.split(' ').pop()!, cut.name);
  },
  keys: ['validity_days', 'name', 'max_uses'],
  created: `select count(*) from service_package where name like '${TAG} ${LABEL}%'`,
};

testTheMarksGoOneByOne([PACKAGE]);

for (const size of VIEWPORTS) {
  test(`hub#888 SERVICE-PACKAGE at ${size.label}: «Add service» takes away the refusal of the lines, the name keeps its own`, async ({ browser }) => {
    const { context, page } = await ownerPage(browser, PACKAGE.page, { width: size.width, height: size.height });
    const words = 'Check this field.';
    try {
      await shown(page).locator(`[data-testid=${PACKAGE.add}]`).click();
      const form = page.locator(`ion-modal[data-testid=${PACKAGE.testid}]`);
      await expect(form).toBeVisible();
      await PACKAGE.fill(form);
      const name = form.locator('[data-testid=service-package-form-name]');
      const lines = form.locator('[data-testid=service-package-form-no-lines]');

      await refuseWithTheSameWords(page, PACKAGE.save, ['name', 'items'], words);
      await form.locator(`[data-testid=${PACKAGE.testid}-submit]`).click();
      await expectMarked(name, words);
      await expect(lines).toContainText(words);
      await lines.scrollIntoViewIfNeeded();
      await capture(page, `CLOSE-SERVICE-PACKAGE-hub888-lines-refused-${size.label}`);

      // A new empty line types nothing: the group of the lines says the change.
      await form.locator('[data-testid=service-package-form-add-line]').click();
      await expect(lines).toBeHidden();
      await expectMarked(name, words);
      await capture(page, `CLOSE-SERVICE-PACKAGE-hub888-lines-changed-${size.label}`);

      await page.unroute(PACKAGE.save);
      expect(psql(PACKAGE.created)).toBe('0');
    } finally {
      await context.close();
    }
  });
}
