// Staff's navigation in Chrome, as Ioan sees it (Spanish): the «Personal» tile of the «My apps» sheet, the footer tabbar with its four
// sections (Personal, Roles, Ausencias, Horarios) plus «Comisiones» and «Ajustes» for
// the owner, each tab replacing the address; Ajustes saves only what changed. Every page is captured in
// the three viewports (desktop 1280×860, tablet 834×1112, phone 390×844) for the comparison with the
// old module's screens; the page never scrolls sideways.
import { type Browser, expect, test } from '@playwright/test';

import { A, api, horizontalOverflow, login, openApps, psql, shot, shown, topbarApps } from './helpers';

const TAG = 'E2E';
const VIEWPORTS = {
  desktop: { width: 1280, height: 860 },
  tablet: { width: 834, height: 1112 },
  phone: { width: 390, height: 844 },
} as const;
const PAGES = [
  ['members', '/staff/members', 'Personal'],
  ['roles', '/staff/roles', 'Roles'],
  ['time-off', '/staff/time-off', 'Ausencias'],
  ['schedules', '/staff/schedules', 'Horarios'],
  ['commissions', '/staff/commissions', 'Comisiones'],
  ['settings', '/staff/settings', 'Ajustes'],
] as const;

function cleanup(): void {
  const members = `select id from staff_member where first_name like '${TAG}%'`;
  psql(
    [
      `delete from staff_timeoff where member_id in (${members})`,
      `delete from staff_scheduleday where schedule_id in (select id from staff_schedule where member_id in (${members}))`,
      `delete from staff_schedule where member_id in (${members})`,
      `delete from staff_member where first_name like '${TAG}%'`,
      `delete from staff_role where name like '${TAG}%'`,
    ].join('; '),
  );
}

test.beforeAll(cleanup);
test.afterAll(cleanup);

/** The owner on `a`, in Spanish: the Hub's language cookie (the one the sign-in sets from the account). */
async function ownerPage(browser: Browser, next: string, viewport: { width: number; height: number }) {
  const context = await browser.newContext({ baseURL: A, viewport, locale: 'es-ES' });
  const page = await context.newPage();
  await login(page, A, next);
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  await page.goto(`${A}${next}`);
  await topbarApps(page).waitFor({ state: 'visible' });
  return { context, page };
}

test('the «My apps» sheet leads to Personal, the tabbar to every section, and Ajustes saves only what changed', async ({ browser }) => {
  const { context, page } = await ownerPage(browser, '/staff/members', VIEWPORTS.desktop);
  try {
    // A sample record, so every list has something to paint.
    expect((await api(context, A, 'POST', '/staff/members', { first_name: `${TAG} Lola`, last_name: 'Muestra' })).status).toBe(201);
    // No app in the hub's side menu (PLAN-MIGRATIONS §16): the app is a tile of the sheet, its sections are the tabbar.
    await expect(page.locator('ion-menu.dash-menu [data-testid=nav-home]')).toBeVisible();
    await expect(page.locator('ion-menu.dash-menu ion-item.nav-item', { hasText: 'Personal' })).toHaveCount(0);
    const sheet = await openApps(page);
    await expect(sheet.locator('[data-testid=apps-launcher-app]', { hasText: 'Personal' })).toBeVisible();
    await sheet.locator('[data-testid=apps-launcher-close]').click();
    await expect(page.locator('ion-modal[data-testid=apps-launcher]:not(.overlay-hidden)')).toHaveCount(0);

    const tabs = shown(page).locator('ion-footer ion-segment-button');
    await expect(tabs).toHaveText(PAGES.map(([, , label]) => new RegExp(label)));
    for (const [, path, label] of PAGES.slice(1)) {
      await shown(page).locator('ion-footer ion-segment-button', { hasText: label }).click();
      await page.waitForURL(`${A}${path}`);
    }

    // Ajustes (STAFF-F22): the proposed values; «Guardar» only when something changed.
    const save = shown(page).locator('[data-testid=staff-settings-save]');
    await expect(save).toHaveAttribute('disabled', /.*/);
    const before = await api<{ default_break_duration: number }>(context, A, 'GET', '/staff/settings');
    const next = before.data.default_break_duration === 45 ? '30' : '45';
    try {
      await shown(page).locator('[data-testid=staff-settings-default_break_duration] input').fill(next);
      await save.click();
      await expect(shown(page).locator('[data-testid=staff-settings-saved]')).toContainText('Ajustes guardados');
      expect((await api<{ default_break_duration: number }>(context, A, 'GET', '/staff/settings')).data.default_break_duration).toBe(Number(next));
    } finally {
      // Back as it was, whatever happened above.
      expect((await api(context, A, 'POST', '/staff/settings', { default_break_duration: before.data.default_break_duration })).status).toBe(200);
    }
  } finally {
    await context.close();
  }
});

for (const [size, viewport] of Object.entries(VIEWPORTS)) {
  test(`every staff page in the ${size} (${viewport.width}×${viewport.height}), without sideways scroll`, async ({ browser }) => {
    const { context, page } = await ownerPage(browser, '/staff/members', viewport);
    try {
      expect((await api(context, A, 'POST', '/staff/members', { first_name: `${TAG} Lola`, last_name: `Muestra ${size}` })).status).toBe(201);
      for (const [name, path] of PAGES) {
        await page.goto(`${A}${path}`);
        const view = shown(page);
        await view.locator('ion-footer ion-segment').waitFor({ state: 'visible' });
        await expect
          .poll(async () => view.locator('[data-testid$=-loading], [data-testid$=-loading-members]').count(), { message: `${name} loaded` })
          .toBe(0);
        const overflow = await horizontalOverflow(page);
        expect(overflow, `${name} scrolls sideways`).toBeLessThanOrEqual(0);
        await page.screenshot({ path: shot(`staff-${name}-${size}`) });
      }
    } finally {
      await context.close();
    }
  });
}
