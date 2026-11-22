// flow: FLOW-F02
// The list of automations opens sorted by «Últimas tocadas primero», and the order does what its name says: the
// automation touched last is the first row, also after touching an older one. Seen in Spanish in a phone, a tablet
// and a desk. Its automations are named «E2E FlowTouched …».
import { expect, test } from '@playwright/test';

import { deleteFlowsNamed, manualFlow } from './flow-helpers';
import { A, api, capture, saveSessionForTheSweep, shown, signedInSpanish, THREE_SIZES } from './helpers';
import { noHorizontalScroll } from './schedule-helpers';

const TAG = 'E2E FlowTouched';

test.beforeAll(() => deleteFlowsNamed(TAG));
test.afterAll(() => deleteFlowsNamed(TAG));

for (const viewport of THREE_SIZES) {
  test(`FLOW-F02 «Últimas tocadas primero» puts the automation touched last at the top, at ${viewport.label}`, async ({ browser }) => {
    test.setTimeout(120_000);
    const name = `${TAG} ${viewport.label} ${Date.now().toString(36)}`;
    const step = { id: 's1', kind: 'ask', title: `${name}?` };
    const { context, page } = await signedInSpanish(browser, viewport, '/flow/automations');
    try {
      const older = await manualFlow(context, `${name} older`, [step], []);
      await manualFlow(context, `${name} newer`, [step], []);
      await expect(shown(page).locator('[data-testid=flow-list-sort]')).toContainText('Últimas tocadas primero');
      await shown(page).locator('[data-testid=flow-list-search] input').fill(name);
      const rows = shown(page).locator('[data-testid=flow-list-row]');
      await expect(rows).toHaveCount(2);
      await expect(rows.nth(0)).toContainText(`${name} newer`);

      expect((await api(context, A, 'POST', '/flow/flows/set_enabled', { id: older, enabled: false })).status).toBe(200);
      await expect(rows.nth(0)).toContainText(`${name} older`);
      await expect(rows.nth(1)).toContainText(`${name} newer`);
      await noHorizontalScroll(page, viewport.label);
      await capture(page, `hub-2076-last-touched-first-${viewport.label}`);
      await saveSessionForTheSweep(context);
    } finally {
      await context.close();
    }
  });
}
