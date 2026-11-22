// flow: STAFF-F01, STAFF-F02 — the team's email and phone reach only whoever sees the team's contact details
// (BASE-F119): the owner sees them in Staff and gets them from the API; an employee gets the same list without an Email
// column (no column of dashes) at every width, and the API gives them the contact as null and refuses to filter by it.
import { expect, test } from '@playwright/test';

import { A, api, capture, EMPLOYEE, shown } from './helpers';
import { signedIn } from './flow-helpers';
import { staffCleanUp } from './staff-helpers';

const TAG = 'E2E Contact';
const VIEWPORTS = [
  { width: 1440, height: 900 },
  { width: 820, height: 1180 },
  { width: 375, height: 667 },
];

type Row = { full_name: string; email: string | null; phone: string | null };
type Page = { rows: Row[] };
type Envelope = { error?: { code: string } };

const cleanup = (): void => staffCleanUp(TAG);

test.beforeAll(cleanup);
test.afterAll(cleanup);

for (const viewport of VIEWPORTS) {
  test(`an employee sees the team without its email or phone at ${viewport.width}px; the owner with them`, async ({ browser }) => {
    const owner = await signedIn(browser, '/staff/members', viewport);
    const employee = await signedIn(browser, '/staff/members', viewport, EMPLOYEE);
    try {
      const last = `Mail${viewport.width}`;
      const email = `rita.${viewport.width}@team.example`;
      const created = await api(owner.context, A, 'POST', '/staff/members', { first_name: TAG, last_name: last, email, phone: '+34 600 111 222' });
      expect(created.status).toBe(201);
      const query = `/staff/members?search=${encodeURIComponent(last)}`;

      const ownerRows = (await api<Page>(owner.context, A, 'GET', query)).data.rows;
      expect(ownerRows.map((row) => [row.email, row.phone])).toEqual([[email, '+34 600 111 222']]);
      await owner.page.reload();
      const ownerView = shown(owner.page);
      await expect(ownerView.locator('[data-testid=staff-members-row]', { hasText: last }).first()).toBeVisible();
      if (viewport.width >= 1440) await expect(ownerView.getByText(email).first()).toBeVisible();
      await capture(owner.page, `staff-team-contact-owner-${viewport.width}`);

      const employeeRows = (await api<Page>(employee.context, A, 'GET', query)).data.rows;
      expect(employeeRows.map((row) => [row.full_name, row.email, row.phone])).toEqual([[`${TAG} ${last}`, null, null]]);
      const refused = await api<Envelope>(employee.context, A, 'GET', `/staff/members?email=${encodeURIComponent('team.example')}`);
      expect([refused.status, refused.data.error?.code]).toEqual([403, 'permission_denied']);

      await employee.page.reload();
      const view = shown(employee.page);
      await expect(view.locator('[data-testid=staff-members-row]', { hasText: last }).first()).toBeVisible();
      await expect(view.locator('[role=columnheader]', { hasText: 'Email' })).toHaveCount(0);
      await expect(view.getByText('@team.example')).toHaveCount(0);
      await expect(view.getByText('600 111 222')).toHaveCount(0);
      await capture(employee.page, `staff-team-contact-employee-${viewport.width}`);
    } finally {
      await owner.context.close();
      await employee.context.close();
    }
  });
}
