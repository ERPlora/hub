// flow: FLOW-F01 FLOW-F02 FLOW-F03 FLOW-F04 FLOW-F05 FLOW-F06 FLOW-F07 FLOW-F08 FLOW-F09 FLOW-F10 FLOW-F11 FLOW-F12 FLOW-F13 FLOW-F14 FLOW-F15 FLOW-F16 FLOW-F18 FLOW-F19
// Every flow of Automations with a screen (apps/flow/WORKBOOK.md), end to end in each of the three sizes,
// as the owner and against the real Tasks app, with one screenshot per flow and size
// (`APP-FLOW-1-<flow>-<width>`). The guide (F08) and a link to a card (F05, an unknown one opens nothing)
// come first; a card of the gallery is used (F04), back by the same link lands on it again, and it is
// allowed and withdrawn (F12). One automation is built from scratch (F09): «Something happens» (which the
// worker's relay starts on its own, F21) finds an event by its technical name, then a weekly schedule keeps its day
// when the time changes (F10); a task, a condition that compares two data and a wait that is removed (F11);
// tried (F13), allowed, turned on and saved (F14), run by hand (F15) and read in its history (F16). The
// list searches, filters, sorts, switches by its named switch and in bulk (F02, F03), copies and deletes
// (F06, F07). Two drafts of the assistant: one discarded (F19), the other reviewed, saved, allowed, turned
// on and run (F18). What a run creates is tagged `E2E FlowF` (plus the ids of the cards it used) and goes.
import { type Browser, expect, type Page, test } from '@playwright/test';

import { A, api, login, psql, shot, shown } from './helpers';
import { noHorizontalScroll, settled, VIEWPORTS } from './schedule-helpers';
import { pick, rowAction } from './task-helpers';

const TAG = 'E2E FlowF';
/** Automations made from a card of the gallery: they carry the card's name, so they go by their ids. */
const fromCards: string[] = [];

function cleanUp(): void {
  const ids = fromCards.filter((id) => /^[0-9a-f-]{36}$/.test(id)).map((id) => `'${id}'`);
  const flows = `select id from flow_flow where name like '${TAG}%'${ids.length ? ` or id in (${ids.join(', ')})` : ''}`;
  psql(
    [
      `delete from flow_draft where name like '${TAG}%' or flow_id in (${flows})`,
      `delete from flow_flowrun where flow_id in (${flows})`,
      `delete from flow_flow where id in (${flows})`,
      `delete from task_task where title like '${TAG}%'`,
    ].join('; '),
  );
}

test.beforeAll(cleanUp);
test.afterAll(cleanUp);

async function signedIn(browser: Browser, next: string, viewport: { width: number; height: number }) {
  const context = await browser.newContext({ baseURL: A, viewport, locale: 'en-US' });
  const page = await context.newPage();
  await login(page, A, next);
  return { context, page };
}

/** Picks `text` in the popover of the `IonSelect` `testid` of the page shown. */
async function choose(page: Page, testid: string, text: string): Promise<void> {
  await shown(page).locator(`[data-testid="${testid}"]`).click();
  const popover = page.locator('ion-popover.select-popover:not(.overlay-hidden)');
  await popover.locator('ion-radio', { hasText: text }).first().click();
  await expect(popover).toHaveCount(0);
}

/** Confirms the dialog titled `title` with its main button. */
async function confirmDialog(page: Page, title: string, beforeConfirm?: () => Promise<void>): Promise<void> {
  const dialog = page.locator('ion-modal.ep-form-modal').filter({ hasText: title });
  await expect(dialog.locator('.ep-form-modal__submit')).toBeInViewport();
  if (beforeConfirm) await beforeConfirm();
  await dialog.locator('.ep-form-modal__submit').click();
  await expect(dialog).toBeHidden();
}

const idFromUrl = (page: Page): string => new URL(page.url()).pathname.split('/').at(-1)!;

for (const viewport of VIEWPORTS) {
  test(`every flow of Automations with a screen at ${viewport.label}`, async ({ browser }) => {
    test.setTimeout(180_000);
    const stamp = `${viewport.label}-${Date.now().toString(36)}`;
    const name = `${TAG} ${stamp}`;
    const title = `${TAG} task ${stamp}`;
    const draftTitle = `${TAG} draft task ${stamp}`;
    const { context, page } = await signedIn(browser, '/flow/automations', viewport);
    const snap = async (flow: string): Promise<void> => {
      await settled(page);
      await page.screenshot({ path: shot(`APP-FLOW-1-${flow}-${viewport.label}`) });
    };
    try {
      // FLOW-F01: the drafts (if any), the automations (if any) and the gallery, always.
      await expect(shown(page).locator('[data-testid=flow-gallery]')).toContainText('Pick one and it becomes yours, paused');
      await expect(shown(page).locator('[data-testid=flow-new]')).toBeVisible();
      await expect(shown(page).locator('[data-testid=flow-card-welcome]')).toBeVisible();
      await noHorizontalScroll(page, viewport.label);
      await snap('FLOW-F01');

      // FLOW-F08: the guide, with what it cannot do yet (pm#134, flows#16).
      await shown(page).locator('[data-testid=flow-gallery-guide]').click();
      await page.waitForURL(/\/flow\/guide$/);
      for (const part of ['what', 'first', 'permissions', 'worked', 'limits']) {
        await expect(shown(page).locator(`[data-testid=flow-guide-section-${part}]`)).toBeVisible();
      }
      // What it already does (starting on its own when something happens, FLOW-F21) is no limit any more.
      await expect(shown(page).locator('[data-testid=flow-guide-section-limits]')).toContainText('Sending messages or asking the assistant');
      await expect(shown(page).locator('[data-testid=flow-guide-section-limits]')).not.toContainText('Starting on its own');
      await noHorizontalScroll(page, viewport.label);
      await snap('FLOW-F08');
      await shown(page).locator('[data-testid=flow-guide-back]').click();
      await page.waitForURL(/\/flow\/automations$/);

      // FLOW-F05: a link to a card that does not exist opens nothing (flows#115); a real one, its card.
      await page.goto(`${A}/flow/automations?template=nothing`);
      await expect(shown(page).locator('[data-testid=flow-gallery]')).toBeVisible();
      await expect(shown(page).locator('[data-testid^=flow-card-panel-]')).toHaveCount(0);
      await page.goto(`${A}/flow/automations?template=welcome`);
      const welcome = shown(page).locator('[data-testid=flow-card-panel-welcome]');
      await expect(welcome).toBeInViewport();
      await snap('FLOW-F05');

      // FLOW-F04: what the card does and asks, in words (flows#114); on a wide screen the cards share the
      // row (flows#40); «Use this one» opens the new one, paused, on its Permissions.
      await expect(welcome).toContainText('Create a task');
      await expect(welcome).not.toContainText('task.task.create');
      if (viewport.width >= 1440) {
        const first = await shown(page).locator('[data-testid=flow-card-bigSaleNote]').boundingBox();
        const second = await shown(page).locator('[data-testid=flow-card-bigSaleTask]').boundingBox();
        expect(Math.abs((first?.y ?? 0) - (second?.y ?? -100)), 'two cards on the same row').toBeLessThan(2);
      }
      await snap('FLOW-F04');
      await shown(page).locator('[data-testid=flow-card-use-welcome]').click();
      await page.waitForURL(/\/flow\/automations\/[0-9a-f-]+\?tab=permissions$/);
      const cardFlow = idFromUrl(page);
      fromCards.push(cardFlow);
      // flows#58: back by the same link, with the editor open, lands on the card, now «See it» first.
      await page.goBack();
      await page.waitForURL(/\/flow\/automations\?template=welcome$/);
      await expect(shown(page).locator('[data-testid=flow-card-panel-welcome]')).toBeVisible();
      await expect(shown(page).locator('[data-testid=flow-card-see-welcome]')).toBeVisible();
      await expect(shown(page).locator('[data-testid=flow-card-use-welcome]')).toBeVisible();

      // FLOW-F12: what it lacks, allowed whole, one withdrawn and allowed again.
      await page.goto(`${A}/flow/automations/${cardFlow}?tab=permissions`);
      const missing = shown(page).locator('[data-testid="flow-perm-missing-task.task.create"]');
      await expect(missing).toContainText('Waiting for your permission');
      await shown(page).locator('[data-testid=flow-perm-grantall]').click();
      await expect(shown(page).locator('[data-testid="flow-perm-granted-task.task.create"]')).toContainText('Allowed');
      await shown(page).locator('[data-testid="flow-perm-withdraw-task.task.create"]').click();
      await expect(missing).toBeVisible();
      await shown(page).locator('[data-testid=flow-perm-grantall]').click();
      await expect(shown(page).locator('[data-testid="flow-perm-granted-task.task.create"]')).toBeVisible();
      await noHorizontalScroll(page, viewport.label);
      await snap('FLOW-F12');

      // FLOW-F09, F10: from scratch. «Something happens» (no «not on its own yet» notice: FLOW-F21) finds an
      // event by its technical name (flows#50); a weekly schedule keeps its day when the time changes
      // (flows#77).
      await page.goto(`${A}/flow/automations/new`);
      const editor = shown(page);
      await expect(editor.locator('[data-testid=flow-editor-nosteps]')).toBeVisible();
      await expect(editor.locator('[data-testid=flow-editor-save]')).toHaveText('Save');
      await editor.locator('[data-testid=flow-editor-name] input').fill(name);
      await editor.locator('[data-testid=flow-trigger-open]').click();
      await choose(page, 'flow-trigger-kind', 'Something happens');
      await expect(editor.locator('[data-testid=flow-trigger-event-notice]')).toHaveCount(0);
      const eventInput = editor.locator('[data-testid=flow-trigger-event] input');
      await eventInput.click();
      await eventInput.fill('task.task.completed');
      await page.locator('[data-testid^=flow-trigger-event-option-]').first().click();
      await expect(editor.locator('[data-testid=flow-trigger-open]')).toContainText('When');
      await choose(page, 'flow-trigger-kind', 'On a schedule');
      await choose(page, 'flow-trigger-every', 'Every week');
      await choose(page, 'flow-trigger-weekday', 'Friday');
      await editor.locator('[data-testid=flow-trigger-time] input').fill('18:00');
      await expect(editor.locator('[data-testid=flow-trigger-open]')).toContainText('Every Friday at 18:00');
      await noHorizontalScroll(page, viewport.label);
      await snap('FLOW-F10');

      // FLOW-F11: a task with its title; a condition that compares a datum with another one, as a pill
      // (hub#1712), whose «one of» hint leaves «Data» and «Is» where they were (flows#121); a wait, removed.
      await editor.locator('[data-testid=flow-editor-add-command]').click();
      await pick(page, 'flow-step-action-s1', 'task', 'Create a task');
      await editor.locator('[data-testid=flow-step-param-s1-title-text-0]').fill(title);
      await editor.locator('[data-testid=flow-editor-add-condition]').click();
      await editor.locator('[data-testid=flow-step-cond-s2-add]').click();
      await choose(page, 'flow-step-cond-s2-path-0', 'Title');
      await choose(page, 'flow-step-cond-s2-op-0', 'one of');
      await expect(editor.locator('[data-testid=flow-step-cond-s2-hint-0]')).toHaveText('Separate the values with commas.');
      if (viewport.width >= 834) {
        const path = await editor.locator('[data-testid=flow-step-cond-s2-path-0]').boundingBox();
        const op = await editor.locator('[data-testid=flow-step-cond-s2-op-0]').boundingBox();
        expect(Math.abs((path?.y ?? 0) - (op?.y ?? -100)), '«Data» and «Is» on one line').toBeLessThan(2);
      }
      await choose(page, 'flow-step-cond-s2-op-0', 'equal to');
      await editor.locator('[data-testid=flow-step-cond-s2-insert-0]').click();
      const picker = page.locator('ion-modal[data-testid=flow-picker]');
      await expect(picker).toBeVisible();
      await picker.locator('[data-testid="flow-picker-steps.s1.title"]').click();
      await expect(picker).toBeHidden();
      await expect(editor.locator('[data-testid=flow-step-cond-s2-pill-0]')).toContainText('Title');
      await editor.locator('[data-testid=flow-editor-add-delay]').click();
      await expect(editor.locator('[data-testid=flow-step-s3]')).toBeVisible();
      await editor.locator('[data-testid=flow-step-remove-s3]').click();
      await expect(editor.locator('[data-testid=flow-step-s3]')).toHaveCount(0);
      await noHorizontalScroll(page, viewport.label);
      await snap('FLOW-F11');

      // FLOW-F09: saved, paused, the editor stays on it.
      await editor.locator('[data-testid=flow-editor-save]').click();
      await page.waitForURL(/\/flow\/automations\/[0-9a-f-]+$/);
      const flowId = idFromUrl(page);
      await expect(shown(page).locator('[data-testid=flow-editor-notice]')).toHaveText('Saved.');
      await expect(shown(page).locator('[data-testid=flow-editor-state]')).toContainText('Paused');
      await snap('FLOW-F09');

      // FLOW-F13: «Try it» runs nothing, and says the task is not allowed yet.
      await shown(page).locator('[data-testid=flow-editor-test]').click();
      await expect(shown(page).locator('[data-testid=flow-test-banner]')).toContainText('None of this is real.');
      await expect(shown(page).locator('[data-testid=flow-test-step-s1]')).toHaveAttribute('data-outcome', 'not_allowed');
      await noHorizontalScroll(page, viewport.label);
      await snap('FLOW-F13');

      // FLOW-F14: allowed, on and saved; the four tabs whole on a phone too (flows#142).
      await shown(page).locator('[data-testid=flow-editor-tab-permissions]').click();
      await shown(page).locator('[data-testid=flow-perm-grantall]').click();
      await expect(shown(page).locator('[data-testid="flow-perm-granted-task.task.create"]')).toBeVisible();
      await shown(page).locator('[data-testid=flow-editor-enabled]').click();
      await shown(page).locator('[data-testid=flow-editor-save]').click();
      await expect(shown(page).locator('[data-testid=flow-editor-notice]')).toHaveText('Saved.');
      await expect(shown(page).locator('[data-testid=flow-editor-state]')).toContainText('Active');
      for (const tab of ['steps', 'test', 'permissions', 'history']) {
        const cut = await shown(page)
          .locator(`[data-testid=flow-editor-tab-${tab}]`)
          .evaluate((element) => element.scrollWidth > element.clientWidth + 1);
        expect(cut, `the tab ${tab} is whole`).toBe(false);
      }
      await snap('FLOW-F14');

      // FLOW-F15: run by hand, asked first.
      await shown(page).locator('[data-testid=flow-editor-run]').click();
      await confirmDialog(page, 'Run it now?', () => snap('FLOW-F15'));
      await expect(page.locator('ion-toast').filter({ hasText: 'See it in History' }).last()).toBeVisible();

      // FLOW-F16: its history says it finished well, step by step; the task is in Tasks.
      await shown(page).locator('[data-testid=flow-editor-tab-history]').click();
      const run = shown(page).locator('[data-testid^=flow-run-]').filter({ hasText: 'Finished well' }).first();
      await expect(run).toBeVisible();
      await run.locator('[data-testid^=flow-run-toggle-]').click();
      await expect(run.locator('[data-testid^=flow-run-steps-]')).toContainText('Did: Create a task');
      await expect(run.locator('[data-testid^=flow-run-steps-]')).toContainText('The condition held');
      await noHorizontalScroll(page, viewport.label);
      await snap('FLOW-F16');
      const tasks = await api<{ rows: { title: string }[] }>(context, A, 'GET', `/task/tasks?search=${encodeURIComponent(title)}`);
      expect(tasks.data.rows.map((row) => row.title)).toEqual([title]);

      // FLOW-F19, F18: two drafts of the assistant; one discarded, the other reviewed, saved, allowed, on
      // and run (flows#12).
      const draftDefinition = {
        trigger: { kind: 'manual' },
        steps: [{ id: 's1', kind: 'command', operation: 'task.task.create', params: { title: draftTitle } }],
      };
      const kept = await api<{ id: string }>(context, A, 'POST', '/flow/drafts', { name: `${TAG} draft ${stamp}`, definition: draftDefinition, notes: ['I guessed the title.'] });
      expect(kept.status).toBe(201);
      const gone = await api<{ id: string }>(context, A, 'POST', '/flow/drafts', { name: `${TAG} other ${stamp}`, definition: draftDefinition, notes: [] });
      expect(gone.status).toBe(201);
      await page.goto(`${A}/flow/automations`);
      await expect(shown(page).locator(`[data-testid=flow-draft-${gone.data.id}]`)).toBeVisible();
      await shown(page).locator(`[data-testid=flow-draft-dismiss-${gone.data.id}]`).click();
      await expect(shown(page).locator(`[data-testid=flow-draft-${gone.data.id}]`)).toHaveCount(0);
      await expect(shown(page).locator(`[data-testid=flow-draft-${kept.data.id}]`)).toBeVisible();
      await snap('FLOW-F19');
      await shown(page).locator(`[data-testid=flow-draft-review-${kept.data.id}]`).click();
      await expect(shown(page).locator('[data-testid=flow-editor-draft]')).toContainText('I guessed the title.');
      await snap('FLOW-F18');
      await shown(page).locator('[data-testid=flow-editor-save]').click();
      await page.waitForURL(/\/flow\/automations\/[0-9a-f-]+$/);
      await shown(page).locator('[data-testid=flow-editor-tab-permissions]').click();
      await shown(page).locator('[data-testid=flow-perm-grantall]').click();
      await expect(shown(page).locator('[data-testid="flow-perm-granted-task.task.create"]')).toBeVisible();
      await shown(page).locator('[data-testid=flow-editor-enabled]').click();
      await shown(page).locator('[data-testid=flow-editor-save]').click();
      await expect(shown(page).locator('[data-testid=flow-editor-state]')).toContainText('Active');
      await shown(page).locator('[data-testid=flow-editor-run]').click();
      await confirmDialog(page, 'Run it now?');
      await expect(page.locator('ion-toast').filter({ hasText: 'See it in History' }).last()).toBeVisible();
      const drafted = await api<{ rows: { title: string }[] }>(context, A, 'GET', `/task/tasks?search=${encodeURIComponent(draftTitle)}`);
      expect(drafted.data.rows.map((row) => row.title)).toEqual([draftTitle]);

      // FLOW-F02: the list searches, filters and sorts; nothing matching says so and clears.
      await page.goto(`${A}/flow/automations`);
      await expect(shown(page).locator(`[data-testid=flow-draft-${kept.data.id}]`)).toHaveCount(0);
      await shown(page).locator('[data-testid=flow-list-search] input').fill(stamp);
      const row = shown(page).locator('[data-testid=flow-list-row]', { hasText: name });
      await expect(row).toContainText('Every Friday at 18:00');
      await expect(row).toContainText('Finished well');
      await choose(page, 'flow-list-sort', 'Name');
      await choose(page, 'flow-list-state', 'Only the paused ones');
      await expect(shown(page).locator('[data-testid=flow-list-nomatch]')).toContainText('Nothing here matches that.');
      await shown(page).locator('[data-testid=flow-list-clear]').click();
      await expect(row).toBeVisible();
      await shown(page).locator('[data-testid=flow-list-search] input').fill(name);
      await expect(shown(page).locator('[data-testid=flow-list-row]')).toHaveCount(1);
      await noHorizontalScroll(page, viewport.label);
      await snap('FLOW-F02');

      // FLOW-F03: the switch of a row has its name (flows#140); several, in bulk.
      const named = shown(page).getByRole('switch', { name: `Turn «${name}» on or off` });
      await named.click();
      await expect(row).toContainText('Paused');
      await expect(row.locator('ion-toggle')).not.toHaveClass(/toggle-checked/);
      await row.locator('ion-checkbox').click();
      await shown(page).locator('[data-testid=flow-list-bulk-enable]').click();
      await expect(row).toContainText('Active');
      await expect(row.locator('ion-toggle')).toHaveClass(/toggle-checked/);
      // The knob slides in its shadow root, out of `settled`'s sight: the shot waits until it rests on.
      await expect
        .poll(() =>
          row.locator('ion-toggle').evaluate((toggle) => {
            const knob = toggle.shadowRoot?.querySelector('.toggle-icon-wrapper');
            return !toggle.shadowRoot?.getAnimations().length && !!knob && new DOMMatrix(getComputedStyle(knob).transform).m41 > 0;
          }),
        )
        .toBe(true);
      await snap('FLOW-F03');

      // FLOW-F06: a copy, paused and without permissions.
      await rowAction(page, 'flow-list', flowId, 'duplicate');
      await shown(page).locator('[data-testid=flow-list-search] input').fill(stamp);
      const copy = shown(page).locator('[data-testid=flow-list-row]', { hasText: `Copy of ${name}` });
      await expect(copy).toContainText('Paused');
      await snap('FLOW-F06');

      // FLOW-F07: deleted, asked first.
      const copyId = await copy.getAttribute('data-id');
      await rowAction(page, 'flow-list', copyId!, 'delete');
      await confirmDialog(page, `Delete «Copy of ${name}»?`, () => snap('FLOW-F07'));
      await expect(copy).toHaveCount(0);
    } finally {
      await context.close();
    }
  });
}
