// PoC §8.7, second pass: the shell's CSP (nonce + strict-dynamic, Trusted Types, `connect-src` with
// `ipc:` and `http://ipc.localhost` for Tauri — CLAUDE.md) and ZERO violations while a person goes
// through every demo screen in one document: list (search, empty, cards, page-size popover), detail,
// edit with a 422, the delete alert, «New item» and back. Violations are caught three ways: the
// `securitypolicyviolation` event, the console («Content Security Policy», «Trusted Type») and the
// reports the browser would POST to `/csp-report/`.
import { expect, test } from '@playwright/test';

import { A, createItem, listReady, login, record, rowOf, shot, shown, uniqueName } from './helpers';

test('CSP header with nonce, strict-dynamic, Trusted Types and connect-src ipc:; zero violations on every demo screen', async ({ page, context }) => {
  const cspConsole: string[] = [];
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];
  const reports: string[] = [];
  page.on('console', (msg) => {
    if (/content security policy|trusted ?type|refused to/i.test(msg.text())) cspConsole.push(msg.text());
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });
  page.on('pageerror', (err) => pageErrors.push(String(err)));
  page.on('request', (req) => {
    if (req.url().includes('/csp-report/')) reports.push(req.postData() ?? '');
  });
  await page.addInitScript(() => {
    const w = window as unknown as { __csp: unknown[] };
    w.__csp = [];
    document.addEventListener('securitypolicyviolation', (e) =>
      w.__csp.push({ directive: e.violatedDirective, blocked: e.blockedURI, sample: e.sample, source: e.sourceFile }),
    );
  });

  await login(page, A);
  const item = await createItem(context, A, uniqueName('CSP walk'));
  const response = await page.goto('/demo/items');
  const header = response?.headers()['content-security-policy'] ?? '';
  const nonce = /'nonce-([A-Za-z0-9_+/=-]+)'/.exec(header)?.[1] ?? '';
  const scriptNonces = await page.evaluate(() => [...document.querySelectorAll('script')].map((s) => s.nonce || '(none)'));
  await listReady(page);
  const visited: string[] = ['list'];

  // List: search with no results, cards, the page-size popover.
  await shown(page).locator('[data-testid=demo-items-search] input').fill('zz-csp-nothing-zz');
  await expect(shown(page).locator('[data-testid=demo-items-empty]')).toBeVisible();
  await shown(page).locator('[data-testid=demo-items-search] input').fill('');
  await expect(rowOf(page, item.id)).toBeVisible();
  await shown(page).locator('[data-testid=demo-items-view-cards]').click();
  await expect(shown(page).locator('ion-card[data-testid=demo-items-row]').first()).toBeVisible();
  await shown(page).locator('[data-testid=demo-items-view-table]').click();
  await shown(page).locator('.data-table__page-size-select').click();
  await page.locator('ion-popover ion-radio').filter({ hasText: /^\s*25\s*$/ }).click();
  // The `ion-select` popover only: the shell's user menu keeps its own `ion-popover` in the DOM.
  await expect(page.locator('ion-popover.select-popover')).toBeHidden();
  visited.push('search+empty', 'cards', 'page-size popover');

  // Detail → edit (422) → back → delete alert (cancel) → list → «New item» → back.
  await rowOf(page, item.id).click();
  await expect(shown(page).locator('[data-testid=demo-detail-status]')).toBeVisible();
  await shown(page).locator('[data-testid=demo-detail-edit]').click();
  const nameInput = shown(page).locator('[data-testid=demo-form-name] input');
  await expect(nameInput).toHaveValue(item.name);
  await nameInput.fill('');
  await shown(page).locator('[data-testid=demo-form-save]').click();
  await expect(shown(page).locator('[data-testid=demo-form-name]')).toHaveClass(/ion-invalid/);
  await shown(page).locator('[data-testid=topbar-back]').click();
  await expect(page).toHaveURL(new RegExp(`/demo/items/${item.id}$`));
  await shown(page).locator('[data-testid=demo-detail-delete]').click();
  await expect(page.locator('ion-alert')).toBeVisible();
  await page.locator('ion-alert button', { hasText: 'Cancel' }).click();
  await expect(page.locator('ion-alert')).toBeHidden();
  await shown(page).locator('[data-testid=topbar-back]').click();
  await expect(page).toHaveURL(/\/demo\/items$/);
  await shown(page).locator('[data-testid=demo-items-add]').click();
  await expect(shown(page).locator('[data-testid=demo-form]')).toBeVisible();
  await page.screenshot({ path: shot('csp--create-page') });
  await shown(page).locator('[data-testid=topbar-back]').click();
  await expect(page).toHaveURL(/\/demo\/items$/);
  visited.push('detail', 'edit 422', 'delete alert', 'create');
  await page.waitForTimeout(1500); // late violations (lazy chunks, icons, styles)

  const violations = await page.evaluate(() => (window as unknown as { __csp?: unknown[] }).__csp ?? []);
  const navigations = await page.evaluate(() => performance.getEntriesByType('navigation').length);
  record('csp', { header, visited, oneDocument: navigations === 1, scriptNonces, violations, cspConsole, consoleErrors, pageErrors, reports });

  const connectSrc = /connect-src ([^;]*)/.exec(header)?.[1].split(/\s+/) ?? [];
  expect(header).toMatch(/script-src [^;]*'nonce-[A-Za-z0-9_+/=-]+'/);
  expect(header).toContain("'strict-dynamic'");
  expect(header).toMatch(/trusted-types default/);
  expect(connectSrc).toEqual(expect.arrayContaining(["'self'", 'ipc:', 'http://ipc.localhost']));
  expect(header).toContain("object-src 'none'");
  expect(scriptNonces.every((n) => n === nonce || n === '(none)')).toBe(true);
  expect(violations).toEqual([]);
  expect(cspConsole).toEqual([]);
  expect(reports).toEqual([]);
  expect(pageErrors).toEqual([]);
  expect(consoleErrors.filter((e) => !e.includes('422'))).toEqual([]);
});
