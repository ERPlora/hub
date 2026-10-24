// flow: BASE-G52 (base/WORKBOOK.md, «Entrar con la cuenta de erplora.com»; APP-BASE-3)
// A link to a tab of a screen (`/settings#data`, `/system#plan`) opened without a session goes through erplora.com's
// sign-in and back to that tab: the part after `#` never reaches a server, so the jump must not drop it. At each size,
// in a fresh browser (no session on the hub nor on erplora.com): the SaaS's form, then the hub, on the address asked.
import { expect, test } from '@playwright/test';

import { A, login, shot, shown, untilStill } from './helpers';

const SIZES = [
  { name: '390', width: 390, height: 844 },
  { name: '834', width: 834, height: 1112 },
  { name: '1440', width: 1440, height: 900 },
] as const;

const LINKS = [
  { path: '/settings#data', tab: 'tab-data', shown: 'data-sections' },
  { path: '/system#plan', tab: 'tab-plan', shown: 'system-plan-devices' },
] as const;

for (const size of SIZES) {
  test(`BASE-G52: a link to a tab opened without a session lands on that tab after erplora.com, at ${size.name}`, async ({
    browser,
  }) => {
    for (const link of LINKS) {
      const context = await browser.newContext({ locale: 'en-US', viewport: { width: size.width, height: size.height } });
      const page = await context.newPage();
      try {
        // `fresh`: through erplora.com's sign-in for real, never a session kept from another spec.
        await login(page, A, link.path, undefined, { fresh: true });
        await expect(page).toHaveURL(`${A}${link.path}`);
        await expect(shown(page).getByTestId(link.tab)).toHaveClass(/segment-button-checked/);
        await expect(shown(page).getByTestId(link.shown).first()).toBeVisible();
        if (link.path === '/system#plan') {
          await untilStill(page);
          await page.screenshot({ path: shot(`APP-BASE-3-BASE-G52-deep-link-${size.name}`), fullPage: true });
        }
      } finally {
        await context.close();
      }
    }
  });
}
