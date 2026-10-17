// PoC §8.6: list, detail, «New item» and «Edit item» at 390×844 (phone), 834×1194 (tablet) and
// 1440×900 (desktop) with no horizontal scroll. The hub's shell is the old hub's (PLAN-MIGRATIONS §16):
// the side menu pinned from 992 px (the topbar's rail toggle) and a drawer below (its hamburger), the ⠿
// «My apps» sheet in the topbar, and no Back on the list, the root of the app.
import { type Page, expect, test } from '@playwright/test';

import { A, api, createItem, listReady, login, openApps, record, shot, shown, uniqueName } from './helpers';

const VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1194 },
  { label: '1440', width: 1440, height: 900 },
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

async function chromeState(page: Page) {
  const bar = shown(page);
  return {
    pinnedMenu: await page.locator('ion-menu.dash-menu').isVisible(),
    drawerButton: await bar.locator('ion-menu-button').isVisible(),
    railToggle: await bar.locator('[data-testid=topbar-rail]').isVisible(),
    back: await bar.locator('[data-testid=topbar-back]').isVisible(),
    apps: await bar.locator('[data-testid=topbar-apps]').isVisible(),
  };
}

test('390 / 834 / 1440: no horizontal scroll on list, detail, create and edit; the menu pinned from 992 px, a drawer below, apps in the topbar', async ({ page, context }) => {
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
    const chrome = await chromeState(page);
    await page.screenshot({ path: shot(`08-list-${vp.label}`) });

    // The way to another app is the «My apps» sheet at every width.
    const sheet = await openApps(page);
    await page.screenshot({ path: shot(`08-apps-open-${vp.label}`) });
    await sheet.locator('[data-testid=apps-launcher-app]', { hasText: 'Demo' }).click();
    await expect(page.locator('ion-modal[data-testid=apps-launcher]:not(.overlay-hidden)')).toHaveCount(0);
    await listReady(page);

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

    results[vp.label] = { list, detail, create, edit, chrome };
    for (const [screen, measured] of Object.entries({ create, edit })) {
      expect(measured.documentScrollWidth, `${vp.label} ${screen}`).toBeLessThanOrEqual(measured.innerWidth);
      expect(measured.contentScrollWidth!, `${vp.label} ${screen} content`).toBeLessThanOrEqual(measured.contentClientWidth!);
    }
    expect(list.documentScrollWidth, `${vp.label} list`).toBeLessThanOrEqual(list.innerWidth);
    expect(detail.documentScrollWidth, `${vp.label} detail`).toBeLessThanOrEqual(detail.innerWidth);
    expect(list.contentScrollWidth!, `${vp.label} list content`).toBeLessThanOrEqual(list.contentClientWidth!);
    expect(detail.contentScrollWidth!, `${vp.label} detail content`).toBeLessThanOrEqual(detail.contentClientWidth!);
    const pinned = vp.width >= 992;
    expect(chrome, `${vp.label} chrome`).toEqual({ pinnedMenu: pinned, drawerButton: !pinned, railToggle: pinned, back: false, apps: true });
  }
  record('08-viewports', results);
});
