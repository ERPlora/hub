// flow: BASE-F13 and BASE-F118 (base/WORKBOOK.md)
// erplora.com changes the role of a person who has a screen open, and the screen follows it in place: an employee on
// Taxes' «Rules» sees «No access»; made a manager, the screen opens; back to employee, «No access» again. Never a
// reload nor a new sign-in: the same page and the same session all along. The photo is sent the way the SaaS sends it
// (`PUT /internal/hubs/{id}/state`, signed) with every person of `a`, and `a`'s photo and roles are put back after.
import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, capture, EMPLOYEE, hostPage, psql, shown, testid, THREE_SIZES } from './helpers';
import { keepPhotoOfA, type PhotoOfA } from './saas-photo';

type Member = { user_id: string; role: string };

let photo: PhotoOfA | undefined;
let members: Member[] = [];

/** erplora.com's people of `a`, with the role each has in the Hub now: the photo lists them all or drops the rest. */
function peopleOfA(): Member[] {
  const rows = psql(
    "select substr(u.username, 6) || ' ' || m.role from base_membership m join auth_user u on u.id = m.user_id " +
      "where m.host = 'a' and u.username like 'saas:%' order by u.username",
  );
  return rows.split('\n').filter(Boolean).map((row) => {
    const [user_id, role] = row.split(' ');
    return { user_id, role };
  });
}

/** The SaaS's photo of `a` with `roles` changed by account; every other person keeps theirs. */
async function pushRoles(roles: Record<string, string>): Promise<void> {
  if (!photo) throw new Error('No photo of a was kept before the run.');
  await photo.send({ members: members.map((member) => ({ ...member, role: roles[member.user_id] ?? member.role })) });
}

/** The Hub's session `context` holds for `a`. */
async function sessionOf(context: BrowserContext): Promise<string | undefined> {
  return (await context.cookies(A)).find((cookie) => cookie.name === 'sessionid' && cookie.domain === new URL(A).hostname)
    ?.value;
}

const stillHere = (page: Page): Promise<boolean | undefined> =>
  page.evaluate(() => (window as { e2eStillHere?: boolean }).e2eStillHere);

test.beforeAll(() => {
  photo = keepPhotoOfA('e2e_base_role_change_photo_before');
});

test.afterAll(async () => {
  if (members.length) await pushRoles({});
  photo?.putBack();
});

test('BASE-F13: a role changed on erplora.com turns the open screen into «No access», or opens it, without a reload', async ({
  browser,
}) => {
  const { context, page } = await hostPage(browser, A, { next: '/tax/rules', credentials: EMPLOYEE });
  try {
    members = peopleOfA();
    const employee = psql(`select substr(username, 6) from auth_user where email = '${EMPLOYEE.email}'`);
    expect(members.find((member) => member.user_id === employee)?.role).toBe('hub_employee');
    await expect(testid(page, 'no-access')).toBeVisible();
    const session = await sessionOf(context);
    await page.evaluate(() => Object.assign(window, { e2eStillHere: true }));

    await pushRoles({ [employee]: 'hub_manager' });
    await expect(shown(page).locator('[data-testid=tax-rules-add]')).toBeVisible();
    await expect(testid(page, 'no-access')).toHaveCount(0);

    await pushRoles({ [employee]: 'hub_employee' });
    await expect(testid(page, 'no-access')).toBeVisible();
    await expect(shown(page).locator('[data-testid=tax-rules-add]')).toHaveCount(0);

    expect(new URL(page.url()).pathname).toBe('/tax/rules');
    expect(await stillHere(page)).toBe(true);
    expect(await sessionOf(context)).toBe(session);
    for (const size of THREE_SIZES) {
      await page.setViewportSize(size);
      await expect(testid(page, 'no-access')).toBeVisible();
      await capture(page, `base-role-change-${size.label}`);
    }
    expect(await stillHere(page)).toBe(true);
  } finally {
    await context.close();
  }
});
