// Employees and the API's documentation (APP-BASE-5; the old hub's EmployeesPage, docs/reference/old-hub/employees-*.png
// and settings-permissions-*.png) in the three viewports, as the owner of hub `a`: «Staff» with the plan's places and how
// each person gets in, «Roles», «API keys» (hub `a` still shares phase 1's database: «Not available yet», and the way to
// the documentation) and «Approvals» (nobody approved anything yet); a person's page, giving and taking away a badge
// (one per run: phase 1 keeps every hub's badges in one table); the API's documentation, hidden, shown from Settings ›
// General and read; and the employee, who has no «API keys» nor «Approvals» and whose `#apikeys` opens «Staff». Each
// flow leaves its capture `APP-BASE-5-<G key>-<width>` once nothing scrolls sideways.
//
// «An approval is needed» (BASE-G136) has no screen of its own: it opens over an app's when the app asks for it, and no
// app does yet; its dialog is ApprovalDialog.test.ts's and the server's base/tests/test_approvals.py's.
// flow: BASE-G138 BASE-G139 BASE-G140 BASE-G142 BASE-G143 BASE-G144 BASE-G145 BASE-G146 BASE-G149 BASE-G150 BASE-G100
// BASE-G10 BASE-G11 BASE-G02 BASE-G04 BASE-G05 BASE-F85
import { readFileSync } from 'node:fs';

import { type Browser, expect, type Page, test } from '@playwright/test';

import { A, collectProblems, EMPLOYEE, hostPage, psql, shot, shown, untilStill } from './helpers';

const VIEWPORTS = {
  390: { width: 390, height: 844 },
  834: { width: 834, height: 1112 },
  1440: { width: 1440, height: 900 },
} as const;

/** A card's number, one per run: a badge opens one person's door only. */
const BADGE = `55${String(Date.now()).slice(-8)}`;

function hideTheDocs(): void {
  psql('delete from base_apisettings');
}

test.beforeAll(hideTheDocs);
test.afterAll(hideTheDocs);
test.describe.configure({ mode: 'serial' });

/** The capture of a flow, once the screen settled. */
async function snap(page: Page, key: string, width: number): Promise<void> {
  await page.mouse.move(0, 0);
  await expect(shown(page).locator('[data-testid$="-loading"]:visible')).toHaveCount(0);
  await untilStill(page);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow, `${key} at ${width}: no sideways scroll`).toBeLessThanOrEqual(0);
  await page.screenshot({ path: shot(`APP-BASE-5-${key}-${width}`) });
}

const testid = (page: Page, id: string) => shown(page).locator(`[data-testid="${id}"]`);

async function signedIn(browser: Browser, viewport: { width: number; height: number }, next: string, employee = false) {
  return hostPage(browser, A, { viewport, next, credentials: employee ? EMPLOYEE : undefined });
}

/** No console error nor uncaught error on the page. */
async function noProblems(problems: Awaited<ReturnType<typeof collectProblems>>): Promise<void> {
  const seen = await problems();
  expect(seen.console).toEqual([]);
  expect(seen.page).toEqual([]);
}

/** The side menu's entries, in order (`nav-<id>`), painted or folded away. */
async function menuIds(page: Page): Promise<string[]> {
  return page.locator('ion-menu.dash-menu ion-item.nav-item').evaluateAll((items) => items.map((item) => item.getAttribute('data-testid') ?? ''));
}

/** The side menu captured: pinned on a desktop; on a phone or a tablet, opened from the bar and closed again. */
async function snapMenu(page: Page, key: string, width: number): Promise<void> {
  const pinned = width >= 992;
  if (!pinned) {
    await shown(page).locator('ion-menu-button').click();
    await expect(page.locator('ion-menu.dash-menu')).toHaveClass(/show-menu/);
  }
  await snap(page, key, width);
  if (!pinned) {
    await page.locator('ion-menu.dash-menu').evaluate((menu) => (menu as HTMLElement & { close(): Promise<boolean> }).close());
    await expect(page.locator('ion-menu.dash-menu')).not.toHaveClass(/show-menu/);
  }
}

/** The owner's menu with the API documentation hidden: every platform entry with a screen, «API» not. */
const OWNER_MENU = ['nav-home', 'nav-employees', 'nav-files', 'nav-apps', 'nav-system', 'nav-settings'];

/** Opens a tab of the footer tabbar (`tab-<id>`). */
async function tab(page: Page, id: string): Promise<void> {
  await testid(page, `tab-${id}`).click();
  await expect(testid(page, `tab-${id}`)).toHaveClass(/segment-button-checked/);
}

for (const [label, viewport] of Object.entries(VIEWPORTS)) {
  const width = Number(label);

  test(`BASE-G11 BASE-G138 BASE-G142 BASE-G143 BASE-G144 — Employees, its people and its roles at ${width}`, async ({ browser }) => {
    const { context, page } = await signedIn(browser, viewport, '/employees');
    const problems = await collectProblems(page);
    await expect(page.getByRole('heading', { name: 'Employees' }).first()).toBeVisible();
    // «Staff»: the plan's places, invitations on erplora.com, and how each person gets in.
    await expect(testid(page, 'people-seats')).toBeVisible();
    await expect(testid(page, 'people-invite')).toHaveAttribute('href', /\/members$/);
    const people = shown(page).locator('[data-testid="people-row"], [data-testid="people-card"]');
    await expect(people.first()).toBeVisible();
    await expect(shown(page).getByText('Account').first()).toBeVisible();
    await snap(page, 'BASE-G142', width);
    // The side menu: whoever runs the business sees every entry with a screen; «API» only with the docs shown.
    await expect.poll(() => menuIds(page)).toEqual(OWNER_MENU);
    await snapMenu(page, 'FIX-SIDEBAR-owner', width);
    // «Roles»: the four of erplora.com.
    await tab(page, 'roles');
    await expect(page).toHaveURL(/\/employees#roles$/);
    await expect(shown(page).locator('[data-testid="roles-row"], [data-testid="roles-card"]')).toHaveCount(4);
    await expect(testid(page, 'roles-change')).toHaveAttribute('href', /\/members$/);
    await snap(page, 'BASE-G143', width);
    await noProblems(problems);
    if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
    await context.close();
  });

  test(`BASE-G146 BASE-G149 BASE-G145 — API keys and Approvals at ${width}`, async ({ browser }) => {
    const { context, page } = await signedIn(browser, viewport, '/employees#apikeys');
    const problems = await collectProblems(page);
    // Hub `a` shares phase 1's database: no key yet, and the way to the documentation.
    await expect(testid(page, 'api-keys-unavailable')).toContainText('API keys are not available yet in this business.');
    await expect(testid(page, 'api-keys-docs')).toHaveAttribute('href', '/api-docs');
    await snap(page, 'BASE-G146', width);
    await tab(page, 'approvals');
    await expect(page).toHaveURL(/\/employees#approvals$/);
    await expect(shown(page).getByText('Each action that needed a manager')).toBeVisible();
    await expect(shown(page).getByText('Nobody has had to approve anything in this business yet.')).toBeVisible();
    // BASE-F85: the record filters by day, action, how and whether it was used, behind its funnel (as the old hub's).
    await expect(shown(page).locator('[data-testid=approvals-filters-toggle]')).toBeVisible();
    // BASE-F85: «Export CSV» downloads what the search and the filters keep, in the person's language: here, nobody has
    // approved anything yet, its header alone.
    const [download] = await Promise.all([
      page.waitForEvent('download'),
      shown(page).locator('[data-testid=approvals-export]').click(),
    ]);
    expect(download.suggestedFilename()).toBe('approvals.csv');
    expect(readFileSync(await download.path(), 'utf8')).toBe('\ufeffWhen,Action,Approved by,Asked by,With,State\r\n');
    await snap(page, 'BASE-G145', width);
    await noProblems(problems);
    await context.close();
  });

  test(`BASE-G100 BASE-G150 — the API's documentation, hidden, shown and read at ${width}`, async ({ browser }) => {
    hideTheDocs();
    const { context, page } = await signedIn(browser, viewport, '/api-docs');
    const problems = await collectProblems(page);
    await expect(testid(page, 'api-docs-hidden')).toContainText('The API documentation is hidden in this business.');
    await testid(page, 'api-docs-show').click();
    await expect(page).toHaveURL(/\/settings/);
    const card = testid(page, 'api-docs-card');
    await card.scrollIntoViewIfNeeded();
    // «API» in the side menu comes and goes with the switch, live (the old hub's, between System and Settings).
    const apiEntry = page.locator('ion-menu.dash-menu [data-testid="nav-api"]');
    await expect(apiEntry).toHaveCount(0);
    await testid(page, 'api-docs-toggle').click();
    await expect(testid(page, 'api-docs-open')).toBeVisible();
    await expect(apiEntry).toHaveCount(1);
    expect(await menuIds(page)).toEqual([...OWNER_MENU.slice(0, -1), 'nav-api', 'nav-settings']);
    await snapMenu(page, 'BASE-G100-menu-api', width);
    await testid(page, 'api-docs-toggle').click();
    await expect(testid(page, 'api-docs-open')).toHaveCount(0);
    await expect(apiEntry).toHaveCount(0);
    await testid(page, 'api-docs-toggle').click();
    await expect(apiEntry).toHaveCount(1);
    await snap(page, 'BASE-G100', width);
    await testid(page, 'api-docs-open').click();
    await expect(page).toHaveURL(/\/api-docs$/);
    await expect(shown(page).locator('[data-testid="api-docs-section"]').first()).toBeVisible();
    await expect(testid(page, 'api-docs-keys-soon')).toBeVisible();
    const route = shown(page).locator('[data-testid="api-docs-route"]').first();
    await route.locator('summary').click();
    await expect(route).toHaveAttribute('open', '');
    await snap(page, 'BASE-G150', width);
    await noProblems(problems);
    await context.close();
  });

  test(`BASE-G11 — the employee has no API keys nor Approvals at ${width}`, async ({ browser }) => {
    // The documentation hidden, whatever the test before left: then «API» is not in the employee's menu either.
    hideTheDocs();
    const { context, page } = await signedIn(browser, viewport, '/employees#apikeys', true);
    const problems = await collectProblems(page);
    await expect(shown(page).locator('[data-testid="people-row"], [data-testid="people-card"]').first()).toBeVisible();
    await expect(shown(page).locator('ion-segment-button[data-testid^="tab-"]')).toHaveCount(2);
    await expect(testid(page, 'tab-personal')).toHaveClass(/segment-button-checked/);
    await expect(testid(page, 'tab-apikeys')).toHaveCount(0);
    await expect(testid(page, 'tab-approvals')).toHaveCount(0);
    await snap(page, 'BASE-G11-employee', width);
    // FIX-UI-SIDEBAR-SYSTEM-VISIBLE-TO-EMPLOYEE: the menu never offers what the employee cannot open (System is for
    // whoever runs the business; Square and Toast hide it the same).
    await expect.poll(() => menuIds(page)).toEqual(['nav-home', 'nav-employees', 'nav-files', 'nav-apps', 'nav-settings']);
    await snapMenu(page, 'FIX-SIDEBAR-employee', width);
    await noProblems(problems);
    await context.close();
  });
}

// A person's page with a badge and without it (BASE-G10, G139, G140): one badge per run, given and taken away once on the
// phone (where its form is tightest), and the page seen with it and without it at the three sizes, its field and buttons
// usable at each one (a trial click: Playwright's checks of a real one, nothing sent). Every badge given
// counts against who gives it, the accepted ones too (`BADGE_CHANGE_LIMIT`, 30 an hour, gh:hub#2560), as a PIN chosen
// does: the approvals' specs choose theirs once per run, in `beforeAll`. A badge per size spent three per run, and the
// eleventh run within the hour fell with «Too many badges tried» (rv-332).
/** The badge's field takes a number and `buttons` take a click at this size, without spending a badge: a trial click runs
 *  every check of a real one (shown, still, enabled, nothing over it) and sends nothing. */
async function badgeFormUsable(page: Page, ...buttons: string[]): Promise<void> {
  const field = testid(page, 'person-badge-input').locator('input');
  await expect(field).toBeEditable();
  await field.click({ trial: true, timeout: 5_000 });
  for (const id of buttons) await testid(page, id).click({ trial: true, timeout: 5_000 });
}

test("BASE-G10 BASE-G139 BASE-G140 — a person's page, a badge given and taken away once, seen at 390, 834 and 1440", async ({
  browser,
}) => {
  // The employee enters once, so the business has them (a fresh e2e database has only who entered).
  const visit = await signedIn(browser, VIEWPORTS[390], '/', true);
  await visit.context.close();
  const { context, page } = await signedIn(browser, VIEWPORTS[390], '/employees');
  const problems = await collectProblems(page);
  const employee = shown(page).locator('[data-testid="people-row"], [data-testid="people-card"]').filter({ hasText: 'Employee' });
  await employee.first().click();
  await expect(page).toHaveURL(/\/employees\/[^/#]+$/);
  await expect(testid(page, 'person-pin')).toContainText('No PIN');
  await testid(page, 'person-badge-input').locator('input').fill(BADGE);
  await testid(page, 'person-badge-save').click();
  await expect(testid(page, 'person-badge')).toContainText('Has a badge since');
  for (const [label, viewport] of Object.entries(VIEWPORTS)) {
    await page.setViewportSize(viewport);
    await expect(testid(page, 'person-badge')).toContainText('Has a badge since');
    await badgeFormUsable(page, 'person-badge-save', 'person-badge-remove');
    await snap(page, 'BASE-G140', Number(label));
  }
  await page.setViewportSize(VIEWPORTS[390]);
  await testid(page, 'person-badge-remove').click();
  await expect(testid(page, 'person-badge')).toContainText('No badge.');
  for (const [label, viewport] of Object.entries(VIEWPORTS)) {
    await page.setViewportSize(viewport);
    await expect(testid(page, 'person-badge')).toContainText('No badge.');
    await badgeFormUsable(page, 'person-badge-save');
    await snap(page, 'BASE-G139', Number(label));
  }
  await noProblems(problems);
  await context.close();
});
