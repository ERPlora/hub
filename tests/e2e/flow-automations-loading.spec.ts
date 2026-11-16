// «Automations» with the business slow (hub#950): while the automations and the questions are read, the page says
// «Loading…» above the gallery — before, it showed the gallery alone, as if the business had no automation and no
// question waiting —; once they arrive, «Waiting for your answer» and «Your automations» show above it as before.
// The business is slowed by holding the live stream (`/api/live`, where the list, the questions and the drafts come)
// while the catalog, a plain read, answers at once: the order a slow business gives. One automation that asks first
// waits on its question; both are captured in the three sizes, loading and arrived.
// Everything created here is named «E2E FlowLoading …» and removed before and after.
// flow: FLOW-F01 FLOW-F29
import { expect, test } from '@playwright/test';

import { capture, psql, saveSessionForTheSweep, shown } from './helpers';
import { askingFlow, onAutomations } from './flow-helpers';

const KEY = 'hub-950-automations-loading';
const TAG = 'E2E FlowLoading';
const VIEWPORTS = [
  { label: '375', width: 375, height: 667 },
  { label: '768', width: 768, height: 1024 },
  { label: '1440', width: 1440, height: 900 },
];
/** The live stream's open (`/api/live?s=…`). */
const LIVE = /\/api\/live\?/;

function cleanUp(): void {
  const flows = `select id from flow_flow where name like '${TAG}%'`;
  psql(
    [
      `delete from flow_question where flow_id in (${flows})`,
      `delete from flow_flowrun where flow_id in (${flows})`,
      `delete from flow_flow where id in (${flows})`,
    ].join('; '),
  );
}

test.beforeAll(cleanUp);
test.afterAll(cleanUp);

for (const viewport of VIEWPORTS) {
  test(`FLOW-F01 says «Loading…» above the gallery while the automations and the questions are read, at ${viewport.label}`, async ({ browser }) => {
    test.setTimeout(120_000);
    await onAutomations(browser, viewport, TAG, async ({ context, page, name }) => {
      await askingFlow(context, name, [{ id: 's1', kind: 'ask', title: `${name}?` }]);

      // The business slow: the live stream opens only when let go.
      let letGo!: () => void;
      const held = new Promise<void>((resolve) => (letGo = resolve));
      await page.route(LIVE, async (route) => {
        await held;
        await route.continue();
      });
      await page.goto('/flow/automations');
      const screen = shown(page);
      const gallery = screen.locator('[data-testid=flow-gallery]');
      const loading = screen.locator('[data-testid=flow-page-loading]');
      await expect(gallery).toContainText('Pick one and it becomes yours, paused');
      // The catalog is in (its cards are painted): the moment the gallery stood alone before.
      await expect(gallery.locator('[data-testid^=flow-card-open-]').first()).toBeVisible();
      await expect(loading).toHaveText('Loading…');
      await expect(loading).toHaveAttribute('role', 'status');
      const [above, below] = [await loading.boundingBox(), await gallery.boundingBox()];
      expect(above!.y + above!.height).toBeLessThanOrEqual(below!.y);
      await expect(screen.locator('[data-testid=flow-inbox]')).toHaveCount(0);
      await expect(screen.locator('[data-testid=flow-list-section]')).toBeHidden();
      await capture(page, `${KEY}-loading-${viewport.label}`);

      letGo();
      const card = screen.locator('[data-testid=flow-inbox] article').filter({ hasText: name });
      await expect(card.locator('[data-testid^=flow-question-title-]')).toHaveText(`${name}?`);
      await expect(screen.locator('[data-testid=flow-list-section]')).toBeVisible();
      await expect(screen.locator('[data-testid=flow-list-row]').filter({ hasText: name }).first()).toBeVisible();
      await expect(loading).toHaveCount(0);
      await capture(page, `${KEY}-arrived-${viewport.label}`);
      await saveSessionForTheSweep(context);

      await card.locator('[data-testid^=flow-question-reject-]').click();
      await expect(card).toHaveCount(0);
    });
  });
}
