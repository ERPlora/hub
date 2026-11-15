// Staff for an employee (`hub_employee`: view the directory, roles, schedules and who is away; ask for
// their own time off; WORKBOOK «Quién puede qué»): no «+» on Staff, Roles or Schedules, no row action,
// no row to open, no «Rate/h», no Settings tab and Settings itself says «You do not have permission»;
// the API refuses every write but asking for time off with 403 `permission_denied`. The owner is the
// positive control: the same hooks are there for who may manage.
import { type Browser, expect, test } from '@playwright/test';

import { A, api, type Credentials, EMPLOYEE, shot, shown } from './helpers';
import { signedIn as signedInAt } from './flow-helpers';
import { staffCleanUp } from './staff-helpers';

type Envelope = { error?: { code: string } };
const TAG = 'E2E';

const cleanup = (): void => staffCleanUp(TAG);

test.beforeAll(cleanup);
test.afterAll(cleanup);

/** Someone (the owner unless `credentials`) on `next` at a desk's size, in English. */
const signedIn = (browser: Browser, next: string, credentials?: Credentials) => signedInAt(browser, next, { width: 1280, height: 860 }, credentials);

test('an employee reads Staff, Roles and Schedules without a single write button, and the API agrees', async ({ browser }) => {
  const owner = await signedIn(browser, '/staff/members');
  const employee = await signedIn(browser, '/staff/members', EMPLOYEE);
  try {
    const member = await api<{ id: string }>(owner.context, A, 'POST', '/staff/members', { first_name: `${TAG} Rita`, last_name: `Readonly${Date.now().toString(36)}` });
    expect(member.status).toBe(201);

    // Positive control: the owner has «+», the actions and the pay.
    const ownerView = shown(owner.page);
    await ownerView.locator('[data-testid=staff-members-row]').first().waitFor({ state: 'visible' });
    await expect(ownerView.locator('[data-testid=staff-members-add]')).toBeVisible();
    await expect(ownerView.locator(`[data-testid^=staff-members-row-${member.data.id}-]`).first()).toBeAttached();
    // Staff, Roles, Time Off, Schedules, Commissions and Settings (STAFF-F21: Commissions only with the pay).
    await expect(ownerView.locator('ion-footer ion-segment-button')).toHaveCount(6);

    // The employee: the list, nothing to write.
    const view = shown(employee.page);
    await view.locator('[data-testid=staff-members-row]').first().waitFor({ state: 'visible' });
    await expect(view.locator('[data-testid=staff-members-add]')).toHaveCount(0);
    await expect(view.locator(`[data-testid^=staff-members-row-${member.data.id}-]`)).toHaveCount(0);
    await expect(view.locator('[role=columnheader]', { hasText: 'Rate/h' })).toHaveCount(0);
    await expect(ownerView.locator('[role=columnheader]', { hasText: 'Rate/h' })).toBeVisible();
    await expect(view.locator('ion-footer ion-segment-button')).toHaveCount(4);
    await employee.page.screenshot({ path: shot('staff-employee-members') });

    for (const [path, table] of [
      ['/staff/roles', 'staff-roles'],
      ['/staff/schedules', 'staff-schedules'],
    ] as const) {
      await employee.page.goto(`${A}${path}`);
      const section = shown(employee.page);
      await section.locator(`[data-testid=${table}-empty], [data-testid=${table}-row]`).first().waitFor({ state: 'visible' });
      await expect(section.locator(`[data-testid=${table}-add]`), path).toHaveCount(0);
      await employee.page.screenshot({ path: shot(`staff-employee-${table.replace('staff-', '')}`) });
    }

    await employee.page.goto(`${A}/staff/settings`);
    await expect(shown(employee.page).locator('[data-testid=staff-settings-forbidden]')).toContainText('You do not have permission');

    // The API refuses every write of a manager.
    const writes: ReadonlyArray<readonly [string, unknown]> = [
      ['/staff/members', { first_name: `${TAG} X`, last_name: 'Y' }],
      ['/staff/members/update', { id: member.data.id, phone: '1' }],
      ['/staff/members/terminate', { id: member.data.id }],
      ['/staff/roles', { name: `${TAG} By employee` }],
      ['/staff/settings', { default_break_duration: 30 }],
    ];
    for (const [path, body] of writes) {
      const res = await api<Envelope>(employee.context, A, 'POST', path, body);
      expect(res.status, path).toBe(403);
      expect(res.data.error?.code, path).toBe('permission_denied');
    }
    expect((await api(employee.context, A, 'GET', '/staff/members?limit=1')).status).toBe(200);
  } finally {
    await owner.context.close();
    await employee.context.close();
  }
});
