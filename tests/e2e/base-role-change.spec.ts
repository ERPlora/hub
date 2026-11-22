// flow: BASE-F13 and BASE-F118 (base/WORKBOOK.md)
// erplora.com changes the role of a person who has a screen open, and the screen follows it in place: an employee on
// Taxes' «Rules» sees «No access»; made a manager, the screen opens; back to employee, «No access» again. Never a
// reload nor a new sign-in: the same page and the same session all along. The photo is sent the way the SaaS sends it
// (`PUT /internal/hubs/{id}/state`, signed) with every person of `a`, and `a`'s photo and roles are put back after.
import { createHmac } from 'node:crypto';

import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, capture, EMPLOYEE, hostPage, psql, shown, testid, THREE_SIZES } from './helpers';
import { STACK } from './stack';

/** The secret `/internal` is signed with; the local default of both projects. */
const SECRET = process.env.INTERNAL_SHARED_SECRET || 'local-internal-shared-secret';
/** The copy the run keeps of `a`'s photo. */
const BACKUP = 'e2e_base_role_change_photo_before';

type Member = { user_id: string; role: string };

let hubId = '';
let version = Math.floor(Date.now() / 1000);
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
  version += 1;
  const listed = members.map((member) => ({ ...member, role: roles[member.user_id] ?? member.role }));
  const body = JSON.stringify({ hub_id: hubId, slug: 'a', version, members: listed });
  const timestamp = String(Math.floor(Date.now() / 1000));
  const signature = createHmac('sha256', SECRET).update(`${timestamp}.${body}`).digest('hex');
  const response = await fetch(`http://127.0.0.1:${STACK.hubPort}/internal/hubs/${hubId}/state`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', 'X-Erplora-Timestamp': timestamp, 'X-Erplora-Signature': signature },
    body,
  });
  const answer = await response.text();
  expect(response.status, answer).toBe(200);
  expect(JSON.parse(answer)).toMatchObject({ applied: true, version });
}

/** The Hub's session `context` holds for `a`. */
async function sessionOf(context: BrowserContext): Promise<string | undefined> {
  return (await context.cookies(A)).find((cookie) => cookie.name === 'sessionid' && cookie.domain === new URL(A).hostname)
    ?.value;
}

const stillHere = (page: Page): Promise<boolean | undefined> =>
  page.evaluate(() => (window as { e2eStillHere?: boolean }).e2eStillHere);

test.beforeAll(() => {
  hubId = psql("select id from base_hub where slug = 'a'");
  version = Math.max(version, Number(psql(`select state_version from base_hub where id = '${hubId}'`)));
  psql(
    [
      `drop table if exists ${BACKUP}`,
      `create table ${BACKUP} as select id, state, state_version from base_hub where id = '${hubId}'`,
    ].join('; '),
  );
});

test.afterAll(async () => {
  if (members.length) await pushRoles({});
  psql(
    [
      `update base_hub h set state = b.state, state_version = b.state_version from ${BACKUP} b where b.id = h.id`,
      `drop table ${BACKUP}`,
    ].join('; '),
  );
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
