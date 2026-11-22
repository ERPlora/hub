// What only the owner of a business does (BASE-F11, BASE-F37): buying for it («Upgrade plan» at the foot of the menu),
// resetting it and downloading its copies. An administrator runs the business but does not own it: in Settings › Data ›
// Reset they still undo imports, and where the reset and the copies would be they read that only the owner can, while
// «Upgrade plan» is not in their menu. The owner's same screen is the positive control. The administrator is the SaaS's
// `employee@example.com` given that role in `a` for this spec, as erplora.com would, and put back after it.
import { expect, test } from '@playwright/test';

import { A, capture, EMPLOYEE, hostPage, psql, shown, THREE_SIZES } from './helpers';

/** The Hub's local copy of the SaaS's employee (`saas:<id>`), never the staff one. */
const EMPLOYEE_USER = `(select id from auth_user where email = '${EMPLOYEE.email}' and username like 'saas:%')`;
const RESET = `${A}/settings?data=reset#data`;

const giveRole = (role: string) => psql(`update base_membership set role = '${role}' where host = 'a' and user_id = ${EMPLOYEE_USER}`);

test('BASE-F37: an administrator neither resets the business nor sees its copies, nor is offered «Upgrade plan»', async ({ browser }) => {
  const admin = await hostPage(browser, A, { credentials: EMPLOYEE });
  giveRole('hub_admin');
  try {
    for (const size of THREE_SIZES) {
      await admin.page.setViewportSize({ width: size.width, height: size.height });
      await admin.page.goto(RESET);
      const notice = shown(admin.page).locator('[data-testid="reset-owner-only"]');
      await expect(notice).toHaveText("Only the business's owner can reset it or download the copies of its data.");
      for (const hook of ['reset-section', 'reset-submit', 'dumps-card', 'reset-admin-only']) {
        await expect(shown(admin.page).locator(`[data-testid="${hook}"]`), hook).toHaveCount(0);
      }
      await expect(admin.page.locator('[data-testid="upgrade-plan"]')).toHaveCount(0);
      await capture(admin.page, `owner-only-admin-reset-${size.label}`, { fullPage: true });
    }
  } finally {
    giveRole('hub_employee');
    await admin.context.close();
  }
});

test('BASE-F37: the owner resets the business and sees its copies, and has «Upgrade plan»', async ({ browser }) => {
  const owner = await hostPage(browser, A);
  try {
    for (const size of THREE_SIZES) {
      await owner.page.setViewportSize({ width: size.width, height: size.height });
      await owner.page.goto(RESET);
      await expect(shown(owner.page).locator('[data-testid="dumps-card"]')).toBeVisible();
      await expect(shown(owner.page).locator('[data-testid="reset-owner-only"]')).toHaveCount(0);
      await expect(owner.page.locator('[data-testid="upgrade-plan"]')).toHaveCount(1);
      await capture(owner.page, `owner-only-owner-reset-${size.label}`, { fullPage: true });
    }
  } finally {
    await owner.context.close();
  }
});
