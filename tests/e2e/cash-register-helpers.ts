// The drawers of Cash register › Settings, as a spec walks them.
import type { Locator, Page } from '@playwright/test';

import { shown } from './helpers';
import { dialog } from './inventory-helpers';

/** Settings › Drawers › «Add drawer», `typed` as its name and «Save» pressed: the window and its name field. */
export async function addDrawerNamed(page: Page, typed: string): Promise<{ modal: Locator; name: Locator }> {
  await shown(page).locator('[data-testid=cash-register-registers-heading]').scrollIntoViewIfNeeded();
  await shown(page).locator('[data-testid=cash-register-registers-add]').click();
  const modal = dialog(page, 'cash-register-register');
  const name = modal.locator('[data-testid=cash-register-register-name]');
  await name.locator('input').fill(typed);
  await modal.locator('[data-testid=cash-register-register-submit]').click();
  return { modal, name };
}
