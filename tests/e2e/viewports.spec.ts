// PoC §8.6: list, detail, «New item» and «Edit item» at 390×844 (phone), 834×1194 (tablet) and
// 1440×900 (desktop) with no horizontal scroll; the menu is an overlay below `lg` and a fixed split
// pane from `lg` (992 px).
import { type Page, expect, test } from '@playwright/test';

import { A, api, createItem, listReady, login, record, shot, shown, uniqueName } from './helpers';

const VIEWPORTS = [
  { label: '390', width: 390, height: 844, splitPane: false },
  { label: '834', width: 834, height: 1194, splitPane: false },
  { label: '1440', width: 1440, height: 900, splitPane: true },
];

async function overflow(page: Page) {
  return page.evaluate(async () => {
    const content = document.querySelector('ion-router-outlet > .ion-page:not(.ion-page-hidden) ion-content') as
      | (HTMLElement & { getScrollElement?: () => Promise<HTMLElement> })
      | null;
    const inner = content?.getScrollElement ? await content.getScrollElement() : null;
    return {
      documentScrollWidth: document.documentElement.scrollWidth,
      innerWidth: window.innerWidth,
      contentScrollWidth: inner?.scrollWidth ?? null,
      contentClientWidth: inner?.clientWidth ?? null,
    };
  });
}

async function menuState(page: Page) {
  return page.evaluate(() => {
    const pane = document.querySelector('ion-split-pane');
    const menu = document.querySelector('ion-menu');
    const rect = menu?.getBoundingClientRect();
    return {
      splitPaneVisible: pane?.classList.contains('split-pane-visible') ?? false,
      menuPaneVisible: menu?.classList.contains('menu-pane-visible') ?? false,
      menuShown: !!rect && rect.width > 0 && getComputedStyle(menu!).display !== 'none' && !menu!.classList.contains('menu-hidden'),
    };
  });
}

test('390 / 834 / 1440: no horizontal scroll on list, detail, create and edit; overlay menu on phone and tablet, split pane on desktop', async ({ page, context }) => {
  await login(page, A);
  const item = await createItem(context, A, uniqueName('Viewport item with a fairly long name to test wrapping'));
  await api(context, A, 'POST', '/demo/items/add_line', { id: item.id, text: 'A line', qty: '2', client_line_id: crypto.randomUUID() });

  const results: Record<string, unknown> = {};
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await page.goto('/demo/items');
    await listReady(page);
    await page.waitForTimeout(600);
    const list = await overflow(page);
    const menu = await menuState(page);
    await page.screenshot({ path: shot(`08-list-${vp.label}`) });

    let overlayOpened: boolean | null = null;
    if (!vp.splitPane) {
      await shown(page).locator('ion-menu-button').click();
      await expect(page.locator('ion-menu')).toHaveClass(/show-menu/);
      overlayOpened = await page.evaluate(() => document.querySelector('ion-menu')?.classList.contains('menu-type-overlay') ?? false);
      await page.screenshot({ path: shot(`08-menu-open-${vp.label}`) });
      await page.locator('ion-menu ion-item', { hasText: 'Demo' }).click();
      await expect(page.locator('ion-menu')).not.toHaveClass(/show-menu/);
    }

    await page.goto(`/demo/items/${item.id}`);
    await expect(page.locator('[data-testid=demo-detail-status]')).toBeVisible();
    await page.waitForTimeout(600);
    const detail = await overflow(page);
    await page.screenshot({ path: shot(`08-detail-${vp.label}`) });

    // «New item» and «Edit item» are pages too (second pass).
    await page.goto('/demo/items/new');
    await expect(shown(page).locator('[data-testid=demo-form]')).toBeVisible();
    await page.waitForTimeout(400);
    const create = await overflow(page);
    await page.screenshot({ path: shot(`08-create-${vp.label}`) });
    await page.goto(`/demo/items/${item.id}/edit`);
    await expect(shown(page).locator('[data-testid=demo-form-name] input')).toHaveValue(item.name);
    await page.waitForTimeout(400);
    const edit = await overflow(page);
    await page.screenshot({ path: shot(`08-edit-${vp.label}`) });

    results[vp.label] = { list, detail, create, edit, menu, overlayOpened };
    for (const [screen, measured] of Object.entries({ create, edit })) {
      expect(measured.documentScrollWidth, `${vp.label} ${screen}`).toBeLessThanOrEqual(measured.innerWidth);
      expect(measured.contentScrollWidth!, `${vp.label} ${screen} content`).toBeLessThanOrEqual(measured.contentClientWidth!);
    }
    expect(list.documentScrollWidth, `${vp.label} list`).toBeLessThanOrEqual(list.innerWidth);
    expect(detail.documentScrollWidth, `${vp.label} detail`).toBeLessThanOrEqual(detail.innerWidth);
    expect(list.contentScrollWidth!, `${vp.label} list content`).toBeLessThanOrEqual(list.contentClientWidth!);
    expect(detail.contentScrollWidth!, `${vp.label} detail content`).toBeLessThanOrEqual(detail.contentClientWidth!);
    expect(menu.splitPaneVisible, `${vp.label} split pane`).toBe(vp.splitPane);
    if (vp.splitPane) expect(menu.menuShown).toBe(true);
    else expect(overlayOpened).toBe(true);
  }
  record('08-viewports', results);
});
