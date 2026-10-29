// flow: STAFF-G01
// Staff's «Empleados por rol» on the Home with each role's own colour (FIX-HUB-STAFF-ROLE-BARS-IGNORE-ROLE-COLOR; the
// old module's `map.color`, the old hub's `renderBarList`, docs/reference/old-hub/dashboard-*.png): the owner of hub
// `a`, in Spanish, adds the panel from «Personalizar panel»; two roles of colours of their own and a third without one,
// each with Active people: each bar's fill is its role's colour, and the role without one keeps the panel's. base paints
// a row's colour only when the panel maps it (FIX-HUB-BASE-HOME-BAR-LIST-IGNORES-MAP-COLOR, `bars()` of
// base/frontend/lib/home.ts), so this checks Staff declares it. Captures `FIX-HUB-STAFF-ROLE-BARS-IGNORE-ROLE-COLOR-<width>`.
// Everything this file creates is named «E2E-ROLECOLOR …» and removed after it.
import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, api, horizontalOverflow, login, psql, shot, shown, untilStill } from './helpers';
import { VIEWPORTS } from './inventory-helpers';
import { stamp } from './sale-helpers';

const KEY = 'FIX-HUB-STAFF-ROLE-BARS-IGNORE-ROLE-COLOR';
const BY_ROLE = 'staff.by_role';
const TAG = 'E2E-ROLECOLOR';
const RUN = stamp();
/** Two roles of colours of their own and one without; each with a different number of Active people. */
const ROLES = [
  { name: `${TAG} ${RUN} Colorista`, color: '#16a34a', people: 3 },
  { name: `${TAG} ${RUN} Estilista`, color: '#e11d48', people: 2 },
  { name: `${TAG} ${RUN} Recepción`, color: '', people: 1 },
];

interface RoleRow {
  name: string;
  member_count: number;
  color: string;
}

test.describe.configure({ mode: 'serial' });

function cleanup(): void {
  psql(
    [`delete from staff_member where first_name like '${TAG}%'`, `delete from staff_role where name like '${TAG}%'`].join('; '),
  );
}

async function created(context: BrowserContext, path: string, body: Record<string, unknown>): Promise<string> {
  const res = await api<{ id: string }>(context, A, 'POST', path, body);
  expect(res.status, `${path} ${JSON.stringify(res.data)}`).toBe(201);
  return res.data.id;
}

test.beforeAll(async ({ browser }) => {
  cleanup();
  const context = await browser.newContext({ baseURL: A });
  try {
    const page = await context.newPage();
    await login(page, A, '/staff/members');
    for (const role of ROLES) {
      const roleId = await created(context, '/staff/roles', role.color ? { name: role.name, color: role.color } : { name: role.name });
      for (let person = 0; person < role.people; person += 1) {
        await created(context, '/staff/members', { first_name: `${TAG} ${person}`, last_name: RUN, role_id: roleId });
      }
    }
  } finally {
    await context.close();
  }
});

test.afterAll(cleanup);

/** The panel's rows as the server gives them (its `params`): ours among the ten, each with its colour, "" without one. */
async function byRole(context: BrowserContext): Promise<RoleRow[]> {
  const res = await api<{ rows: RoleRow[] }>(context, A, 'GET', '/staff/roles?sort=-member_count&limit=10');
  expect(res.status).toBe(200);
  return res.data.rows;
}

/** Each of our bars' fill and what it should be: its role's colour, or the panel's for a role without one. */
async function fills(page: Page): Promise<{ name: string; fill: string; wanted: string }[]> {
  const panel = shown(page).locator(`[data-testid="widget-board"] [data-testid="widget"][data-key="${BY_ROLE}"]`);
  return panel.evaluate(
    (element, roles) => {
      const probe = (background: string) => {
        const span = document.createElement('span');
        span.style.background = background;
        element.append(span);
        const found = getComputedStyle(span).backgroundColor;
        span.remove();
        return found;
      };
      const rows = [...element.querySelectorAll('[data-testid="widget-bar"]')];
      return roles.map(({ name, color }) => {
        const row = rows.find((candidate) => candidate.querySelector('.widget-bar-label')?.textContent === name);
        const fill = row?.querySelector('.widget-bar-fill');
        return {
          name,
          fill: fill ? getComputedStyle(fill).backgroundColor : 'no bar',
          wanted: probe(color || 'var(--ion-color-primary)'),
        };
      });
    },
    ROLES.map(({ name, color }) => ({ name, color })),
  );
}

for (const viewport of VIEWPORTS) {
  test(`STAFF-G01: «Empleados por rol» paints each bar in its role's colour, and the panel's without one, at ${viewport.label}`, async ({ browser }) => {
    const context = await browser.newContext({ baseURL: A, viewport, locale: 'es-ES' });
    try {
      const page = await context.newPage();
      await login(page, A, '/');
      await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
      await page.goto(`${A}/`);
      await expect(page.locator('html')).toHaveAttribute('lang', /^es/);

      // The server gives each row its role's colour ("" for none), and ours are among the panel's ten.
      const rows = await byRole(context);
      for (const role of ROLES) {
        expect(
          rows.find((row) => row.name === role.name),
          role.name,
        ).toMatchObject({ member_count: role.people, color: role.color });
      }

      await shown(page).locator('[data-testid="widgets-customize"]').click();
      const picker = page.locator('ion-modal[data-testid="widgets-picker"]:not(.overlay-hidden)');
      await expect(picker).toContainText('Personal');
      await picker.locator(`[data-testid="widgets-add-${BY_ROLE}"]`).click();
      await picker.locator('[data-testid="widgets-close"]').click();
      await expect(picker).toHaveCount(0);

      const panel = shown(page).locator(`[data-testid="widget-board"] [data-testid="widget"][data-key="${BY_ROLE}"]`);
      await expect(panel.locator('[data-testid="widget-title"]')).toHaveText('Empleados por rol');
      await expect(panel).toHaveAttribute('aria-busy', 'false');
      await expect(panel.locator('[data-testid="widget-error"]')).toHaveCount(0);
      const bar = (name: string) =>
        panel.locator('[data-testid="widget-bar"]').filter({ has: page.locator('.widget-bar-label').getByText(name, { exact: true }) });
      for (const role of ROLES) await expect(bar(role.name).locator('.widget-bar-text')).toHaveText(String(role.people));

      for (const { name, fill, wanted } of await fills(page)) expect(fill, name).toBe(wanted);
      // The two colours of their own are not the panel's: a bar in the panel's colour would not pass for its role's.
      const [colourist, stylist, reception] = await fills(page);
      expect(new Set([colourist.fill, stylist.fill, reception.fill]).size).toBe(3);
      // The owner's Spanish session with the panel on, for the fleet's visual sweep (`ui-clip-sweep.sh --storage-state`).
      if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });

      await panel.evaluate((element) => element.scrollIntoView({ block: 'center' }));
      await untilStill(page);
      const overflow = await horizontalOverflow(page);
      expect(overflow, `no sideways scroll at ${viewport.label}`).toBeLessThanOrEqual(0);
      await page.screenshot({ path: shot(`${KEY}-${viewport.label}`) });
    } finally {
      await context.close();
    }
  });
}
