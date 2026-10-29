// Every flow of Demo in the three viewports (390, 834 and 1440 wide), as the owner and, for
// DEMO-F06, as the employee: one item goes through creation, edition, its lines, the second tablet
// that follows it live and its deletion. Each flow is a step that leaves its capture,
// `APP-DEMO-<flow>-<width>`, after checking that nothing scrolls sideways. The finer measures (the
// second under which another tablet is told, the optimistic line before the answer, `a` versus `b`)
// stay in their own specs: two-tabs-live, optimistic-add-line, two-orgs-isolated, reconnect. On a phone
// (≤767 px) the detail's actions are in the bar's «⋮» («More actions»), so its title is read whole.
// flow: DEMO-F01 DEMO-F02 DEMO-F03 DEMO-F04 DEMO-F05 DEMO-F06
import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, capture, createItem, EMPLOYEE, horizontalOverflow, hostPage, listReady, row, rowNames, rowOf, settled, shown, uniqueName } from './helpers';

const FLOW_VIEWPORTS = {
  390: { width: 390, height: 844 },
  834: { width: 834, height: 1112 },
  1440: { width: 1440, height: 900 },
} as const;

type Envelope = { id: string; error?: { code: string } };

/**
 * The capture of `flow` at `width`, once nothing moves (`settled`: no overlay coming or going in its shadow root, no
 * page transition nor floating label) and nothing scrolls sideways (`capture`).
 */
async function snap(page: Page, flow: string, width: string): Promise<void> {
  await settled(page);
  const overflow = await horizontalOverflow(page);
  expect(overflow, `${flow} at ${width}: no sideways scroll`).toBeLessThanOrEqual(0);
  await capture(page, `APP-DEMO-${flow}-${width}`);
}

/** A signed-in tablet at `viewport`, on `next`. */
async function tablet(
  browser: Parameters<typeof hostPage>[0],
  viewport: { width: number; height: number },
  next: string,
  credentials?: typeof EMPLOYEE,
): Promise<{ context: BrowserContext; page: Page }> {
  const signed = await hostPage(browser, A, { viewport, credentials });
  await signed.page.goto(`${A}${next}`);
  return signed;
}

const field = (scope: Locator, testid: string) => scope.locator(`[data-testid=${testid}]`);

/** The width at or below which the bar folds two or more actions into «⋮» (`AppTopbar`). */
const PHONE_MAX = 767;

/** Runs an action of the detail's bar: from «⋮» on a phone, from the bar itself on wider screens. */
async function act(page: Page, width: string, testid: string): Promise<void> {
  if (Number(width) <= PHONE_MAX) {
    await shown(page).locator('[data-testid=topbar-more]').click();
    await page.locator(`[data-testid=topbar-more-menu] [data-testid=${testid}]`).click();
    await expect(page.locator('[data-testid=topbar-more-menu]')).toHaveCount(0);
  } else {
    await shown(page).locator(`[data-testid=${testid}]`).click();
  }
}

/** The detail's bar: its title read whole (not cut with «…»), and where its actions are. */
async function expectBar(page: Page, width: string, title: string): Promise<void> {
  const heading = shown(page).locator('ion-title').first();
  await expect(heading).toContainText(title);
  const cut = await heading.evaluate((el) => {
    const box = (el.shadowRoot?.querySelector('.toolbar-title') ?? el) as HTMLElement;
    return box.scrollWidth > box.clientWidth;
  });
  expect(cut, `the title «${title}» at ${width} is read whole`).toBe(false);
  const phone = Number(width) <= PHONE_MAX;
  await expect(shown(page).locator('[data-testid=topbar-more]')).toHaveCount(phone ? 1 : 0);
  await expect(shown(page).locator('[data-testid=demo-detail-delete]')).toHaveCount(phone ? 0 : 1);
}
const errorUnder = (scope: Locator, testid: string) => field(scope, testid).locator('.error-text');

for (const [width, viewport] of Object.entries(FLOW_VIEWPORTS)) {
  test(`DEMO-F01 to DEMO-F06, every screen of Demo at ${width} wide`, async ({ browser }) => {
    // Short enough for a phone's title: «F390 mvhcvsqr 2».
    const name = uniqueName(`F${width}`);
    const { context, page } = await tablet(browser, viewport, '/demo/items');
    let id = '';
    try {
      await test.step('DEMO-F01 create an item', async () => {
        await listReady(page);
        await shown(page).locator('[data-testid=demo-items-add]').click();
        await page.waitForURL(/\/demo\/items\/new$/);
        const form = shown(page).locator('[data-testid=demo-form]');
        // Si falla: a name of spaces is refused under its field and nothing is saved.
        await field(form, 'demo-form-name').locator('input').fill('   ');
        await field(form, 'demo-form-save').click();
        await expect(errorUnder(form, 'demo-form-name')).toBeVisible();
        await expect(page).toHaveURL(/\/demo\/items\/new$/);
        // Back to the list and «New item» again: a clean form.
        await shown(page).locator('[data-testid=topbar-back]').click();
        await page.waitForURL(/\/demo\/items$/);
        await shown(page).locator('[data-testid=demo-items-add]').click();
        await page.waitForURL(/\/demo\/items\/new$/);
        await expect(errorUnder(form, 'demo-form-name')).toHaveCount(0);
        await field(form, 'demo-form-name').locator('input').fill(name);
        await field(form, 'demo-form-note').locator('textarea').fill('Written when it was created');
        await snap(page, 'DEMO-F01', width);
        const created = page.waitForResponse((r) => r.url().endsWith('/api/demo/items') && r.request().method() === 'POST');
        await field(form, 'demo-form-save').click();
        id = ((await (await created).json()) as Envelope).id;
        await page.waitForURL(/\/demo\/items$/);
        await expect(rowOf(page, id)).toBeVisible();
        expect((await rowNames(page))[0]).toBe(name);
        await expect(rowOf(page, id).locator('[data-testid=demo-item-lines]')).toHaveText('no lines');
      });

      const edited = `${name} 2`;
      await test.step('DEMO-F02 edit an item', async () => {
        await rowOf(page, id).click();
        await page.waitForURL(new RegExp(`/demo/items/${id}$`));
        await expectBar(page, width, name);
        await act(page, width, 'demo-detail-edit');
        await page.waitForURL(new RegExp(`/demo/items/${id}/edit$`));
        const form = shown(page).locator('[data-testid=demo-form]');
        await expect(field(form, 'demo-form-name').locator('input')).toHaveValue(name);
        await expect(field(form, 'demo-form-note').locator('textarea')).toHaveValue('Written when it was created');
        await field(form, 'demo-form-name').locator('input').fill(edited);
        await field(form, 'demo-form-status').click();
        await page
          .locator('ion-popover ion-radio, ion-alert button.alert-radio-button, ion-action-sheet button')
          .filter({ hasText: /^\s*Done\s*$/ })
          .first()
          .click();
        await expect(field(form, 'demo-form-status')).toHaveJSProperty('value', 'done');
        await snap(page, 'DEMO-F02', width);
        const sent = page.waitForRequest((r) => r.url().endsWith('/api/demo/items/update'));
        await field(form, 'demo-form-save').click();
        // Only what changed travels: the note, untouched, is not sent.
        expect(Object.keys((await sent).postDataJSON() as object).sort()).toEqual(['id', 'name', 'status']);
        await page.waitForURL(new RegExp(`/demo/items/${id}$`));
        const detail = shown(page);
        await expect(detail.locator('[data-testid=demo-detail-status]')).toHaveText('Done');
        await expect(detail.getByText(edited, { exact: true }).first()).toBeVisible();
        // On the detail itself: «Reopen» and the note, without opening the form.
        await act(page, width, 'demo-detail-toggle');
        await expect(detail.locator('[data-testid=demo-detail-status]')).toHaveText('Open');
        await detail.locator('[data-testid=demo-note] textarea').fill('Changed on the detail');
        await detail.locator('[data-testid=demo-note-save]').click();
        await expect(detail.locator('[data-testid=demo-note-save]')).toHaveJSProperty('disabled', true);
      });

      // The second tablet of DEMO-F05 follows the list while the first one adds lines.
      const other = await context.newPage();
      await test.step('DEMO-F04 add a line at once', async () => {
        await other.goto(`${A}/demo/items`);
        await listReady(other);
        await other.evaluate(() => ((window as unknown as { __sameDocument: boolean }).__sameDocument = true));
        const detail = shown(page);
        await detail.locator('[data-testid=demo-line-input-text] input').fill('Two boxes');
        await detail.locator('[data-testid=demo-line-input-qty] input').fill('2');
        await detail.locator('[data-testid=demo-line-add]').click();
        await expect(detail.locator('[data-testid=demo-line-text]')).toHaveText(['Two boxes']);
        await expect(detail.locator('[data-testid=demo-line-pending]')).toHaveCount(0);
        await expectBar(page, width, edited);
        await snap(page, 'DEMO-F04', width);
        // Si falla: a quantity that is not above zero is refused under its field.
        await detail.locator('[data-testid=demo-line-input-text] input').fill('Nothing');
        await detail.locator('[data-testid=demo-line-input-qty] input').fill('0');
        await detail.locator('[data-testid=demo-line-add]').click();
        await expect(errorUnder(detail, 'demo-line-input-qty')).toBeVisible();
        await expect(detail.locator('[data-testid=demo-line-text]')).toHaveText(['Two boxes']);
        // Si falla: on a done item the line is undone and a toast says why.
        await act(page, width, 'demo-detail-toggle');
        await expect(detail.locator('[data-testid=demo-detail-status]')).toHaveText('Done');
        await detail.locator('[data-testid=demo-line-input-qty] input').fill('1');
        await detail.locator('[data-testid=demo-line-input-text] input').fill('Too late');
        await detail.locator('[data-testid=demo-line-add]').click();
        const toast = page.locator('ion-toast');
        await expect(toast).toHaveJSProperty('message', 'This item is closed: open it to add lines.');
        await toast.evaluate((el) => (el as HTMLElement & { dismiss: () => Promise<boolean> }).dismiss());
        await expect(toast).toHaveCount(0);
        await expect(detail.locator('[data-testid=demo-line-text]')).toHaveText(['Two boxes']);
        await act(page, width, 'demo-detail-toggle');
        await expect(detail.locator('[data-testid=demo-detail-status]')).toHaveText('Open');
      });

      await test.step('DEMO-F05 see the change on another tablet', async () => {
        // The other tablet already shows the line added on the first one, without reloading.
        await expect(rowOf(other, id).locator('[data-testid=demo-item-lines]')).toHaveText('1 line');
        await shown(page).locator('[data-testid=demo-line-input-text] input').fill('One more');
        await shown(page).locator('[data-testid=demo-line-add]').click();
        await expect(rowOf(other, id).locator('[data-testid=demo-item-lines]')).toHaveText('2 lines');
        expect((await rowNames(other))[0]).toBe(edited);
        expect(await other.evaluate(() => (window as unknown as { __sameDocument?: boolean }).__sameDocument)).toBe(true);
        await snap(other, 'DEMO-F05', width);
      });

      await test.step('DEMO-F06 try it without permission', async () => {
        const employee = await tablet(browser, viewport, '/demo/items', EMPLOYEE);
        try {
          await listReady(employee.page);
          await expect(rowOf(employee.page, id)).toBeVisible();
          await expect(shown(employee.page).locator('[data-testid=demo-items-add]')).toHaveCount(0);
          await expect(shown(employee.page).locator('[data-testid=demo-stats]')).toHaveCount(0);
          await rowOf(employee.page, id).click();
          await employee.page.waitForURL(new RegExp(`/demo/items/${id}$`));
          const detail = shown(employee.page);
          await expect(detail.locator('[data-testid=demo-line-text]')).toHaveText(['Two boxes', 'One more']);
          for (const hook of ['demo-detail-edit', 'demo-detail-toggle', 'demo-detail-delete', 'demo-note-save', 'demo-line-form']) {
            await expect(detail.locator(`[data-testid=${hook}]`), hook).toHaveCount(0);
          }
          await snap(employee.page, 'DEMO-F06', width);
          // A line asks for a manager's approval instead (BASE-F84), said with its figures; nothing is added meanwhile.
          const refused = await api<Envelope>(employee.context, A, 'POST', '/demo/items/add_line', { id, text: 'Employee', qty: 1 });
          expect([refused.status, refused.data.error?.code]).toEqual([403, 'requires_elevation']);
        } finally {
          await employee.context.close();
        }
      });

      await test.step('DEMO-F03 delete an item', async () => {
        await other.goto(`${A}/demo/items/${id}`);
        await expect(shown(other).locator('[data-testid=demo-detail-status]')).toBeVisible();
        await act(page, width, 'demo-detail-delete');
        const alert = page.locator('ion-alert');
        await expect(alert.locator('.alert-title')).toHaveText('Delete this item and its lines?');
        await snap(page, 'DEMO-F03', width);
        await alert.locator('button.alert-button-role-destructive').click();
        await page.waitForURL(/\/demo\/items$/);
        await listReady(page);
        await expect(rowOf(page, id)).toHaveCount(0);
        await expect(shown(other).locator('[data-testid=demo-detail-error]')).toContainText('This item no longer exists.');
        await expect(shown(other).locator('[data-testid=demo-detail-delete]')).toHaveCount(0);
        expect((await api(context, A, 'GET', `/demo/items/detail?id=${id}`)).status).toBe(404);
        id = '';
      });
    } finally {
      if (id) await api(context, A, 'POST', '/demo/items/delete', { id });
      await context.close();
    }
  });
}

/** The longest the SDK holds a change of the live stream while it reconnects (its backoff caps at 30 s,
 *  `MAX_BACKOFF_MS` of `@erplora/ui/sdk`), with the 150 ms of its resubscribe debounce and room for the reopen. */
const LIVE_REOPEN_MS = 45_000;

// CLOSE-DEMO: more items than one page of `demo.item.list` holds (100, `ItemListIn.limit`). On a phone «Load more»
// grows the window only within those 100 (three in a row at 25 per page), and past them the list pages instead, so
// the oldest row is reached without «The items could not be loaded» (the second «Load more» at 50 per page asked for
// 150 rows and the server refused it with a 422).
test('DEMO-F05 with more than 100 items, every row in reach at 390, 834 and 1440 wide', async ({ browser }) => {
  test.setTimeout(240_000);
  const run = Date.now().toString(36);
  // 100 «LM<run> a NNN» fill the server's longest page exactly; 30 «LM<run> b NNN» more pass it.
  const name = (group: 'a' | 'b', n: number) => `LM${run} ${group} ${String(n).padStart(3, '0')}`;
  // The newest two, outside every search: once they are gone, the (debounced) search has been applied.
  const outside = [`LO${run} 1`, `LO${run} 2`];
  const { context, page } = await tablet(browser, FLOW_VIEWPORTS[1440], '/demo/items');
  const created: string[] = [];
  const loadError = () => shown(page).locator('[data-role=load-error]');
  const loadMore = () => shown(page).locator('[data-testid=demo-items-load-more]');
  /** Searches `text` and waits until the list is that search's: the outside items gone, `first` on top. */
  async function search(text: string, first: string): Promise<void> {
    await shown(page).locator('[data-testid=demo-items-search] input').fill(text);
    for (const other of outside) await expect(row(page, other)).toHaveCount(0);
    await expect.poll(async () => (await rowNames(page))[0]).toBe(first);
  }
  /**
   * Clicks `control` and waits for its answer: first the live stream reopened with the control's change, then the
   * last row shown changes, or the list fails. The SDK reopens the stream 150 ms after a change, but when the stream
   * has dropped (a loaded machine) it holds every change until its reconnection backoff ends, up to `LIVE_REOPEN_MS`:
   * the rows' 15 s count from the reopen, never from a click the backoff held (FIX DEMO-F05, rv-332).
   */
  async function advance(control: Locator, what: string): Promise<void> {
    const before = (await rowNames(page)).at(-1);
    const reopened = page.waitForResponse((answer) => answer.url().includes('/api/live') && answer.status() === 200, {
      timeout: LIVE_REOPEN_MS,
    });
    await control.click();
    await reopened.catch(() => {
      throw new Error(`${what}: the live stream did not reopen with the list's new window in ${LIVE_REOPEN_MS / 1000} s`);
    });
    await expect
      .poll(async () => (await loadError().count()) > 0 || (await rowNames(page)).at(-1) !== before, { timeout: 15_000 })
      .toBe(true);
    await expect(loadError(), `${what}: no «The items could not be loaded»`).toHaveCount(0);
  }
  try {
    for (const [group, count] of [['a', 100], ['b', 30]] as const) {
      for (let n = 1; n <= count; n += 1) created.push((await createItem(context, A, name(group, n))).id);
    }
    for (const other of outside) created.push((await createItem(context, A, other)).id);
    await listReady(page);

    await test.step('390: past 100 rows the phone pages to the oldest row', async () => {
      await page.setViewportSize(FLOW_VIEWPORTS[390]);
      await search(`LM${run}`, name('b', 30));
      const oldest = row(page, name('a', 1));
      for (let step = 1; step <= 6 && !(await oldest.isVisible()); step += 1) {
        const more = (await loadMore().count()) > 0;
        await advance(more ? loadMore() : shown(page).locator('[data-testid=demo-items-page-next]'), `step ${step}`);
      }
      await expect(oldest).toBeVisible();
      await expect(loadMore(), 'no «Load more» that would ask past 100 rows').toHaveCount(0);
      await snap(page, 'CLOSE-DEMO-more-than-100', '390');
    });

    await test.step('390: three «Load more» in a row at 25 per page, within the 100 rows', async () => {
      await page.setViewportSize(FLOW_VIEWPORTS[1440]);
      await search(`LM${run} a`, name('a', 100));
      await shown(page).locator('ion-select.data-table__page-size-select').click();
      await page.locator('ion-popover ion-radio').filter({ hasText: /^\s*25\s*$/ }).click();
      await expect(shown(page).locator('[data-testid=demo-items-row]')).toHaveCount(25);
      await page.setViewportSize(FLOW_VIEWPORTS[390]);
      await expect(shown(page).locator('[data-testid=demo-items-row]')).toHaveCount(25);
      for (const shownRows of [50, 75, 100]) {
        await advance(loadMore(), `«Load more» to ${shownRows}`);
        await expect(shown(page).locator('[data-testid=demo-items-row]')).toHaveCount(shownRows);
      }
      await expect(row(page, name('a', 1))).toBeVisible();
      await expect(loadMore(), 'every row is shown').toHaveCount(0);
      await snap(page, 'CLOSE-DEMO-load-more-100', '390');
    });

    for (const width of ['834', '1440'] as const) {
      await test.step(`${width}: the same 130 items page on a desk`, async () => {
        await page.setViewportSize(FLOW_VIEWPORTS[width]);
        await search(`LM${run}`, name('b', 30));
        await expect(loadError()).toHaveCount(0);
        await snap(page, 'CLOSE-DEMO-more-than-100', width);
      });
    }
  } finally {
    for (const id of created) await api(context, A, 'POST', '/demo/items/delete', { id });
    await context.close();
  }
});
