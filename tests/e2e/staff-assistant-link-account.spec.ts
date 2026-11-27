// «La ficha de Ana engánchala a su usuario»: the model reads the accounts of the business in the list of the record
// form's «Hub user» (staff.account.list), sends the id it read, and the card says the record and the name of the account
// it links; the yes links them. End to end with the stack's SaaS gateway and the e2e's provider (assistant-provider.ts,
// `E2E-ASK <tool> <JSON>`). The step «Ask the assistant» of Automations offers that read by its name too. What this
// file creates is named «E2E Enlace» and goes away before and after.
// flow: STAFF-F03 BASE-F97 FLOW-F37
import { expect, test } from '@playwright/test';

import { AN_ID, cardSpec, datumOf, VIEWPORTS } from './assistant-card-helpers';
import { card, decide, lastAnswer, openPanelAtTheDesk, ownerIn } from './assistant-panel';
import { signedIn } from './flow-helpers';
import { A, api, capture, psql, shown } from './helpers';
import { post } from './service-helpers';
import { pick } from './task-helpers';

const TAG = 'E2E Enlace';

cardSpec(['staff', 'flow'], () => psql(`delete from staff_member where first_name like '${TAG}%'`));

type Account = { user_id: string; name: string };

test('the card of linking a record to an account says the account, and the yes links it', async ({ browser }) => {
  const [context, page] = await ownerIn(browser, 'es');
  const record = await post<{ id: string; full_name: string }>(context, '/staff/members', {
    first_name: `${TAG} Ana`,
    last_name: 'Martín',
  });
  const listed = await api<{ rows: Account[] }>(context, A, 'GET', '/staff/accounts?limit=100');
  expect(listed.status).toBe(200);
  const [account] = listed.data.rows;
  expect(account, 'the owner of a is an account of the business').toBeDefined();

  await openPanelAtTheDesk(page);
  const linked = await datumOf(page, 'staff__member__update', { id: record.id, user_id: account.user_id }, 'user_id');
  expect(linked.value).toBe(account.name);
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(card(page)).toContainText(record.full_name);
    await expect(card(page)).toContainText(account.name);
    await expect(card(page)).not.toContainText(AN_ID);
    await capture(page, `hub-2681-link-account-es-${vp.label}`);
  }
  await page.setViewportSize({ width: 1440, height: 900 });

  await card(page).locator('[data-testid="assistant-confirm-input"] input').fill('CONFIRMAR');
  await decide(page, 'submit');
  await expect(lastAnswer(page)).not.toBeEmpty();
  const detail = await api<{ user_id: string | null }>(context, A, 'GET', `/staff/members/detail?id=${record.id}`);
  expect(detail.data.user_id).toBe(account.user_id);
  await context.close();
});

const ACCOUNTS_READ = 'Look for the accounts a staff record can be linked to';

for (const vp of VIEWPORTS) {
  test(`the step «Ask the assistant» offers the accounts a record can be linked to at ${vp.label}`, async ({ browser }) => {
    const { context, page } = await signedIn(browser, '/flow/automations/new', vp);
    const editor = shown(page);
    await editor.locator('[data-testid=flow-editor-add-assistant]').click();
    await pick(page, 'flow-assistant-addtool-s1', 'accounts', ACCOUNTS_READ);
    await expect(editor.locator('[data-testid="flow-assistant-tool-s1-staff.account.list"]')).toHaveText(ACCOUNTS_READ);
    await capture(page, `hub-2681-flow-tool-${vp.label}`);
    await context.close();
  });
}
