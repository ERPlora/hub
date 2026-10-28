// DEMO-F06 «Intentarlo sin permiso» (apps/demo/WORKBOOK.md): an employee (`hub_employee`, the SaaS's
// `employee@example.com` of `demo_seed`) sees Demo's list and detail, but none of what managing
// takes: no «New item», figures, «Edit», «Delete» nor «Add line»; reached by its address, a form says
// «You do not have permission»; the API refuses every management operation with 403
// `permission_denied` but a line, which asks for a manager's approval (403 `requires_elevation`, said
// with its figures: BASE-F84), and nothing changes. Without a session the API answers 401 `unauthorized`;
// with the permission taken away while the screen is open, the next refresh ends in «You do not have
// permission» and the item is no longer on screen.
// The owner's screens are the positive control: the same hooks are there for who may manage.
import { type BrowserContext, expect, test } from '@playwright/test';

import { A, EMPLOYEE, api, createItem, hostPage, itemDetail, listReady, psql, rowOf, shot, shown, uniqueName } from './helpers';

const OWNER_LINE = 'Owner line';
/** The Hub's local copy of the SaaS's employee (`saas:<id>`), never the staff one. */
const EMPLOYEE_USER = `(select id from auth_user where email = '${EMPLOYEE.email}' and username like 'saas:%')`;

type Envelope = { error?: { code: string; message: string; approval?: { operation: string; label: string } } };

async function addLine(context: BrowserContext, id: string, text: string): Promise<void> {
  const res = await api(context, A, 'POST', '/demo/items/add_line', { id, text, qty: 1 });
  expect(res.status, `add_line ${text}`).toBe(200);
}

test('DEMO-F06: an employee sees Demo but cannot manage it, by the screens or by the API', async ({ browser }) => {
  const owner = await hostPage(browser, A);
  const item = await createItem(owner.context, A, uniqueName('F06'));
  await addLine(owner.context, item.id, OWNER_LINE);
  const employee = await hostPage(browser, A, { credentials: EMPLOYEE });
  const { page } = employee;

  try {
    // Positive control: the owner's list and detail do show what the employee must not see.
    await listReady(owner.page);
    await expect(shown(owner.page).locator('[data-testid=demo-items-add]')).toBeVisible();
    await owner.page.goto(`${A}/demo/items/${item.id}`);
    await expect(shown(owner.page).locator('[data-testid=demo-detail-edit]')).toBeVisible();
    await expect(shown(owner.page).locator('[data-testid=demo-line-form]')).toBeVisible();

    // 1. The list: the item is there, without «New item» nor figures.
    await listReady(page);
    await expect(rowOf(page, item.id)).toBeVisible();
    await expect(shown(page).locator('[data-testid=demo-items-add]')).toHaveCount(0);
    await expect(shown(page).locator('[data-testid=demo-stats]')).toHaveCount(0);
    await page.screenshot({ path: shot('f06-employee-list') });

    // 1. The detail: status and lines, without «Edit», «Delete» nor «Add line»; the note is read-only.
    await rowOf(page, item.id).click();
    await page.waitForURL(new RegExp(`/demo/items/${item.id}$`));
    const detail = shown(page);
    await expect(detail.locator('[data-testid=demo-detail-status]')).toBeVisible();
    await expect(detail.locator('[data-testid=demo-line-text]')).toHaveText([OWNER_LINE]);
    for (const hook of ['demo-detail-edit', 'demo-detail-toggle', 'demo-detail-delete', 'demo-line-form', 'demo-note-save']) {
      await expect(detail.locator(`[data-testid=${hook}]`), hook).toHaveCount(0);
    }
    await expect(detail.locator('[data-testid=demo-note] textarea')).toHaveJSProperty('readOnly', true);
    await page.screenshot({ path: shot('f06-employee-detail') });

    // «Si llega por otra puerta»: the forms by their address say «You do not have permission».
    for (const path of ['/demo/items/new', `/demo/items/${item.id}/edit`]) {
      await page.goto(`${A}${path}`);
      const forbidden = shown(page).locator('[data-testid=demo-form-forbidden]');
      await expect(forbidden, path).toBeVisible();
      await expect(forbidden, path).toContainText(/You do not have permission|No tienes permiso/);
      await expect(shown(page).locator('[data-testid=demo-form]'), path).toHaveCount(0);
    }
    await page.screenshot({ path: shot('f06-employee-new-forbidden') });

    // 2. By the API: every management operation is refused with 403 `permission_denied`.
    const attempts: ReadonlyArray<readonly ['GET' | 'POST', string, unknown?]> = [
      ['GET', '/demo/items/stats'],
      ['POST', '/demo/items', { name: 'Created by the employee' }],
      ['POST', '/demo/items/update', { id: item.id, name: 'Changed by the employee' }],
      ['POST', '/demo/items/delete', { id: item.id }],
    ];
    for (const [method, path, body] of attempts) {
      const res = await api<Envelope>(employee.context, A, method, path, body);
      expect(res.status, `${method} ${path}`).toBe(403);
      expect(res.data.error?.code, `${method} ${path}`).toBe('permission_denied');
    }
    // A line is the one a manager may approve on the spot: the question, with what it approves and its figures.
    const line = await api<Envelope>(employee.context, A, 'POST', '/demo/items/add_line', { id: item.id, text: 'Employee line', qty: 1 });
    expect(line.status).toBe(403);
    expect(line.data.error?.code).toBe('requires_elevation');
    expect(line.data.error?.approval).toMatchObject({ operation: 'demo.item.add_line', label: 'Add a line: 1 × Employee line' });
    // What the employee may do, it does: read.
    expect((await api(employee.context, A, 'GET', `/demo/items/detail?id=${item.id}`)).status).toBe(200);

    // «Sale: nada cambia».
    const after = await itemDetail(owner.context, A, item.id);
    expect(after.name).toBe(item.name);
    expect(after.lines.map((line) => line.text)).toEqual([OWNER_LINE]);

    // Without a session: 401 `unauthorized`.
    const anonymous = await browser.newContext();
    try {
      const res = await api<Envelope>(anonymous, A, 'GET', '/demo/items');
      expect(res.status).toBe(401);
      expect(res.data.error?.code).toBe('unauthorized');
    } finally {
      await anonymous.close();
    }

    // The permission is taken away with the detail open: the next refresh ends in the error.
    await page.goto(`${A}/demo/items/${item.id}`);
    await expect(shown(page).locator('[data-testid=demo-detail-status]')).toBeVisible();
    psql(`delete from base_membership where host = 'a' and user_id = ${EMPLOYEE_USER}`);
    try {
      await addLine(owner.context, item.id, 'Second owner line');
      const refused = shown(page).locator('[data-testid=demo-detail-error]');
      await expect(refused).toContainText('You do not have permission');
      // What it may no longer read is no longer on screen.
      for (const hook of ['demo-detail-status', 'demo-note', 'demo-line-text']) {
        await expect(shown(page).locator(`[data-testid=${hook}]`), hook).toHaveCount(0);
      }
      await page.screenshot({ path: shot('f06-employee-revoked') });
    } finally {
      // What the next sign-in would do: the SaaS still says employee of `a`.
      psql(
        `insert into base_membership (id, host, role, user_id) select gen_random_uuid(), 'a', 'hub_employee', ${EMPLOYEE_USER} on conflict do nothing`,
      );
    }
  } finally {
    await api(owner.context, A, 'POST', '/demo/items/delete', { id: item.id });
    await employee.context.close();
    await owner.context.close();
  }
});
