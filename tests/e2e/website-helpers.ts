// What the website specs (website*.spec.ts) share and the rest of the e2e does not.
import type { Page } from '@playwright/test';

import { settled } from './helpers';

/**
 * The page at rest for its capture: no focus ring (the website's own step), then the harness's one wait, `settled`
 * (helpers.ts): nothing moving, in the document or in any shadow root (Bootstrap's buttons fade 150 ms, the dev server
 * injects the stylesheets after the first paint, and in the editor Ionic animates its dialogs and toasts in theirs),
 * and the page painted as it is now.
 */
export async function atRest(page: Page): Promise<void> {
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  await settled(page);
}
