// flow: CUSTOMER-F02, CUSTOMER-F03 — the customers' email and phone reach only whoever sees the customers' contact
// details (BASE-F119). The employee holds that permission (base/apps.py), so they still see the list with «Email» and
// «Phone» and the card with both, at every width; nobody sorts the list by them any more (the API answers 422), and a
// filter by them is the employee's to use. A role without the permission does not exist yet in a browser: what it
// gets is held by the server's tests (apps/customer/tests/test_customer_contact.py) and the pages' (Vitest).
import { expect, test } from '@playwright/test';

import { cleanUp, createCard, customersReady, e2eName, FLOW_VIEWPORTS, rowNamed, searchList, spanishMobile } from './customer-helpers';
import { signedIn } from './flow-helpers';
import { A, api, capture, EMPLOYEE, shown } from './helpers';

type Row = { name: string; email: string | null; phone: string | null };
type Page = { rows: Row[]; total: number };

test.afterAll(() => cleanUp());

for (const viewport of FLOW_VIEWPORTS) {
  test(`the employee sees a customer's email and phone at ${viewport.label}px; nobody sorts by them`, async ({ browser }) => {
    const { context, page } = await signedIn(browser, '/customer/customers', viewport, EMPLOYEE);
    try {
      const name = e2eName(`Contact ${viewport.label}`);
      const email = `contact.${viewport.label}.${Date.now().toString(36)}@example.com`;
      const card = await createCard(context, { name, email, phone: spanishMobile() });

      const query = `/customer/customers?search=${encodeURIComponent(name)}`;
      expect((await api<Page>(context, A, 'GET', query)).data.rows.map((row) => [row.name, row.email])).toEqual([[name, email]]);
      const byEmail = await api<Page>(context, A, 'GET', `/customer/customers?email=${encodeURIComponent(email)}`);
      expect([byEmail.status, byEmail.data.total]).toEqual([200, 1]);
      expect((await api(context, A, 'GET', '/customer/customers?sort=email')).status).toBe(422);

      await customersReady(page);
      await searchList(page, 'customer-list', name);
      const row = rowNamed(page, 'customer-list', name);
      await expect(row).toBeVisible();
      if (viewport.width >= 1440) {
        await expect(shown(page).locator('[role=columnheader]', { hasText: 'Email' })).toHaveCount(1);
        await expect(row.getByText(email)).toBeVisible();
      }
      await capture(page, `customer-contact-list-${viewport.label}`);

      await row.click();
      await page.waitForURL(new RegExp(`/customer/customers/${card.id}$`));
      const facts = shown(page).locator('[data-testid=customer-facts]');
      await expect(facts.locator('[data-fact=email] dd')).toHaveText(email);
      await expect(facts.locator('[data-fact=phone]')).toHaveCount(1);
      await capture(page, `customer-contact-card-${viewport.label}`);
    } finally {
      await context.close();
    }
  });
}
