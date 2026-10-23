// FIX-UI-COMBO-ENTER-WHILE-SEARCHING-SUBMITS — a Combo (ui:Combo) in Chrome, on Staff › Staff › a member's
// sheet, field «Role» (it searches the server): the owner types a role and presses Enter before the server
// answers. Enter stays in the field: the sheet stays open, nothing is saved and the record keeps its role.
// When the answer comes it is shown with its first role highlighted, but nothing is chosen behind the owner's
// back; a second Enter takes it and Save keeps it. At a phone, a tablet and a desk. Everything this spec
// creates is named «CMB …» and removed after it (and before, if a run died half-way).
// flow: ui:Combo
import { type Browser, expect, type Route, test } from '@playwright/test';

import { A, api, login, psql, shot, shown } from './helpers';

const TAG = 'CMB';
const VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
];

/** Removes every record this spec creates (first names «CMB…», roles «CMB…»). */
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

/** The owner signed in on `a`, in English, at the given size. */
async function ownerPage(browser: Browser, viewport: { width: number; height: number }) {
  const context = await browser.newContext({ baseURL: A, viewport, locale: 'en-US' });
  const page = await context.newPage();
  await login(page, A, '/staff/members');
  // The owner's session for the fleet's visual sweep of Staff (`ui-clip-sweep.sh --storage-state`), when asked.
  if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  return { context, page };
}

type Role = { id: string; name: string };

for (const vp of VIEWPORTS) {
  test(`ui:Combo — Enter on «Role» while its search loads keeps the sheet open and saves nothing (${vp.label})`, async ({ browser }) => {
    const stamp = `${vp.label}x${Date.now().toString(36)}`;
    const { context, page } = await ownerPage(browser, { width: vp.width, height: vp.height });
    try {
      const role = async (name: string): Promise<Role> => {
        const res = await api<Role>(context, A, 'POST', '/staff/roles', { name });
        expect(res.status, JSON.stringify(res.data)).toBe(201);
        return res.data;
      };
      const manager = await role(`${TAG} Manager ${stamp}`);
      const stylist = await role(`${TAG} Stylist ${stamp}`);
      const fullName = `${TAG} Dana ${stamp}`;
      const created = await api<{ id: string }>(context, A, 'POST', '/staff/members', {
        first_name: `${TAG} Dana`,
        last_name: stamp,
        role_id: manager.id,
      });
      expect(created.status, JSON.stringify(created.data)).toBe(201);
      const roleOf = (): string => psql(`select coalesce(role_id::text, '') from staff_member where id = '${created.data.id}'`);
      expect(roleOf()).toBe(manager.id);

      // The role search for what the owner types is held until the test lets it go; any other passes.
      const typed = `Stylist ${stamp}`;
      const held: Route[] = [];
      await page.route(
        (url) => url.pathname === '/api/staff/roles',
        (route) => {
          if (new URL(route.request().url()).searchParams.get('search') === typed) held.push(route);
          else void route.continue();
        },
      );
      const saves: string[] = [];
      page.on('request', (request) => {
        if (request.method() === 'POST' && new URL(request.url()).pathname.startsWith('/api/staff/members')) saves.push(request.url());
      });

      await page.goto(`${A}/staff/members`);
      const row = shown(page).locator('[data-testid=staff-members-row]', { hasText: fullName });
      await row.getByText(fullName).click();
      const sheet = page.locator('ion-modal[data-testid=staff-member-form]');
      await expect(sheet.locator('ion-title')).toHaveText(`Edit · ${fullName}`);
      const field = page.locator('[data-testid=staff-member-form-role_id] input');
      await expect(field).toHaveValue(manager.name);

      // Typed, asked, the answer not back yet: Enter.
      await field.click();
      await field.fill(typed);
      await expect.poll(() => held.length).toBe(1);
      await expect(page.locator('[data-testid=staff-member-form-role_id-loading]')).toBeVisible();
      await field.press('Enter');
      // A submit leaves at once on Enter: give it time to show before saying none left.
      await page.waitForTimeout(500);
      await expect(sheet).toBeVisible();
      await expect(field).toHaveValue(typed);
      expect(saves).toEqual([]);
      expect(roleOf()).toBe(manager.id);
      await page.screenshot({ path: shot(`FIX-UI-COMBO-ENTER-WHILE-SEARCHING-SUBMITS-${vp.label}`) });

      // The answer comes: shown, its first role highlighted, nothing chosen behind the owner's back.
      for (const route of held.splice(0)) await route.continue();
      const option = page.locator(`[data-testid=staff-member-form-role_id-option-${stylist.id}]`);
      await expect(option).toBeVisible();
      await expect(option).toHaveAttribute('aria-selected', 'true');
      await expect(field).toHaveValue(typed);
      expect(saves).toEqual([]);

      // Enter on what the owner now sees takes it, and still not the form; Save keeps it.
      await field.press('Enter');
      await expect(field).toHaveValue(stylist.name);
      await expect(option).toBeHidden();
      await expect(sheet).toBeVisible();
      expect(saves).toEqual([]);
      await page.locator('[data-testid=staff-member-form-submit]').click();
      await expect(sheet).toBeHidden();
      await expect.poll(roleOf).toBe(stylist.id);
      expect(saves).toHaveLength(1);
    } finally {
      await context.close();
    }
  });
}
