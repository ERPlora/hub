// OutfitKit is gone (PLAN §16.11; packages/ui, 2026-10-13): no `ok-*` element anywhere in the DOM
// (shadow roots included) of the list (table and cards), the detail, «New item» and «Edit item»; no
// `ok-*` attribute on the demo's own markup; no `ok-*` custom element defined; no OutfitKit module
// loaded; and no `--ok-*` custom property left in the DataTable's computed styles.
import { type Page, expect, test } from '@playwright/test';

import { A, createItem, listReady, login, record, shot, shown, uniqueName } from './helpers';

/** What is left of OutfitKit on the current screen. */
async function outfitkitTraces(page: Page) {
  return page.evaluate(() => {
    const all: Element[] = [];
    const walk = (root: Document | ShadowRoot) => {
      for (const el of root.querySelectorAll('*')) {
        all.push(el);
        if (el.shadowRoot) walk(el.shadowRoot);
      }
    };
    walk(document);
    const tags = [...new Set(all.filter((el) => el.tagName.startsWith('OK-')).map((el) => el.tagName.toLowerCase()))];
    const attributes = [
      ...new Set(all.flatMap((el) => [...el.attributes].map((a) => a.name)).filter((name) => name.startsWith('ok-'))),
    ];
    const defined = ['ok-data-table', 'ok-empty-state', 'ok-inline-feedback', 'ok-button', 'ok-icon', 'ok-widget-board'].filter(
      (tag) => customElements.get(tag) !== undefined,
    );
    const modules = performance
      .getEntriesByType('resource')
      .map((e) => e.name)
      .filter((url) => /outfitkit/i.test(url));
    const tableRoot = document.querySelector('.ion-page:not(.ion-page-hidden) .data-table');
    const okProps = new Set<string>();
    if (tableRoot) {
      for (const el of [tableRoot, ...tableRoot.querySelectorAll('*')].slice(0, 400)) {
        const style = getComputedStyle(el);
        for (let i = 0; i < style.length; i += 1) if (style[i].startsWith('--ok-')) okProps.add(style[i]);
      }
    }
    return { elements: all.length, tags, attributes, defined, modules, dataTableOkProps: [...okProps], dataTableFound: !!tableRoot };
  });
}

test('no ok-* element, attribute, definition, module or --ok-* token on list, cards, detail, create and edit', async ({ page, context }) => {
  await login(page, A);
  const item = await createItem(context, A, uniqueName('No OutfitKit'));
  const screens: Record<string, Awaited<ReturnType<typeof outfitkitTraces>>> = {};

  await page.goto('/demo/items');
  await listReady(page);
  screens.list = await outfitkitTraces(page);
  // The control catches the positive: an ok-* element inside a shadow root, an ok-* attribute and a
  // --ok-* token on the DataTable are all reported, then removed.
  await page.evaluate(() => {
    const host = document.createElement('div');
    host.id = 'ok-probe-host';
    host.attachShadow({ mode: 'open' }).append(document.createElement('ok-probe'));
    host.setAttribute('ok-text', 'probe');
    document.body.append(host);
    (document.querySelector('.ion-page:not(.ion-page-hidden) .data-table') as HTMLElement).style.setProperty('--ok-probe', '1');
  });
  const probe = await outfitkitTraces(page);
  await page.evaluate(() => {
    document.getElementById('ok-probe-host')?.remove();
    (document.querySelector('.ion-page:not(.ion-page-hidden) .data-table') as HTMLElement).style.removeProperty('--ok-probe');
  });
  expect(probe.tags).toEqual(['ok-probe']);
  expect(probe.attributes).toEqual(['ok-text']);
  expect(probe.dataTableOkProps).toContain('--ok-probe');
  await shown(page).locator('[data-testid=demo-items-view-cards]').click();
  await expect(shown(page).locator('ion-card[data-testid=demo-items-row]').first()).toBeVisible();
  screens.cards = await outfitkitTraces(page);
  await page.screenshot({ path: shot('no-outfitkit--cards') });
  await shown(page).locator('[data-testid=demo-items-view-table]').click();

  await page.goto(`/demo/items/${item.id}`);
  await expect(shown(page).locator('[data-testid=demo-detail-status]')).toBeVisible();
  screens.detail = await outfitkitTraces(page);

  await page.goto('/demo/items/new');
  await expect(shown(page).locator('[data-testid=demo-form]')).toBeVisible();
  screens.create = await outfitkitTraces(page);

  await page.goto(`/demo/items/${item.id}/edit`);
  await expect(shown(page).locator('[data-testid=demo-form-name] input')).toHaveValue(item.name);
  screens.edit = await outfitkitTraces(page);

  record('no-outfitkit', screens);
  expect(screens.list.dataTableFound).toBe(true);
  for (const [name, found] of Object.entries(screens)) {
    expect(found.tags, `${name}: ok-* elements`).toEqual([]);
    expect(found.attributes, `${name}: ok-* attributes`).toEqual([]);
    expect(found.defined, `${name}: ok-* custom elements defined`).toEqual([]);
    expect(found.modules, `${name}: OutfitKit modules loaded`).toEqual([]);
    expect(found.dataTableOkProps, `${name}: --ok-* in the DataTable`).toEqual([]);
  }
});
