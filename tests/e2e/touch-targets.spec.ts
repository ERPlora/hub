// Touch targets of the shared components and of hub#1074…#1078, measured in Chrome with a coarse pointer. The demo
// owner only visits existing screens: no business record is created, changed or removed. Failure screenshots and traces
// come from the shared Playwright configuration; a passing run captures nothing.
import { expect, type Locator, test } from '@playwright/test';

import { A, horizontalOverflow, login, OWNER, shown } from './helpers';

const VIEWPORTS = [
  { width: 390, height: 844 },
  { width: 834, height: 1112 },
];

test.use({ hasTouch: true, locale: 'en-US' });

async function expect44(targets: Locator, label: string): Promise<void> {
  await expect(targets.first(), `${label}: at least one visible control`).toBeVisible();
  const boxes = await targets.evaluateAll((elements) =>
    elements.map((element) => {
      const rect = element.getBoundingClientRect();
      return {
        control: element.getAttribute('data-testid') ?? element.textContent?.trim() ?? element.tagName,
        width: rect.width,
        height: rect.height,
      };
    }),
  );
  for (const box of boxes) {
    expect.soft(box.width, `${label}: ${box.control} width`).toBeGreaterThanOrEqual(44);
    expect.soft(box.height, `${label}: ${box.control} height`).toBeGreaterThanOrEqual(44);
  }
}

for (const viewport of VIEWPORTS) {
  test(`QA touch targets are at least 44x44 at ${viewport.width}x${viewport.height}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await login(page, A, '/', OWNER);

    await expect44(page.locator('.app-topbar ion-button:visible'), 'topbar');

    const setup = shown(page).locator('[data-testid="setup-card"]');
    await expect(setup).toHaveAttribute('aria-busy', 'false');
    const toggle = setup.locator('[data-testid="setup-toggle"]:visible');
    if (await toggle.count()) await toggle.click();
    await expect44(setup.locator('ion-button[size="small"]:visible'), 'setup');
    await expect44(shown(page).locator('[data-testid="widgets-customize"]:visible'), 'customize panel');
    expect(await horizontalOverflow(page), `home at ${viewport.width}px`).toBeLessThanOrEqual(1);

    await page.goto(`${A}/profile`);
    await expect(shown(page).locator('[data-testid="profile-summary"]')).toBeVisible();
    await expect44(shown(page).locator('[data-testid="profile-photo-choose"]:visible'), 'profile photo choose');
    const removePhoto = shown(page).locator('[data-testid="profile-photo-remove"]:visible');
    if (await removePhoto.count()) await expect44(removePhoto, 'profile photo remove');
    expect(await horizontalOverflow(page), `profile at ${viewport.width}px`).toBeLessThanOrEqual(1);

    await page.goto(`${A}/files`);
    const files = shown(page).locator('[data-testid="files-manager"]');
    await expect(files.locator('[data-testid="files-view-list"]')).toBeVisible();
    // «New folder» and «Upload» come with the listing's permissions: measured once they are there (hub#1075).
    await expect(files.locator('[data-testid="files-upload"]')).toBeVisible();
    await expect44(files.locator('ion-button[size="small"]:visible'), 'files');
    expect(await horizontalOverflow(page), `files at ${viewport.width}px`).toBeLessThanOrEqual(1);

    await page.goto(`${A}/settings#general`);
    const device = shown(page).locator('[data-testid="device-row"]').first();
    await expect(device).toBeVisible();
    await expect44(device.locator('ion-button[size="small"]:visible'), 'devices');
    expect(await horizontalOverflow(page), `settings at ${viewport.width}px`).toBeLessThanOrEqual(1);

    await page.goto(`${A}/inventory/products`);
    await expect44(shown(page).locator('[data-testid="inventory-products-csv-import-button"]:visible'), 'CSV import');
    await expect44(shown(page).locator('[data-testid="inventory-products-csv-export"]:visible'), 'CSV export');
    expect(await horizontalOverflow(page), `products at ${viewport.width}px`).toBeLessThanOrEqual(1);

    await page.goto(`${A}/sale/pos`);
    const till = shown(page).locator('[data-testid="pos-till"]');
    await expect(till).toBeVisible();
    await expect44(till.locator('[data-testid="pos-screen-menu"]:visible'), 'POS screen menu');
    const fab = till.locator('[data-testid="pos-cart-fab"]:visible');
    if (await fab.count()) await fab.click();
    const cart = till.locator('[data-testid="pos-cart-drawer"]');
    await expect(cart).toBeVisible();
    await expect44(cart.locator('[data-testid="pos-table-trigger"]:visible'), 'POS table trigger');
    await expect44(cart.locator('[data-testid="pos-open-checks"]:visible'), 'POS open checks');
    await expect44(cart.locator('[data-testid="pos-check-title-edit"]:visible'), 'POS check title edit');
    expect(await horizontalOverflow(page), `POS at ${viewport.width}px`).toBeLessThanOrEqual(1);
  });
}
