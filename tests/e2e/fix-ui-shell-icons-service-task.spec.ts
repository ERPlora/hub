// flow: HUB_SHELL icons
// Services, Tasks and Price Lists wear the icons of the old modules (FIX-UI-SHELL-ICONS-SERVICE-TASK), now that
// the shell registers them (@erplora/ui `ION_ICONS`): an icon the shell does not know paints an empty box, so
// each one is checked painted in the page at 390×844, 834×1112 and 1440×900, as the owner of hub `a`:
//   - Services: the briefcase of its tab and its «My apps» tile, the gift of «Packages», the archive box of
//     «Archive», and the star of «Main service» in «Professionals who do it» — filled on the main one, empty
//     (the button that makes it theirs) on the others, as the old Staff record; pressing it fills it.
//   - Tasks: the checkbox of its tab and its tile, «Details» (open), «Start» (play) and «Complete» (double
//     check) of a task, and «Open» (open) of a project.
//   - Price Lists: the pricetag of its «My apps» tile.
// «Painted» = the `ion-icon` names that icon (its `name`, or the data URL the shell registered for it, which a
// DataTable action hands as its `icon`) and draws a non-empty SVG. What the run creates is deleted.
import { expect, type Locator, type Page, test } from '@playwright/test';

import { A, openApps, psql, shot, shown } from './helpers';
import { cleanUp as cleanServices, FLOW_VIEWPORTS, named, ownerPage, post, settled } from './service-helpers';
import { cleanUp as cleanTasks, named as taskNamed } from './task-helpers';

const KEY = 'FIX-UI-SHELL-ICONS-SERVICE-TASK';

function cleanUp(): void {
  cleanServices();
  cleanTasks();
}

test.beforeAll(cleanUp);
test.afterAll(cleanUp);

/** The `ion-icon` paints the registered icon `name`: it names it, the shell registered it, and its SVG is drawn. */
async function expectPaints(icon: Locator, name: string, what: string): Promise<void> {
  await expect(icon, what).toBeVisible();
  await icon.scrollIntoViewIfNeeded();
  await expect
    .poll(
      () =>
        icon.evaluate((el, wanted) => {
          const registry = (window as unknown as { Ionicons?: { map?: Map<string, string> } }).Ionicons?.map;
          const src = registry?.get(wanted);
          const ion = el as HTMLElement & { name?: string; icon?: string };
          const svg = ion.shadowRoot?.querySelector('.icon-inner svg');
          return {
            registered: typeof src === 'string',
            named: ion.name === wanted || (src !== undefined && ion.icon === src),
            drawn: (svg?.childElementCount ?? 0) > 0,
          };
        }, name),
      { message: `${what} paints ${name}` },
    )
    .toEqual({ registered: true, named: true, drawn: true });
}

/** The icon of a row action: on its button, or on the same entry inside «⋮» when the row folds its actions
 *  (the menu is left open; `closeMenu` shuts it). */
async function actionIcon(page: Page, table: string, id: string, action: string): Promise<Locator> {
  const button = shown(page).locator(`[data-testid=${table}-row-${id}-${action}]`);
  const menu = shown(page).locator(`[data-testid=${table}-row-${id}-menu]`);
  await button.or(menu).first().waitFor({ state: 'visible' });
  if (await button.isVisible()) return button.locator('ion-icon').first();
  const open = page.locator('ion-popover:not(.overlay-hidden)');
  if (!(await open.isVisible())) await menu.click();
  return open.locator(`[data-testid=${table}-row-${id}-${action}] ion-icon`).first();
}

async function closeMenu(page: Page): Promise<void> {
  const open = page.locator('ion-popover:not(.overlay-hidden)');
  if (await open.isVisible()) {
    await page.keyboard.press('Escape');
    await expect(open).toBeHidden();
  }
}

/** The icon of the tile `label` in «My apps». */
const tileIcon = (sheet: Locator, label: string): Locator =>
  sheet
    .locator('[data-testid=apps-launcher-app]')
    .filter({ has: sheet.page().locator('.apps-launcher-name', { hasText: new RegExp(`^\\s*${label}\\s*$`) }) })
    .locator('ion-icon')
    .first();

FLOW_VIEWPORTS.forEach((vp) => {
  test(`HUB_SHELL icons at ${vp.label}: Services, Tasks and Price Lists wear the old modules' icons`, async ({ browser }) => {
    const { context, page } = await ownerPage(browser, '/service/services', vp);
    try {
      // What the screens show: a service two people perform, Ana its main one, and a task in a project.
      const service = await post<{ id: string; name: string }>(context, '/service/services', {
        name: named('Icons'),
        price: 2000,
        duration_minutes: 30,
        tax_category_key: 'service.generic',
      });
      const ana = await post<{ id: string }>(context, '/staff/members', { first_name: named('Ana'), last_name: 'Star' });
      const bea = await post<{ id: string }>(context, '/staff/members', { first_name: named('Bea'), last_name: 'Star' });
      const main = await post<{ id: string }>(context, '/service/assignments/assign', { service_id: service.id, member_id: ana.id }, 200);
      const other = await post<{ id: string }>(context, '/service/assignments/assign', { service_id: service.id, member_id: bea.id }, 200);
      await post(context, '/service/assignments/update', { id: main.id, is_primary: true }, 200);
      const stamp = Date.now().toString(36);
      const project = await post<{ id: string }>(context, '/task/projects', { code: `e2e-icons-${stamp}`, name: taskNamed('Icons') });
      const task = await post<{ id: string }>(context, '/task/tasks', { title: taskNamed('Icons'), project_id: project.id });

      // Services: its tabs and «Archive».
      await page.goto(`${A}/service/services`);
      const view = shown(page);
      await expect(view.locator('[data-testid=service-services-row]', { hasText: service.name })).toBeVisible();
      await expectPaints(view.locator('[data-testid=tab-services] ion-icon'), 'briefcase-outline', `Services tab ${vp.label}`);
      await expectPaints(view.locator('[data-testid=tab-packages] ion-icon'), 'gift-outline', `Packages tab ${vp.label}`);
      await expectPaints(await actionIcon(page, 'service-services', service.id, 'archive'), 'archive-outline', `«Archive» ${vp.label}`);
      await closeMenu(page);

      // «Professionals who do it»: the filled star on Ana's, the empty one (a button) on Bea's.
      await view.locator('[data-testid=service-services-row]', { hasText: service.name }).getByText(service.name).first().click();
      const form = page.locator('ion-modal[data-testid=service-form]');
      await expect(form).toBeVisible();
      const primary = (id: string) => form.locator(`[data-testid=service-professionals-primary-${id}]`);
      const makePrimary = (id: string) => form.locator(`[data-testid=service-professionals-make-primary-${id}]`);
      await expectPaints(primary(main.id), 'star', `Ana's star ${vp.label}`);
      await expect(primary(main.id)).toHaveAttribute('aria-label', 'Main service');
      await expect(makePrimary(main.id)).toHaveCount(0);
      await expectPaints(makePrimary(other.id).locator('ion-icon'), 'star-outline', `Bea's star ${vp.label}`);
      // Ionic hands the button's name to its native <button> (and takes it off the host).
      await expect(makePrimary(other.id).locator('button')).toHaveAttribute('aria-label', 'Make it their main service');
      await settled(page);
      await page.screenshot({ path: shot(`${KEY}-${vp.label}`) });

      // The empty star makes it Bea's main service (one per person: Ana's stays hers) and fills.
      await makePrimary(other.id).click();
      await expectPaints(primary(other.id), 'star', `Bea's star, pressed, ${vp.label}`);
      await expect(makePrimary(other.id)).toHaveCount(0);
      await expectPaints(primary(main.id), 'star', `Ana's star, kept, ${vp.label}`);
      await expect
        .poll(() => psql(`select string_agg(is_primary::text, ',' order by member_id = '${ana.id}') from service_assignment where service_id = '${service.id}'`))
        .toBe('true,true');
      await form.locator('[data-testid=service-form-cancel]').click();
      await expect(form).toBeHidden();

      // Tasks: its tabs and the actions of a task.
      await page.goto(`${A}/task/tasks`);
      const tasks = shown(page);
      await expect(tasks.locator('[data-testid=task-tasks-row]').first()).toBeVisible();
      await expectPaints(tasks.locator('[data-testid=tab-tasks] ion-icon'), 'checkbox-outline', `Tasks tab ${vp.label}`);
      await expectPaints(tasks.locator('[data-testid=tab-projects] ion-icon'), 'folder-outline', `Projects tab ${vp.label}`);
      for (const [action, icon] of [
        ['detail', 'open-outline'],
        ['start', 'play-circle-outline'],
        ['complete', 'checkmark-done-outline'],
      ] as const) {
        await expectPaints(await actionIcon(page, 'task-tasks', task.id, action), icon, `«${action}» ${vp.label}`);
      }
      await closeMenu(page);
      await settled(page);
      await page.screenshot({ path: shot(`${KEY}-tasks-${vp.label}`) });

      // Projects: «Open».
      await page.goto(`${A}/task/projects`);
      await expect(shown(page).locator('[data-testid=task-projects-row]').first()).toBeVisible();
      await expectPaints(await actionIcon(page, 'task-projects', project.id, 'open'), 'open-outline', `«Open» ${vp.label}`);
      await closeMenu(page);

      // «My apps»: the tiles of Services, Tasks and Price Lists.
      const sheet = await openApps(page);
      await expectPaints(tileIcon(sheet, 'Services'), 'briefcase-outline', `Services tile ${vp.label}`);
      await expectPaints(tileIcon(sheet, 'Tasks'), 'checkbox-outline', `Tasks tile ${vp.label}`);
      await expectPaints(tileIcon(sheet, 'Price Lists'), 'pricetag', `Price Lists tile ${vp.label}`);
      // The owner's session for the fleet's visual sweep (`ui-clip-sweep.sh --storage-state`), when asked.
      if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
    } finally {
      await context.close();
    }
  });
});
