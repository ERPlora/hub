// PoC §8.13, second pass: icons come from npm (`ionicons/icons` through `addIcons`, other sets baked
// by `unplugin-icons`), so every visible `ion-icon` of the shell and the demo pages — shadow roots
// included (ion-select, the topbar buttons…) — paints an inner SVG of non-zero size, with no request to
// any Iconify host, no icon fetched as a URL from our server and no failed request at all.
import { type Page, expect, test } from '@playwright/test';

import { A, createItem, type Item, listReady, login, openApps, psql, record, shot, shown, uniqueName } from './helpers';

const ICONIFY_HOSTS = /iconify\.design|simplesvg\.com|unisvg\.com|iconify/i;

type IconState = { where: string; name: string; host: string; painted: boolean; width: number; height: number };

/** The items this file made: deleted after it, whatever the run left. */
const mine: Item[] = [];

test.afterAll(() => {
  const ids = mine.map((item) => `'${item.id}'`).join(',');
  if (ids) psql(`delete from demo_itemline where item_id in (${ids}); delete from demo_item where id in (${ids})`);
});

/**
 * Every visible `ion-icon` once they all painted, or as they are after 5 s: an icon mounted with its screen
 * (the side menu's foot after a full load) paints its `<svg>` a few frames later. One that never paints
 * still comes back unpainted.
 */
async function icons(page: Page, where: string): Promise<IconState[]> {
  const deadline = Date.now() + 5_000;
  for (;;) {
    const found = await iconsNow(page, where);
    if (found.every((icon) => icon.painted) || Date.now() > deadline) return found;
    await page.waitForTimeout(100);
  }
}

/** Every visible `ion-icon` (light DOM and shadow roots) and whether it painted a sized `<svg>`. */
async function iconsNow(page: Page, where: string): Promise<IconState[]> {
  const found = await page.evaluate(() => {
    const out: { name: string; host: string; painted: boolean; width: number; height: number }[] = [];
    const walk = (root: Document | ShadowRoot) => {
      for (const el of root.querySelectorAll('*')) {
        if (el.tagName === 'ION-ICON' && (el as HTMLElement).checkVisibility({ visibilityProperty: true, opacityProperty: false })) {
          const box = el.getBoundingClientRect();
          if (box.width > 0 && box.height > 0) {
            const svg = el.shadowRoot?.querySelector('svg');
            const svgBox = svg?.getBoundingClientRect();
            out.push({
              name: el.getAttribute('name') ?? el.getAttribute('aria-label') ?? '(icon prop)',
              // The component it belongs to: the shadow host, or its nearest ion-* ancestor.
              host: ((el.getRootNode() as ShadowRoot).host ?? el.parentElement?.closest('[class*="data-table"], ion-button, ion-item, ion-segment-button, ion-searchbar, ion-menu-button'))?.tagName.toLowerCase() ?? '',
              painted: !!svg && !!svgBox && svgBox.width > 0 && svgBox.height > 0,
              width: Math.round(svgBox?.width ?? 0),
              height: Math.round(svgBox?.height ?? 0),
            });
          }
        }
        if (el.shadowRoot) walk(el.shadowRoot);
      }
    };
    walk(document);
    return out;
  });
  return found.map((icon) => ({ where, ...icon }));
}

test('every visible ion-icon paints a sized SVG; no Iconify request, no icon URL fetch, no failed request', async ({ page, context }) => {
  await login(page, A);
  const iconify: string[] = [];
  const iconUrlFetches: string[] = [];
  const failed: { url: string; error: string }[] = [];
  const abortedStreams: string[] = [];
  const badStatus: { url: string; status: number }[] = [];
  const ionWarnings: string[] = [];
  page.on('request', (req) => {
    if (ICONIFY_HOSTS.test(new URL(req.url()).hostname)) iconify.push(req.url());
    if (req.url().includes('%3Csvg') || req.url().includes('<svg')) iconUrlFetches.push(req.url().slice(0, 100));
  });
  page.on('requestfailed', (req) => {
    const error = req.failure()?.errorText ?? 'failed';
    // Leaving a screen (or changing its subscriptions) closes its live stream on purpose.
    if (req.url().includes('/api/live') && error === 'net::ERR_ABORTED') abortedStreams.push(req.url().slice(0, 60));
    else failed.push({ url: req.url(), error });
  });
  page.on('response', (res) => {
    if (res.status() >= 400) badStatus.push({ url: res.url(), status: res.status() });
  });
  page.on('console', (msg) => {
    if (/ionicons|could not load icon/i.test(msg.text())) ionWarnings.push(msg.text());
  });

  // Eleven of its own, so that the pager at 10 per page has a second page on any database: a run's own e2e
  // database starts empty (tests/e2e/README.md), and other runs' leftovers are no fixture.
  const name = uniqueName('Icons');
  for (let n = 1; n <= 11; n += 1) mine.push(await createItem(context, A, `${name} ${n}`));
  const item = mine[0];
  const all: IconState[] = [];

  // Desktop: the shell's topbar (back, apps, user), the list toolbar (search, choosers, segment,
  // «New item»), the pager (10 per page), the cards and the empty state of a search with no results.
  await page.goto('/demo/items');
  await listReady(page);
  await page.waitForTimeout(500);
  all.push(...(await icons(page, 'shell+list')));
  await shown(page).locator('.data-table__page-size-select').click();
  await page.locator('ion-popover ion-radio').filter({ hasText: /^\s*10\s*$/ }).click();
  await expect(shown(page).locator('[data-testid=demo-items-page-next]')).toBeVisible();
  all.push(...(await icons(page, 'list pager')));
  await page.screenshot({ path: shot('icons--list-1280') });
  await shown(page).locator('[data-testid=demo-items-view-cards]').click();
  await expect(shown(page).locator('ion-card[data-testid=demo-items-row]').first()).toBeVisible();
  all.push(...(await icons(page, 'cards')));
  await shown(page).locator('[data-testid=demo-items-view-table]').click();
  await shown(page).locator('[data-testid=demo-items-search] input').fill('zz-no-such-item-zz');
  await expect(shown(page).locator('[data-testid=demo-items-empty]')).toBeVisible();
  await page.waitForTimeout(300);
  all.push(...(await icons(page, 'empty state')));
  await page.screenshot({ path: shot('icons--empty-1280') });

  // Detail (topbar back), «New item» and «Edit item».
  await page.goto(`/demo/items/${item.id}`);
  await expect(shown(page).locator('[data-testid=demo-detail-status]')).toBeVisible();
  all.push(...(await icons(page, 'detail')));
  await shown(page).locator('[data-testid=demo-detail-edit]').click();
  await expect(shown(page).locator('[data-testid=demo-form-name] input')).toHaveValue(item.name);
  all.push(...(await icons(page, 'edit')));
  await page.goto('/demo/items/new');
  await expect(shown(page).locator('[data-testid=demo-form]')).toBeVisible();
  all.push(...(await icons(page, 'create')));

  // Phone: the topbar's ⠿ button and the «My apps» sheet (the side menu is a closed drawer there).
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/demo/items');
  await listReady(page);
  all.push(...(await icons(page, 'phone list')));
  await openApps(page);
  await page.waitForTimeout(400);
  all.push(...(await icons(page, 'phone apps')));
  await page.screenshot({ path: shot('icons--phone-apps-390') });
  await page.waitForTimeout(1000); // late requests

  const empty = all.filter((i) => !i.painted);
  record('icons', {
    checked: all.length,
    perScreen: Object.fromEntries([...new Set(all.map((i) => i.where))].map((w) => [w, all.filter((i) => i.where === w).length])),
    empty,
    sizes: [...new Set(all.map((i) => `${i.width}x${i.height}`))],
    notSquare: all.filter((i) => i.width !== i.height),
    iconify,
    iconUrlFetches,
    failed,
    abortedStreams: abortedStreams.length,
    badStatus,
    ionWarnings,
  });
  expect(all.length).toBeGreaterThan(10);
  expect(empty).toEqual([]);
  expect(iconify).toEqual([]);
  expect(iconUrlFetches).toEqual([]);
  expect(failed).toEqual([]);
  expect(badStatus).toEqual([]);
  expect(ionWarnings).toEqual([]);

  // Last (it warns on purpose): the control catches the positive, an icon name that is not
  // registered stays without its SVG.
  await page.evaluate(() => {
    const probe = document.createElement('ion-icon');
    probe.id = 'icon-probe';
    probe.setAttribute('name', 'zz-not-registered');
    probe.style.cssText = 'position:fixed;top:0;left:0;font-size:24px;z-index:99999';
    document.body.append(probe);
  });
  await page.waitForTimeout(500);
  const probe = (await icons(page, 'probe')).filter((i) => i.name === 'zz-not-registered');
  await page.evaluate(() => document.getElementById('icon-probe')?.remove());
  expect(probe).toHaveLength(1);
  expect(probe[0].painted).toBe(false);
});
