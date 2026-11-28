// What the specs of a business's backup share: the screen measured and captured once it is still, the file loaded
// back from Settings › Data › Import, and the rows of one part the file carries.
import { execFileSync } from 'node:child_process';

import { expect, type Page } from '@playwright/test';

import { capture, horizontalOverflow, shown, testid, untilStill } from './helpers';

/** The page once nothing loads or moves, without sideways scroll, captured as `name`. */
export async function snap(page: Page, name: string): Promise<void> {
  await expect(shown(page).locator('ion-skeleton-text:visible')).toHaveCount(0);
  await untilStill(page);
  expect(await horizontalOverflow(page), `${name}: no sideways scroll`).toBeLessThanOrEqual(0);
  await capture(page, name);
}

/** Loads the file `saved` from Import, past its review. */
export async function importBack(page: Page, saved: string): Promise<void> {
  await testid(page, 'data-section-import').click();
  await testid(page, 'import-file').setInputFiles(saved);
  await expect(testid(page, 'review')).toBeVisible();
  await testid(page, 'review-import').click();
}

/** The rows of `part` the file `saved` carries. */
export function rowsIn(saved: string, part: string): Record<string, unknown>[] {
  return JSON.parse(execFileSync('unzip', ['-p', saved, `data/${part}.json`], { encoding: 'utf8' }));
}
