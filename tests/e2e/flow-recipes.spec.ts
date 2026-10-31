// flow: FLOW-F33 FLOW-F34 FLOW-F35 FLOW-F36
// The ready-made automations the apps bring (apps/flow/WORKBOOK.md FLOW-F33 to F36), end to end in each of the
// three sizes, as the owner and against the real apps: «Comes with Appointments» under the gallery, its card
// says what it does and why it asks each permission; «Turn it on» builds it on with exactly that permission
// (F33) and «See it» opens it; «Pause it» pauses it and keeps it (F34); built from an older version and
// renamed, it says «New version» and «Restore the factory one», asked first, brings today's back (F35); set
// up with a fault its app already fixed, nothing waits for the owner: no notice above «Your automations», and its
// «Only when…» already has what its app added, though nothing was written (F36). One screenshot per flow and size
// (`APP-FLOW-3-<flow>-<width>`). A business has one
// automation per recipe: it is removed before each size and after the run.
import { expect, type Page, test } from '@playwright/test';

import { confirmDialog, signedIn } from './flow-helpers';
import { A, psql, shot, shown } from './helpers';
import { noHorizontalScroll, settled, VIEWPORTS } from './schedule-helpers';

const REF = 'appointment/customer_cancelled';
const OLDER = '0'.repeat(64);
const FACTORY = 'Fill the gap when a customer cancels';

const card = (page: Page, part: string) => shown(page).locator(`[data-testid="flow-recipe-${part}-${REF}"]`);
const built = (column: string): string =>
  psql(`select ${column} from flow_flow where recipe = '${REF}' and deleted_at is null`);

function cleanUp(): void {
  const flows = `select id from flow_flow where recipe = '${REF}'`;
  psql([`delete from flow_flowrun where flow_id in (${flows})`, `delete from flow_flow where id in (${flows})`].join('; '));
}

test.beforeEach(cleanUp);
test.afterAll(cleanUp);

for (const viewport of VIEWPORTS) {
  test(`the ready-made automations the apps bring at ${viewport.label}`, async ({ browser }) => {
    test.setTimeout(120_000);
    const { context, page } = await signedIn(browser, '/flow/automations', viewport);
    const snap = async (flow: string): Promise<void> => {
      await settled(page);
      await page.screenshot({ path: shot(`APP-FLOW-3-${flow}-${viewport.label}`) });
    };
    try {
      // FLOW-F33: under the gallery, what Appointments brings; its card in words; on with exactly its permission.
      await expect(shown(page).locator('[data-testid="flow-recipes-appointment"]')).toContainText('Comes with Appointments');
      await card(page, 'open').click();
      const panel = card(page, 'panel');
      await expect(panel).toContainText('This automation comes with Appointments.');
      await expect(panel).toContainText('Create a task');
      await expect(panel).toContainText('Leaves you the task, so you remember to offer the free time.');
      await expect(panel).not.toContainText('task.task.create');
      await card(page, 'enable').click();
      await expect(card(page, 'open')).toContainText('Active');
      await expect(card(page, 'disable')).toBeVisible();
      expect(built(`enabled::text || ' ' || grants::text`)).toBe('true ["task.task.create"]');
      await card(page, 'panel').scrollIntoViewIfNeeded();
      await noHorizontalScroll(page, viewport.label);
      await snap('FLOW-F33');

      // FLOW-F34: paused, never deleted: its permission stays.
      await card(page, 'disable').click();
      await expect(card(page, 'open')).toContainText('Paused');
      await expect(card(page, 'enable')).toBeVisible();
      expect(built(`enabled::text || ' ' || grants::text || ' ' || (deleted_at is null)::text`)).toBe('false ["task.task.create"] true');
      await noHorizontalScroll(page, viewport.label);
      await snap('FLOW-F34');
      await card(page, 'see').click();
      await page.waitForURL(/\/flow\/automations\/[0-9a-f-]+$/);
      await expect(shown(page).locator('[data-testid=flow-editor-name] input')).toHaveValue(FACTORY);

      // FLOW-F35: renamed by the owner and built from an older version: «New version», then the factory one back.
      psql(`update flow_flow set name = 'My gap', recipe_digest = '${OLDER}' where recipe = '${REF}'`);
      await page.goto(`${A}/flow/automations`);
      await expect(card(page, 'open')).toContainText('New version');
      await card(page, 'open').click();
      await expect(card(page, 'panel')).toContainText('There is a new version of this automation.');
      await card(page, 'restore').click();
      await confirmDialog(page, 'Restore the factory version?');
      await expect(card(page, 'open')).not.toContainText('New version');
      await expect.poll(() => built('name')).toBe(FACTORY);
      expect(built('enabled::text')).toBe('false');
      await card(page, 'panel').scrollIntoViewIfNeeded();
      await noHorizontalScroll(page, viewport.label);
      await snap('FLOW-F35');

      // FLOW-F36: set up with a fault its app already fixed, nothing waits for the owner: no notice above the list,
      // and its «Only when…» already has what its app added (it never starts on a team's cancellation), though
      // nothing was written behind the owner's back.
      psql(`update flow_flow set name = 'My gap', trigger_filter = '{}', recipe_digest = '${OLDER}' where recipe = '${REF}'`);
      await page.goto(`${A}/flow/automations`);
      // The list has loaded before looking for a notice: the automation is there, paused.
      await expect(shown(page).locator(`[data-testid="flow-list-toggle-${built('id')}"]`)).toBeVisible();
      await expect(shown(page).locator('[data-testid=flow-repairs]')).toHaveCount(0);
      await expect(shown(page).getByText('starts in more cases than it should')).toHaveCount(0);
      await noHorizontalScroll(page, viewport.label);
      await snap('FLOW-F36');
      await page.goto(`${A}/flow/automations/${built('id')}`);
      await shown(page).locator('[data-testid=flow-trigger-open]').click();
      await expect(shown(page).locator('[data-testid^=flow-trigger-filter-row-]')).toHaveCount(1);
      expect(built(`trigger_filter::text || ' ' || name || ' ' || enabled::text`)).toBe('{} My gap false');
    } finally {
      await context.close();
    }
  });
}
